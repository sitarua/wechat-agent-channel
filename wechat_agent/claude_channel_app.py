from .constants import BACKOFF_DELAY_MS, MAX_CONSECUTIVE_FAILURES, RETRY_DELAY_MS

from .media import parse_inbound_message
from .mcp import McpBridge
from .state import SYNC_BUF_FILE, get_credentials_file, load_account
from .util import log, sleep_ms
from .wechat import WechatClient

def _log_startup_state():
    account = load_account()
    if not account:
        log("⚠️  未找到微信登录凭据，请先运行 npm run claude:setup")
        log(f"凭据文件位置: {get_credentials_file()}")
    elif account.get("source") == "env":
        log("使用环境变量 BOT_TOKEN 登录微信")
    else:
        suffix = f": {account.get('accountId')}" if account.get("accountId") else ""
        log(f"使用本地微信登录凭据{suffix}")


def main():
    _log_startup_state()

    if not load_account():
        raise RuntimeError("未找到微信登录凭据，请先运行 `npm run claude:setup`")

    wechat_client = WechatClient()
    context_token_cache = {}
    mcp_bridge = McpBridge(wechat_client, context_token_cache)
    mcp_bridge.start()

    get_updates_buf = ""
    consecutive_failures = 0
    if SYNC_BUF_FILE.exists():
        try:
            get_updates_buf = SYNC_BUF_FILE.read_text(encoding="utf-8")
            log("恢复上次同步状态")
        except Exception:
            pass

    log("开始监听微信消息...")

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
                if context_token:
                    context_token_cache[sender_id] = context_token
                else:
                    log(f"收到消息但缺少 context_token: from={sender_id.split('@')[0]}，后续可能无法自动回复")

                preview = inbound.text[:60] if inbound.text else "[附件消息]"
                log(
                    f"收到消息: from={sender_id.split('@')[0]} text={preview}"
                    + (f" images={len(inbound.images)} files={len(inbound.files)}" if inbound.has_media else "")
                )
                mcp_bridge.notify_claude_channel(inbound.prompt, sender_id)

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
