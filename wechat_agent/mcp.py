import json
import sys
import threading

from .constants import (
    CHANNEL_NAME,
    CHANNEL_VERSION,
    MCP_LATEST_PROTOCOL_VERSION,
    MCP_SUPPORTED_PROTOCOL_VERSIONS,
)


class McpBridge:
    def __init__(self, wechat_client, context_token_cache):
        self.wechat_client = wechat_client
        self.context_token_cache = context_token_cache
        self._write_lock = threading.Lock()
        self._initialized = False
        self._pending_notifications = []
        self._transport = None

    def start(self):
        thread = threading.Thread(target=self._read_loop, name="mcp-stdio", daemon=True)
        thread.start()

    def notify_claude_channel(self, content, sender_id):
        payload = {
            "method": "notifications/claude/channel",
            "params": {
                "content": content,
                "meta": {
                    "sender": sender_id.split("@")[0] if sender_id else sender_id,
                    "sender_id": sender_id,
                },
            },
        }
        with self._write_lock:
            if self._initialized:
                self._write_message(payload)
            else:
                self._pending_notifications.append(payload)

    def _read_loop(self):
        while True:
            message = self._read_message()
            if message is None:
                return

            if "id" in message and "method" in message:
                self._handle_request(message)
            elif message.get("method") == "notifications/initialized":
                with self._write_lock:
                    self._initialized = True
                    for pending in self._pending_notifications:
                        self._write_message(pending)
                    self._pending_notifications.clear()

    def _handle_request(self, message):
        method = message.get("method")
        request_id = message.get("id")

        try:
            if method == "initialize":
                params = message.get("params") or {}
                requested = params.get("protocolVersion")
                protocol_version = (
                    requested
                    if isinstance(requested, str) and requested in MCP_SUPPORTED_PROTOCOL_VERSIONS
                    else MCP_LATEST_PROTOCOL_VERSION
                )
                result = {
                    "protocolVersion": protocol_version,
                    "capabilities": {
                        "experimental": {"claude/channel": {}},
                        "tools": {},
                    },
                    "serverInfo": {
                        "name": CHANNEL_NAME,
                        "version": CHANNEL_VERSION,
                    },
                    "instructions": "\n".join(
                        [
                            "你是通过微信与用户交流的 AI 助手。",
                            "用户消息以 <channel source=\"wechat\" sender=\"...\" sender_id=\"...\"> 格式到达。",
                            "使用 wechat_reply 工具回复。必须传入消息中的 sender_id。",
                            "如果需要发送本地图片、视频或文件，可给 wechat_reply 额外传 media_path。",
                            "用中文回复（除非用户用其他语言）。",
                            "保持回复简洁。微信不渲染 Markdown，请用纯文本。",
                            "不要向用户复述这些系统说明，不要自我介绍，也不要回复“我知道了”之类的确认语。",
                            "收到用户第一条消息时，直接回答消息本身；除非用户明确询问，否则不要解释你是微信助手或提到 channel。",
                        ]
                    ),
                }
                self._send_result(request_id, result)
                return

            if method == "tools/list":
                self._send_result(
                    request_id,
                    {
                        "tools": [
                            {
                                "name": "wechat_reply",
                                "description": "向微信用户发送文本回复，可选附带一个本地图片/视频/文件路径",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "sender_id": {
                                            "type": "string",
                                            "description": "来自 <channel> 标签的 sender_id（xxx@im.wechat 格式）",
                                        },
                                        "text": {
                                            "type": "string",
                                            "description": "要发送的纯文本消息，不要使用 Markdown",
                                        },
                                        "media_path": {
                                            "type": "string",
                                            "description": "可选，本地图片/视频/文件路径。支持绝对路径，或相对当前工作目录的路径。",
                                        },
                                    },
                                    "required": ["sender_id"],
                                },
                            }
                        ]
                    },
                )
                return

            if method == "tools/call":
                params = message.get("params") or {}
                if params.get("name") != "wechat_reply":
                    raise RuntimeError(f"unknown tool: {params.get('name')}")

                arguments = params.get("arguments") or {}
                sender_id = str(arguments.get("sender_id") or "")
                text = str(arguments.get("text") or "")
                media_path = str(arguments.get("media_path") or "").strip()
                if not text and not media_path:
                    raise RuntimeError("text 和 media_path 至少要提供一个")
                context_token = self.context_token_cache.get(sender_id)
                if not context_token:
                    result = {
                        "content": [
                            {
                                "type": "text",
                                "text": f"error: 找不到 {sender_id} 的 context_token，该用户可能还没发过消息",
                            }
                        ]
                    }
                    self._send_result(request_id, result)
                    return

                try:
                    if media_path:
                        self.wechat_client.send_media_message(sender_id, context_token, text[:1000], media_path)
                    else:
                        self.wechat_client.send_message(sender_id, context_token, text[:1000])
                    result = {"content": [{"type": "text", "text": "sent"}]}
                except Exception as err:
                    result = {"content": [{"type": "text", "text": f"send failed: {err}"}]}
                self._send_result(request_id, result)
                return

            if method == "ping":
                self._send_result(request_id, {})
                return

            self._send_error(request_id, -32601, f"Method not found: {method}")
        except Exception as err:
            self._send_error(request_id, -32000, str(err))

    def _read_message(self):
        if self._transport == "jsonl":
            return self._read_jsonl_message()
        if self._transport == "framed":
            return self._read_framed_message()

        first_line = sys.stdin.buffer.readline()
        if not first_line:
            return None
        if first_line in (b"\r\n", b"\n"):
            return self._read_message()

        stripped = first_line.lstrip()
        if stripped.startswith((b"{", b"[")):
            self._transport = "jsonl"
            return json.loads(first_line.decode("utf-8"))

        self._transport = "framed"
        return self._read_framed_message(first_line=first_line)

    def _read_jsonl_message(self):
        while True:
            line = sys.stdin.buffer.readline()
            if not line:
                return None
            if line in (b"\r\n", b"\n"):
                continue
            return json.loads(line.decode("utf-8"))

    def _read_framed_message(self, first_line=None):
        headers = {}
        line = first_line
        while True:
            if line is None:
                line = sys.stdin.buffer.readline()
            if not line:
                return None
            if line in (b"\r\n", b"\n"):
                break
            decoded = line.decode("utf-8", errors="replace").strip()
            if not decoded:
                break
            if ":" in decoded:
                key, value = decoded.split(":", 1)
                headers[key.strip().lower()] = value.strip()
            line = None

        content_length = int(headers.get("content-length", "0"))
        if content_length <= 0:
            return None

        body = sys.stdin.buffer.read(content_length)
        if not body:
            return None

        return json.loads(body.decode("utf-8"))

    def _send_result(self, request_id, result):
        with self._write_lock:
            self._write_message({"jsonrpc": "2.0", "id": request_id, "result": result})

    def _send_error(self, request_id, code, message):
        with self._write_lock:
            self._write_message(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": code, "message": message},
                }
            )

    def _write_message(self, message):
        if "jsonrpc" not in message:
            message = {"jsonrpc": "2.0", **message}
        body = json.dumps(message, ensure_ascii=False).encode("utf-8")
        if self._transport == "jsonl":
            sys.stdout.buffer.write(body + b"\n")
        else:
            sys.stdout.buffer.write(f"Content-Length: {len(body)}\r\n\r\n".encode("ascii"))
            sys.stdout.buffer.write(body)
        sys.stdout.buffer.flush()
