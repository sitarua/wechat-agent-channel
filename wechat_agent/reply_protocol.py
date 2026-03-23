import json
import re
from dataclasses import dataclass, field


WECHAT_REPLY_BLOCK_RE = re.compile(
    r"```(?:wechat-reply|wechat_reply|wechatreply)\s*(\{.*?\})\s*```",
    re.IGNORECASE | re.DOTALL,
)


@dataclass
class ParsedReply:
    text: str
    media_paths: list[str] = field(default_factory=list)


def _normalize_media_paths(value):
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, list):
        result = []
        for item in value:
            text = str(item or "").strip()
            if text:
                result.append(text)
        return result
    return []


def parse_agent_reply(raw_text):
    text = str(raw_text or "")
    matches = list(WECHAT_REPLY_BLOCK_RE.finditer(text))
    if not matches:
        return ParsedReply(text=text.strip())

    match = matches[-1]
    payload_raw = match.group(1)
    payload = json.loads(payload_raw)
    if not isinstance(payload, dict):
        raise ValueError("wechat-reply block must be a JSON object")

    visible_text = (text[: match.start()] + text[match.end() :]).strip()
    block_text = str(payload.get("text") or "").strip()
    media_paths = _normalize_media_paths(payload.get("media_paths"))
    if not media_paths:
        media_paths = _normalize_media_paths(payload.get("media_path"))

    final_text = block_text or visible_text
    return ParsedReply(text=final_text, media_paths=media_paths)
