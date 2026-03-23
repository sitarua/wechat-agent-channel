import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from .constants import (
    BOT_TYPE,
    DEFAULT_BASE_URL,
    DEFAULT_CDN_BASE_URL,
    LOGIN_TIMEOUT_MS,
    PROJECT_DIR,
    STATUS_TIMEOUT_MS,
)
from .state import (
    get_app_config_file,
    get_credentials_file,
    load_app_config,
    save_account,
    save_app_config,
)
from .util import configure_stdio, now_utc_iso


def fetch_json(url, *, headers=None, timeout_s=15):
    request = urllib.request.Request(url=url, method="GET", headers=headers or {})
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        return json.loads(response.read().decode("utf-8"))


def prompt_provider(*, force=False):
    existing_config = load_app_config()
    if existing_config and existing_config.get("defaultProvider"):
        if not force:
            print(f"当前默认 provider: {existing_config['defaultProvider']}")
            print(f"配置文件位置: {get_app_config_file()}")
            return existing_config["defaultProvider"]

        print(f"已忽略当前默认 provider: {existing_config['defaultProvider']}")
        print(f"配置文件位置: {get_app_config_file()}")

    print("请选择默认 provider：")
    print("1. Codex")
    print("2. OpenCode")

    while True:
        answer = input("请输入 1 或 2: ").strip()
        if answer == "1":
            save_app_config({"defaultProvider": "codex"})
            print(f"已保存默认 provider: codex ({get_app_config_file()})")
            return "codex"
        if answer == "2":
            save_app_config({"defaultProvider": "opencode"})
            print(f"已保存默认 provider: opencode ({get_app_config_file()})")
            return "opencode"
        print("输入无效，请输入 1 或 2。")


def render_qr_terminal(qr_content):
    script = "require('qrcode-terminal').generate(process.argv[1], { small: true });"
    try:
        completed = subprocess.run(
            ["node", "-e", script, qr_content],
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            check=True,
        )
        output = completed.stdout.strip("\n")
        if output:
            sys.stdout.write(output)
            sys.stdout.write("\n")
            sys.stdout.flush()
            return True
    except Exception:
        pass

    print("无法在终端渲染二维码，请手动处理下面这段二维码内容：\n")
    print(qr_content)
    print()
    return False


def fetch_qr_code(base_url):
    url = f"{base_url}/ilink/bot/get_bot_qrcode?bot_type={BOT_TYPE}"
    return fetch_json(url, timeout_s=15)


def poll_qr_status(base_url, qrcode_id):
    encoded = urllib.parse.quote(qrcode_id, safe="")
    url = f"{base_url}/ilink/bot/get_qrcode_status?qrcode={encoded}"
    try:
        return fetch_json(
            url,
            headers={"iLink-App-ClientVersion": "1"},
            timeout_s=STATUS_TIMEOUT_MS / 1000,
        )
    except (TimeoutError, urllib.error.URLError) as err:
        reason = getattr(err, "reason", err)
        if isinstance(reason, (TimeoutError, socket.timeout)) or isinstance(err, socket.timeout):
            return {"status": "wait"}
        raise


def main(*, reset_provider=False, select_provider=True):
    configure_stdio()
    print("正在获取微信登录二维码...\n")
    qr_response = fetch_qr_code(DEFAULT_BASE_URL)

    qr_content = qr_response.get("qrcode_img_content")
    if not qr_content:
        print("二维码内容缺失，请稍后重试。")
        raise SystemExit(1)

    render_qr_terminal(qr_content)
    print("\n请使用微信扫描上方二维码并确认登录。\n")

    deadline = time.time() + (LOGIN_TIMEOUT_MS / 1000)
    scanned_printed = False

    while time.time() < deadline:
        status = poll_qr_status(DEFAULT_BASE_URL, qr_response["qrcode"])
        current = status.get("status")

        if current == "wait":
            sys.stdout.write(".")
            sys.stdout.flush()
        elif current == "scaned":
            if not scanned_printed:
                print("\n已扫码，请在微信中确认...")
                scanned_printed = True
        elif current == "expired":
            print("\n二维码已过期，请重新运行 `npm run setup`。")
            raise SystemExit(1)
        elif current == "confirmed":
            if not status.get("ilink_bot_id") or not status.get("bot_token"):
                print("\n登录失败：服务端未返回完整凭据。")
                raise SystemExit(1)

            account = {
                "token": status["bot_token"],
                "baseUrl": status.get("baseurl") or DEFAULT_BASE_URL,
                "cdnBaseUrl": DEFAULT_CDN_BASE_URL,
                "accountId": status["ilink_bot_id"],
                "userId": status.get("ilink_user_id"),
                "savedAt": now_utc_iso(),
            }
            save_account(account)

            print("\n微信连接成功。")
            print(f"账号 ID: {account['accountId']}")
            if account.get("userId"):
                print(f"用户 ID: {account['userId']}")
            print(f"凭据已保存到: {get_credentials_file()}")
            if select_provider:
                prompt_provider(force=reset_provider)
            return

        time.sleep(1)

    print("\n登录超时，请重新运行 `npm run setup`。")
    raise SystemExit(1)
