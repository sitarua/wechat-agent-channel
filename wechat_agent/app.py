import atexit
import queue
import signal
import threading
import sys
import time
from pathlib import Path
from uuid import uuid4

from .codex import CodexRunner
from .opencode import OpenCodeRunner
from .constants import BACKOFF_DELAY_MS, MAX_CONSECUTIVE_FAILURES, RETRY_DELAY_MS
from .lock import SingleInstanceLock
from .media import parse_inbound_message
from .reply_protocol import parse_agent_reply
from .state import (
    CODEX_THREAD_STORE_FILE,
    INSTANCE_LOCK_FILE,
    OPENCODE_SESSION_STORE_FILE,
    SYNC_BUF_FILE,
    get_app_config_file,
    get_credentials_file,
    load_account,
    load_app_config,
    route_task,
)
from .util import log, sleep_ms
from .wechat import WechatClient


SESSION_COMMAND_ALIASES = {
    "new": ["/new", "/新建", "/新任务", "新建会话", "新任务", "新会话", "开始新任务"],
    "list": ["/list", "/列表", "/会话列表", "会话列表", "列出会话"],
    "current": ["/current", "/当前", "/当前会话", "当前会话"],
    "switch": ["/switch", "/切换", "/切换会话", "切换会话"],
    "delete": ["/delete", "/删除", "/删除会话", "删除会话"],
    "clear": ["/clear", "/清空", "/清空会话", "清空会话", "清空历史会话"],
}

MESSAGE_BINDING_TTL_SECONDS = 60 * 30
MESSAGE_BINDING_MAX_ITEMS = 2000
SESSION_ATTACHMENT_MAX_ITEMS = 50


def _safe_int_text(value):
    if value is None:
        return "0"
    text = str(value).strip()
    if not text:
        return "0"
    return text


def _trim_token(value, size):
    text = str(value or "").strip()
    if not text:
        return "-"
    return text[:size]


def _build_msg_key(msg, sender_id, context_token):
    message_id = _safe_int_text(msg.get("message_id"))
    seq = _safe_int_text(msg.get("seq"))
    create_time_ms = _safe_int_text(msg.get("create_time_ms"))
    client_id = _trim_token(msg.get("client_id"), 8)
    ctx = _trim_token(context_token, 8)
    sender = _trim_token(str(sender_id or "").split("@")[0], 12)
    nonce = uuid4().hex[:6]
    return f"{sender}|mid:{message_id}|seq:{seq}|ts:{create_time_ms}|ctx:{ctx}|cid:{client_id}|n:{nonce}"


def _provider_session_binding(provider, sender_id, codex_runner, opencode_runner):
    runner = None
    if provider == "codex":
        runner = codex_runner
    elif provider == "opencode":
        runner = opencode_runner
    if runner is None:
        return {"session_key": "-", "session_name": "-", "engine_id": "-"}

    try:
        session = runner.get_current_session(sender_id)
    except Exception:
        session = None

    if not isinstance(session, dict):
        return {"session_key": "-", "session_name": "-", "engine_id": "-"}

    return {
        "session_key": str(session.get("key") or "-"),
        "session_name": str(session.get("name") or "-"),
        "engine_id": str(session.get("engineId") or "-"),
    }


def _format_session_binding(binding):
    data = binding if isinstance(binding, dict) else {}
    return (
        f"session_key={data.get('session_key', '-')}"
        f" session_name={data.get('session_name', '-')}"
        f" engine_id={data.get('engine_id', '-')}"
    )


def _upsert_message_binding(store, msg_key, provider, sender_id, context_token, has_media, session_binding):
    store[msg_key] = {
        "provider": provider,
        "sender_id": sender_id,
        "context_token": str(context_token or ""),
        "has_media": bool(has_media),
        "session_key": (session_binding or {}).get("session_key", "-"),
        "session_name": (session_binding or {}).get("session_name", "-"),
        "engine_id": (session_binding or {}).get("engine_id", "-"),
        "updated_at": time.time(),
    }

    cutoff = time.time() - MESSAGE_BINDING_TTL_SECONDS
    stale_keys = [key for key, value in store.items() if float(value.get("updated_at") or 0) < cutoff]
    for key in stale_keys:
        store.pop(key, None)

    if len(store) > MESSAGE_BINDING_MAX_ITEMS:
        ordered = sorted(store.items(), key=lambda item: float(item[1].get("updated_at") or 0))
        for key, _ in ordered[: len(store) - MESSAGE_BINDING_MAX_ITEMS]:
            store.pop(key, None)


def _session_attachment_store_key(provider, sender_id, session_binding):
    session_key = (session_binding or {}).get("session_key", "-")
    return f"{provider}|{sender_id}|{session_key}"


def _update_session_attachments(store, store_key, inbound):
    record = store.setdefault(
        store_key,
        {
            "images": [],
            "files": [],
            "updated_at": 0.0,
        },
    )

    for item in inbound.images:
        if not item.path:
            continue
        alias = f"@image{len(record['images']) + 1}"
        record["images"].append({"alias": alias, "path": item.path, "name": item.file_name or Path(item.path).name})

    for item in inbound.files:
        if not item.path:
            continue
        alias = f"@file{len(record['files']) + 1}"
        record["files"].append({"alias": alias, "path": item.path, "name": item.file_name or Path(item.path).name})

    if len(record["images"]) > SESSION_ATTACHMENT_MAX_ITEMS:
        record["images"] = record["images"][-SESSION_ATTACHMENT_MAX_ITEMS:]
    if len(record["files"]) > SESSION_ATTACHMENT_MAX_ITEMS:
        record["files"] = record["files"][-SESSION_ATTACHMENT_MAX_ITEMS:]

    record["updated_at"] = time.time()
    return record


def _session_attachment_alias_map(record):
    aliases = {}
    data = record if isinstance(record, dict) else {}
    for key in ("images", "files"):
        for item in data.get(key) or []:
            alias = str(item.get("alias") or "").strip()
            path = str(item.get("path") or "").strip()
            if alias and path:
                aliases[alias] = path
    return aliases


def _format_session_attachment_refs(record):
    data = record if isinstance(record, dict) else {}
    lines = []
    images = data.get("images") or []
    files = data.get("files") or []

    if images:
        lines.append("当前会话可引用的图片附件：")
        for item in images[-10:]:
            lines.append(f"- {item['alias']} {item['name']}: {item['path']}")

    if files:
        lines.append("当前会话可引用的文件附件：")
        for item in files[-10:]:
            lines.append(f"- {item['alias']} {item['name']}: {item['path']}")

    if not lines:
        return ""

    lines.extend(
        [
            "如果要回传历史附件，优先使用这些会话别名，例如 @image2 或 @file3。",
            "会话别名比手写路径更可靠。",
        ]
    )
    return "\n".join(lines)


def _parse_session_command(text):
    stripped = str(text or "").strip()
    if not stripped:
        return None

    for action, aliases in SESSION_COMMAND_ALIASES.items():
        for alias in aliases:
            if stripped == alias:
                return {"action": action, "arg": ""}
            for separator in (" ", ":", "："):
                prefix = f"{alias}{separator}"
                if stripped.startswith(prefix):
                    return {"action": action, "arg": stripped[len(prefix):].strip()}
    return None


def _format_session_summary(session, index=None):
    if not session:
        return "暂无会话"
    prefix = f"{index}. " if index is not None else ""
    marker = " [当前]" if session.get("current") else ""
    state = "未开始" if not session.get("engineId") else "已开始"
    return f"{prefix}{session.get('name')}{marker} ({state})"


def _log_prompt_dispatch(provider, sender_id, prompt):
    preview = str(prompt or "").replace("\r", " ").replace("\n", " ").strip()
    if len(preview) > 300:
        preview = preview[:300] + "..."
    log(f"[{provider}] 发给 {sender_id.split('@')[0]} 的 prompt: {preview}")


def _register_exit_handlers(lock):
    atexit.register(lock.release)

    def handle_exit(_signum, _frame):
        lock.release()
        raise SystemExit(0)

    for sig_name in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, sig_name, None)
        if sig is not None:
            signal.signal(sig, handle_exit)


def _log_startup_state():
    account = load_account()
    if not account:
        log("⚠️  未找到微信登录凭据，请先运行 npm run setup 或设置 BOT_TOKEN")
        log(f"凭据文件位置: {get_credentials_file()}")
    elif account.get("source") == "env":
        log("使用环境变量 BOT_TOKEN 登录微信")
    else:
        suffix = f": {account.get('accountId')}" if account.get("accountId") else ""
        log(f"使用本地微信登录凭据{suffix}")

    app_config = load_app_config()
    if not app_config or not app_config.get("defaultProvider"):
        log("⚠️  未找到 provider 配置，默认回退到 codex")
        log(f"配置文件位置: {get_app_config_file()}")
        log("请运行 npm run setup 完成首次 provider 选择")
    elif app_config.get("defaultProvider") == "claude" and sys.stdin.isatty():
        log("⚠️  当前默认 provider 是 claude，但 Claude 现在走独立插件模式。")
        log("请运行 `npm run claude:install`，然后用 `claude --dangerously-load-development-channels server:wechat` 启动。")


def _create_worker(task_queue):
    def worker():
        while True:
            task = task_queue.get()
            try:
                task()
            except Exception as err:
                log(f"任务执行失败: {err}")
            finally:
                task_queue.task_done()

    threading.Thread(target=worker, name="wechat-worker", daemon=True).start()


def main():
    lock = SingleInstanceLock(INSTANCE_LOCK_FILE)
    if not lock.acquire():
        return

    _register_exit_handlers(lock)
    _log_startup_state()

    app_config = load_app_config()
    default_provider = route_task((app_config or {}).get("defaultProvider"))
    if default_provider == "claude":
        log("Claude Code 已从主应用路径拆出。")
        log("请运行 `npm run claude:install`，然后用 `claude --dangerously-load-development-channels server:wechat` 启动。")
        return

    wechat_client = WechatClient()
    codex_runner = CodexRunner(CODEX_THREAD_STORE_FILE)
    opencode_runner = OpenCodeRunner(OPENCODE_SESSION_STORE_FILE)

    task_queue = queue.Queue()
    message_bindings = {}
    message_bindings_lock = threading.Lock()
    session_attachments = {}
    session_attachments_lock = threading.Lock()
    _create_worker(task_queue)

    def record_message_binding(msg_key, provider, sender_id, context_token, has_media, session_binding, media_aliases=None):
        with message_bindings_lock:
            _upsert_message_binding(
                message_bindings,
                msg_key,
                provider,
                sender_id,
                context_token,
                has_media,
                session_binding,
            )
            if media_aliases:
                message_bindings[msg_key]["media_aliases"] = dict(media_aliases)

    def update_session_attachment_index(provider, sender_id, session_binding, inbound):
        if not inbound or not inbound.has_media:
            with session_attachments_lock:
                return dict(
                    _session_attachment_alias_map(
                        session_attachments.get(_session_attachment_store_key(provider, sender_id, session_binding), {})
                    )
                )

        store_key = _session_attachment_store_key(provider, sender_id, session_binding)
        with session_attachments_lock:
            record = _update_session_attachments(session_attachments, store_key, inbound)
            return dict(_session_attachment_alias_map(record))

    def build_session_attachment_prompt(provider, sender_id, session_binding):
        store_key = _session_attachment_store_key(provider, sender_id, session_binding)
        with session_attachments_lock:
            record = session_attachments.get(store_key)
            return _format_session_attachment_refs(record)

    def get_session_attachment_aliases(provider, sender_id, session_binding):
        store_key = _session_attachment_store_key(provider, sender_id, session_binding)
        with session_attachments_lock:
            return dict(_session_attachment_alias_map(session_attachments.get(store_key)))

    def send_provider_result(provider, sender_id, result, context_token=None, msg_key=None, media_aliases=None):
        sender = sender_id.split("@")[0]
        ctx = context_token
        if not ctx:
            msg_tag = f" msg_key={msg_key}" if msg_key else ""
            log(f"[{provider}] 已拿到结果，但无法回复 {sender}：缺少 context_token{msg_tag}")
            return

        msg_tag = f" msg_key={msg_key}" if msg_key else ""
        try:
            parsed = parse_agent_reply(result)
        except Exception as err:
            log(f"[{provider}] 解析回传协议失败，按纯文本回复: {err}{msg_tag}")
            parsed = None

        if not parsed:
            parsed_text = str(result or "").strip()
            parsed_media_paths = []
        else:
            parsed_text = parsed.text
            parsed_media_paths = list(parsed.media_paths or [])

        normalized_paths = []
        media_errors = []
        alias_map = {str(key): str(value) for key, value in (media_aliases or {}).items()}
        for media_path in parsed_media_paths:
            raw_path = str(media_path or "").strip()
            if not raw_path:
                continue
            candidate_path = alias_map.get(raw_path, raw_path)
            expanded = Path(raw_path).expanduser()
            if candidate_path != raw_path:
                expanded = Path(candidate_path).expanduser()
            resolved = expanded if expanded.is_absolute() else (Path.cwd() / expanded)
            if not resolved.exists():
                media_errors.append(f"文件不存在：{raw_path}")
                continue
            if not resolved.is_file():
                media_errors.append(f"不是文件：{raw_path}")
                continue
            normalized_paths.append(candidate_path)

        sent_any = False
        if normalized_paths:
            for index, media_path in enumerate(normalized_paths):
                text_payload = parsed_text[:1000] if index == 0 else ""
                wechat_client.send_media_message(sender_id, ctx, text_payload, media_path)
                sent_any = True
            log(
                f"[{provider}] 已回复 {sender}，media_count={len(normalized_paths)}"
                + (f" text=yes{msg_tag}" if parsed_text else f" text=no{msg_tag}")
            )
        elif parsed_text:
            response = wechat_client.send_message(sender_id, ctx, parsed_text[:1000])
            sent_any = True
            message_id = None
            if isinstance(response, dict):
                message_id = response.get("message_id") or response.get("msg_id")
            if message_id:
                log(f"[{provider}] 已回复 {sender}，message_id={message_id}{msg_tag}")
            else:
                log(f"[{provider}] 已回复 {sender}，sendMessage 返回: {response}{msg_tag}")

        if media_errors:
            error_text = "\n".join(["以下文件回传失败：", *media_errors])[:1000]
            response = wechat_client.send_message(sender_id, ctx, error_text)
            sent_any = True
            log(f"[{provider}] 文件回传失败，已通知 {sender}：{'; '.join(media_errors)}{msg_tag}")

        if not sent_any:
            fallback = "处理完成，但没有可发送的文本或文件。"
            response = wechat_client.send_message(sender_id, ctx, fallback)
            log(f"[{provider}] 结果为空，已发送兜底提示给 {sender}: {response}{msg_tag}")

    def enqueue_provider_task(provider, sender_id, inbound, context_token, msg_key, session_binding):
        if provider == "codex":

            def codex_task(
                sender_id=sender_id,
                inbound=inbound,
                context_token=context_token,
                msg_key=msg_key,
                session_binding=session_binding,
            ):
                media_aliases = get_session_attachment_aliases("codex", sender_id, session_binding)
                log(
                    f"[codex] 开始处理 from={sender_id.split('@')[0]} msg_key={msg_key} "
                    + _format_session_binding(session_binding)
                )
                log("[codex] 已转交 Codex，会在拿到结果后自动回复微信")
                prompt = inbound.prompt
                session_refs = build_session_attachment_prompt("codex", sender_id, session_binding)
                if session_refs:
                    prompt = f"{prompt}\n\n{session_refs}" if prompt else session_refs
                _log_prompt_dispatch("codex", sender_id, prompt)
                result = codex_runner.run(sender_id, prompt)
                final_binding = _provider_session_binding("codex", sender_id, codex_runner, opencode_runner)
                record_message_binding(
                    msg_key,
                    "codex",
                    sender_id,
                    context_token,
                    inbound.has_media,
                    final_binding,
                    media_aliases=media_aliases,
                )
                log(
                    f"[codex] 已收到结果，准备回复 {sender_id.split('@')[0]} msg_key={msg_key} "
                    + _format_session_binding(final_binding)
                )
                send_provider_result(
                    "codex",
                    sender_id,
                    result,
                    context_token=context_token,
                    msg_key=msg_key,
                    media_aliases=media_aliases,
                )

            task_queue.put(codex_task)
            return

        if provider == "opencode":

            def opencode_task(
                sender_id=sender_id,
                inbound=inbound,
                context_token=context_token,
                msg_key=msg_key,
                session_binding=session_binding,
            ):
                media_aliases = get_session_attachment_aliases("opencode", sender_id, session_binding)
                log(
                    f"[opencode] 开始处理 from={sender_id.split('@')[0]} msg_key={msg_key} "
                    + _format_session_binding(session_binding)
                )
                log("[opencode] 已转交 OpenCode，会在拿到结果后自动回复微信")
                waiting_notice_done = threading.Event()

                def opencode_waiting_notice():
                    if waiting_notice_done.wait(8):
                        return
                    send_provider_result(
                        "opencode",
                        sender_id,
                        "OpenCode 正在处理中，首次回复可能会慢一些，我拿到结果后继续发你。",
                        context_token=context_token,
                        msg_key=msg_key,
                    )

                threading.Thread(
                    target=opencode_waiting_notice,
                    name="opencode-waiting-notice",
                    daemon=True,
                ).start()
                prompt = inbound.prompt
                session_refs = build_session_attachment_prompt("opencode", sender_id, session_binding)
                if session_refs:
                    prompt = f"{prompt}\n\n{session_refs}" if prompt else session_refs
                _log_prompt_dispatch("opencode", sender_id, prompt)
                result = opencode_runner.run(sender_id, prompt)
                waiting_notice_done.set()
                final_binding = _provider_session_binding("opencode", sender_id, codex_runner, opencode_runner)
                record_message_binding(
                    msg_key,
                    "opencode",
                    sender_id,
                    context_token,
                    inbound.has_media,
                    final_binding,
                    media_aliases=media_aliases,
                )
                log(
                    f"[opencode] 已收到结果，准备回复 {sender_id.split('@')[0]} msg_key={msg_key} "
                    + _format_session_binding(final_binding)
                )
                send_provider_result(
                    "opencode",
                    sender_id,
                    result,
                    context_token=context_token,
                    msg_key=msg_key,
                    media_aliases=media_aliases,
                )

            task_queue.put(opencode_task)

    def handle_session_command(sender_id, text, context_token, msg_key):
        parsed = _parse_session_command(text)
        if not parsed:
            return False

        runner = None
        provider_label = default_provider
        if default_provider == "codex":
            runner = codex_runner
        elif default_provider == "opencode":
            runner = opencode_runner

        if runner is None:
            send_provider_result(
                "system",
                sender_id,
                "当前 provider 不支持会话命令。",
                context_token=context_token,
                msg_key=msg_key,
            )
            return True

        action = parsed["action"]
        arg = parsed["arg"]

        if action == "new":
            session = runner.create_session(sender_id, name=arg or None)
            reply = f"已创建新会话：{session['name']}\n下一条普通消息会在这个会话里开始。"
        elif action == "list":
            sessions = runner.list_sessions(sender_id)
            if not sessions:
                reply = "暂无会话。下一条普通消息会自动创建默认会话。"
            else:
                lines = ["会话列表："]
                for index, session in enumerate(sessions, start=1):
                    lines.append(_format_session_summary(session, index=index))
                reply = "\n".join(lines)
        elif action == "current":
            session = runner.get_current_session(sender_id)
            if not session:
                reply = "当前还没有会话。下一条普通消息会自动创建默认会话。"
            else:
                reply = f"当前会话：{_format_session_summary(session)}"
        elif action == "delete":
            if not arg:
                reply = "请提供要删除的会话编号或名称，例如：/delete 2 或 删除会话 新任务"
            else:
                session = runner.delete_session(sender_id, arg)
                if not session:
                    reply = f"未找到会话：{arg}"
                else:
                    current = runner.get_current_session(sender_id)
                    if current:
                        reply = f"已删除会话：{session['name']}\n当前已切换到：{current['name']}"
                    else:
                        reply = f"已删除会话：{session['name']}\n当前已无会话，下一条普通消息会自动创建默认会话。"
        elif action == "clear":
            count = runner.clear_sessions(sender_id)
            if count:
                reply = f"已清空全部会话，共删除 {count} 个会话。\n下一条普通消息会自动创建默认会话。"
            else:
                reply = "当前没有可清空的会话。"
        else:
            if not arg:
                reply = "请提供要切换的会话编号或名称，例如：/switch 2 或 切换会话 新任务"
            else:
                session = runner.switch_session(sender_id, arg)
                if not session:
                    reply = f"未找到会话：{arg}"
                else:
                    reply = f"已切换到会话：{session['name']}\n下一条普通消息会继续这个会话。"

        log(f"[session] {provider_label} command handled for {sender_id.split('@')[0]}: {action} {arg}".strip())
        send_provider_result("session", sender_id, reply, context_token=context_token, msg_key=msg_key)
        return True

    get_updates_buf = ""
    consecutive_failures = 0
    if SYNC_BUF_FILE.exists():
        try:
            get_updates_buf = SYNC_BUF_FILE.read_text(encoding="utf-8")
            log("恢复上次同步状态")
        except Exception:
            pass

    log("开始监听微信消息...")
    log(f"当前默认 provider: {default_provider}")

    while True:
        try:
            response = wechat_client.get_updates(get_updates_buf)

            is_error = (
                ("ret" in response and response.get("ret") not in (None, 0))
                or ("errcode" in response and response.get("errcode") not in (None, 0))
            )
            if is_error:
                consecutive_failures += 1
                errmsg = response.get("errmsg") or ""
                log(
                    f"getUpdates 失败: ret={response.get('ret')} errcode={response.get('errcode')} errmsg={errmsg}"
                )
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    log(f"连续失败 {MAX_CONSECUTIVE_FAILURES} 次，等待 {BACKOFF_DELAY_MS // 1000}s...")
                    consecutive_failures = 0
                    sleep_ms(BACKOFF_DELAY_MS)
                else:
                    sleep_ms(RETRY_DELAY_MS)
                continue

            consecutive_failures = 0

            if response.get("get_updates_buf"):
                get_updates_buf = response["get_updates_buf"]
                try:
                    SYNC_BUF_FILE.write_text(get_updates_buf, encoding="utf-8")
                except Exception:
                    pass

            for msg in response.get("msgs") or []:
                if msg.get("message_type") != 1:
                    continue

                inbound = parse_inbound_message(wechat_client, msg)
                if not inbound.text and not inbound.has_media:
                    continue

                sender_id = msg.get("from_user_id") or "unknown"
                context_token = msg.get("context_token")
                msg_key = _build_msg_key(msg, sender_id, context_token)
                session_binding = _provider_session_binding(default_provider, sender_id, codex_runner, opencode_runner)
                session_media_aliases = update_session_attachment_index(default_provider, sender_id, session_binding, inbound)
                record_message_binding(
                    msg_key,
                    default_provider,
                    sender_id,
                    context_token,
                    inbound.has_media,
                    session_binding,
                    media_aliases=session_media_aliases,
                )
                if not context_token:
                    log(
                        f"收到消息但缺少 context_token: from={sender_id.split('@')[0]} "
                        f"msg_key={msg_key}，后续可能无法自动回复"
                    )

                preview = inbound.text[:60] if inbound.text else "[附件消息]"
                log(
                    f"收到消息: from={sender_id.split('@')[0]} msg_key={msg_key} text={preview} "
                    + _format_session_binding(session_binding)
                    + (f" images={len(inbound.images)} files={len(inbound.files)}" if inbound.has_media else "")
                )

                if inbound.text and handle_session_command(sender_id, inbound.text, context_token, msg_key):
                    continue

                enqueue_provider_task(
                    default_provider,
                    sender_id,
                    inbound,
                    context_token,
                    msg_key,
                    session_binding,
                )

        except KeyboardInterrupt:
            raise
        except Exception as err:
            consecutive_failures += 1
            log(f"轮询异常: {err}")
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                consecutive_failures = 0
                sleep_ms(BACKOFF_DELAY_MS)
            else:
                sleep_ms(RETRY_DELAY_MS)
