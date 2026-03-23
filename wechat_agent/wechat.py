import json
import os
import socket
import subprocess
import time
import urllib.error
import urllib.request

from .constants import CHANNEL_VERSION, LONG_POLL_TIMEOUT_MS, MEDIA_CLI_TIMEOUT_MS, PROJECT_DIR
from .state import load_account
from .util import random_wechat_uin


class WechatApiError(RuntimeError):
    def __init__(self, action, response):
        self.action = action
        self.response = response if isinstance(response, dict) else {"raw": response}
        self.ret = self.response.get("ret")
        self.errcode = self.response.get("errcode")
        self.errmsg = self.response.get("errmsg") or self.response.get("msg") or ""
        detail = {"ret": self.ret, "errcode": self.errcode, "errmsg": self.errmsg}
        super().__init__(f"{action} 失败: {json.dumps(detail, ensure_ascii=False)}")


class WechatClient:
    def __init__(self):
        self._account = None

    def get_account(self):
        self._account = load_account()
        if not self._account or not self._account.get("token"):
            raise RuntimeError("未找到微信登录凭据，请先运行 `npm run setup` 或设置 BOT_TOKEN")
        return self._account

    @staticmethod
    def _normalize_uin(value):
        text = str(value or "").strip()
        if not text:
            return ""
        return text.split("@", 1)[0].strip()

    def _build_headers(self, body, *, wechat_uin=None):
        account = self.get_account()
        headers = {
            "Content-Type": "application/json",
            "AuthorizationType": "ilink_bot_token",
            "Authorization": f"Bearer {account['token']}",
            "Content-Length": str(len(body.encode("utf-8"))),
        }
        resolved_uin = self._normalize_uin(wechat_uin)
        if not resolved_uin:
            resolved_uin = self._normalize_uin(os.environ.get("WECHAT_AGENT_WECHAT_UIN", ""))
        if not resolved_uin:
            resolved_uin = random_wechat_uin()
        if resolved_uin:
            headers["X-WECHAT-UIN"] = resolved_uin
        return headers

    def _request_json(self, url, body, timeout_s, *, wechat_uin=None):
        request = urllib.request.Request(
            url=url,
            method="POST",
            data=body.encode("utf-8"),
            headers=self._build_headers(body, wechat_uin=wechat_uin),
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_s) as response:
                raw = response.read().decode("utf-8")
                try:
                    return json.loads(raw)
                except json.JSONDecodeError as err:
                    raise RuntimeError(f"接口返回了非 JSON 内容: {raw[:300]}") from err
        except urllib.error.HTTPError as err:
            detail = ""
            try:
                raw = err.read().decode("utf-8", errors="replace").strip()
                if raw:
                    detail = f": {raw[:300]}"
            except Exception:
                pass
            raise RuntimeError(f"HTTP {err.code}{detail}") from err

    @staticmethod
    def _raise_on_error_response(action, response):
        if not isinstance(response, dict):
            raise RuntimeError(f"{action} 返回格式异常: {response}")

        ret = response.get("ret")
        errcode = response.get("errcode")
        if ret in (None, 0) and errcode in (None, 0):
            return

        raise WechatApiError(action, response)

    def get_updates(self, get_updates_buf=""):
        account = self.get_account()
        body = json.dumps(
            {
                "get_updates_buf": get_updates_buf,
                "base_info": {"channel_version": CHANNEL_VERSION},
            },
            ensure_ascii=False,
        )
        try:
            response = self._request_json(
                f"{account['baseUrl']}/ilink/bot/getupdates",
                body,
                timeout_s=(LONG_POLL_TIMEOUT_MS + 5_000) / 1000,
            )
            self._raise_on_error_response("getUpdates", response)
            return response
        except (TimeoutError, socket.timeout, urllib.error.URLError) as err:
            reason = getattr(err, "reason", err)
            if isinstance(reason, socket.timeout) or isinstance(err, TimeoutError):
                return {"ret": 0, "msgs": [], "get_updates_buf": get_updates_buf}
            raise

    def _send_message_request(self, payload, *, wechat_uin=None):
        account = self.get_account()
        body = json.dumps(payload, ensure_ascii=False)
        response = self._request_json(
            f"{account['baseUrl']}/ilink/bot/sendmessage",
            body,
            timeout_s=15,
            wechat_uin=wechat_uin,
        )
        self._raise_on_error_response("sendMessage", response)
        return response

    def _run_media_cli(self, command, payload):
        script_path = PROJECT_DIR / "scripts" / "wechat-media-cli.mjs"
        process = subprocess.run(
            ["node", str(script_path), command],
            input=json.dumps(payload, ensure_ascii=False),
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=MEDIA_CLI_TIMEOUT_MS / 1000,
            check=False,
        )
        if process.returncode != 0:
            detail = (process.stderr or process.stdout or "").strip()
            raise RuntimeError(f"微信媒体桥执行失败: {detail or f'退出码 {process.returncode}'}")

        output = (process.stdout or "").strip()
        if not output:
            return {}
        try:
            return json.loads(output)
        except json.JSONDecodeError as err:
            raise RuntimeError(f"微信媒体桥返回了非法 JSON: {output[:300]}") from err

    def send_message(self, to_user_id, context_token, text):
        client_id = f"wechat-agent:{int(time.time() * 1000)}"
        payload = {
            "msg": {
                "from_user_id": "",
                "to_user_id": to_user_id,
                "client_id": client_id,
                "message_type": 2,
                "message_state": 2,
                "item_list": [
                    {
                        "type": 1,
                        "text_item": {
                            "text": text,
                        },
                    }
                ],
                "context_token": context_token,
            },
            "base_info": {"channel_version": CHANNEL_VERSION},
        }
        response = self._send_message_request(payload)
        if isinstance(response, dict):
            response = dict(response)
            response.setdefault("_client_id", client_id)
            response.setdefault("_payload_variant", "msg_wrapper")
        return response

    def send_media_message(self, to_user_id, context_token, text, media_path):
        account = self.get_account()
        return self._run_media_cli(
            "send-media",
            {
                "account": {
                    "token": account["token"],
                    "baseUrl": account["baseUrl"],
                    "cdnBaseUrl": account.get("cdnBaseUrl"),
                },
                "toUserId": to_user_id,
                "contextToken": context_token,
                "text": text,
                "mediaPath": media_path,
                "workDir": str(PROJECT_DIR),
            },
        )

    def collect_inbound_media(self, msg):
        item_list = msg.get("item_list") or []
        has_media = any(
            item.get("type") in {2, 3, 4, 5}
            or (
                item.get("type") == 1
                and isinstance(item.get("ref_msg"), dict)
                and isinstance(item["ref_msg"].get("message_item"), dict)
                and item["ref_msg"]["message_item"].get("type") in {2, 3, 4, 5}
            )
            for item in item_list
        )
        if not has_media:
            return {"images": [], "files": []}

        account = self.get_account()
        return self._run_media_cli(
            "collect-inbound",
            {
                "account": {
                    "token": account["token"],
                    "baseUrl": account["baseUrl"],
                    "cdnBaseUrl": account.get("cdnBaseUrl"),
                },
                "message": msg,
                "workDir": str(PROJECT_DIR),
            },
        )


def extract_text(msg):
    item_list = msg.get("item_list") or []
    for item in item_list:
        if item.get("type") == 1:
            text_item = item.get("text_item") or {}
            text = text_item.get("text")
            if text:
                ref = item.get("ref_msg")
                if not ref:
                    return text
                parts = []
                title = ref.get("title")
                if title:
                    parts.append(title)
                return f"[引用: {' | '.join(parts)}]\n{text}" if parts else text
        if item.get("type") == 3:
            voice_item = item.get("voice_item") or {}
            if voice_item.get("text"):
                return voice_item["text"]
    return ""
