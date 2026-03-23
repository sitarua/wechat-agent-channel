import atexit
import queue
import signal
import threading
import sys

from .codex import CodexRunner
from .opencode import OpenCodeRunner
from .constants import BACKOFF_DELAY_MS, MAX_CONSECUTIVE_FAILURES, RETRY_DELAY_MS
from .lock import SingleInstanceLock
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
from .wechat import WechatClient, extract_text


SESSION_COMMAND_ALIASES = {
    "new": ["/new", "/新建", "/新任务", "新建会话", "新任务", "新会话", "开始新任务"],
    "list": ["/list", "/列表", "/会话列表", "会话列表", "列出会话"],
    "current": ["/current", "/当前", "/当前会话", "当前会话"],
    "switch": ["/switch", "/切换", "/切换会话", "切换会话"],
}


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
    _create_worker(task_queue)

    def send_provider_result(provider, sender_id, result, context_token=None):
        sender = sender_id.split("@")[0]
        ctx = context_token
        if not ctx:
            log(f"[{provider}] 已拿到结果，但无法回复 {sender}：缺少 context_token")
            return

        response = wechat_client.send_message(sender_id, ctx, result[:1000])
        message_id = None
        if isinstance(response, dict):
            message_id = response.get("message_id") or response.get("msg_id")

        if message_id:
            log(f"[{provider}] 已回复 {sender}，message_id={message_id}")
        else:
            log(f"[{provider}] 已回复 {sender}，sendMessage 返回: {response}")

    def handle_session_command(sender_id, text, context_token):
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
            send_provider_result("system", sender_id, "当前 provider 不支持会话命令。", context_token=context_token)
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
        send_provider_result("session", sender_id, reply, context_token=context_token)
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

                text = extract_text(msg)
                if not text:
                    continue

                sender_id = msg.get("from_user_id") or "unknown"
                context_token = msg.get("context_token")
                if not context_token:
                    log(f"收到消息但缺少 context_token: from={sender_id.split('@')[0]}，后续可能无法自动回复")

                log(f"收到消息: from={sender_id.split('@')[0]} text={text[:60]}")

                if handle_session_command(sender_id, text, context_token):
                    continue

                if default_provider == "codex":

                    def codex_task(sender_id=sender_id, text=text, context_token=context_token):
                        log(f"[codex] 处理来自 {sender_id.split('@')[0]} 的消息...")
                        log("[codex] 已转交 Codex，会在拿到结果后自动回复微信")
                        result = codex_runner.run(sender_id, text)
                        log(f"[codex] 已收到结果，准备回复 {sender_id.split('@')[0]}")
                        send_provider_result("codex", sender_id, result, context_token=context_token)

                    task_queue.put(codex_task)
                elif default_provider == "opencode":

                    def opencode_task(sender_id=sender_id, text=text, context_token=context_token):
                        log(f"[opencode] 处理来自 {sender_id.split('@')[0]} 的消息...")
                        log("[opencode] 已转交 OpenCode，会在拿到结果后自动回复微信")
                        result = opencode_runner.run(sender_id, text)
                        log(f"[opencode] 已收到结果，准备回复 {sender_id.split('@')[0]}")
                        send_provider_result("opencode", sender_id, result, context_token=context_token)

                    task_queue.put(opencode_task)

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
