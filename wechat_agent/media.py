from dataclasses import dataclass, field
from pathlib import Path

from .util import log
from .wechat import extract_text


@dataclass
class MediaAttachment:
    path: str
    kind: str
    mime_type: str = ""
    file_name: str = ""


@dataclass
class InboundMessage:
    text: str
    prompt: str
    images: list[MediaAttachment] = field(default_factory=list)
    files: list[MediaAttachment] = field(default_factory=list)

    @property
    def has_media(self):
        return bool(self.images or self.files)


def _attachment_name(item):
    if item.file_name:
        return item.file_name
    if item.path:
        return Path(item.path).name
    return "attachment"


def _format_refs(title, items):
    refs = [f"{title}:"]
    for item in items:
        if not item.path:
            continue
        refs.append(f"- {_attachment_name(item)}: {item.path}")
    return "\n".join(refs)


def build_prompt(text, images=None, files=None):
    images = images or []
    files = files or []
    attachments = [item for item in images + files if item.path]

    prompt = str(text or "").strip()
    if not prompt and attachments:
        if images and not files:
            prompt = "Please analyze the attached image(s)."
        elif files and not images:
            prompt = "Please analyze the attached file(s)."
        else:
            prompt = "Please analyze the attached content."

    refs = []
    if images:
        refs.append(_format_refs("本地图片", images))
        refs.append("请直接查看上面的本地图片后再回答。")
    if files:
        refs.append(_format_refs("本地文件", files))
        refs.append("请直接读取上面的本地文件后再回答。")

    body = ""
    if prompt and refs:
        body = f"{prompt}\n\n" + "\n".join(refs)
    elif refs:
        body = "\n".join(refs)
    else:
        body = prompt.strip()

    protocol = "\n\n".join(
        [
            "如果你需要把本机上的图片、视频或文件回传到微信，请在最终回复末尾追加一个唯一的 JSON 代码块。",
            "不要在解释性文字里提路径，只在这个代码块里提供路径。",
            "如果下文给出了会话附件别名，优先使用这些别名，例如 @image1、@file1，避免手写长路径出错。",
            "代码块格式如下：",
            "```wechat-reply",
            '{"text":"发给用户的文本，可留空","media_paths":["@image1","绝对路径或相对当前项目的路径"]}',
            "```",
            "如果不需要回传文件，就不要输出这个代码块。",
        ]
    )

    if body:
        return f"{body}\n\n{protocol}"
    return protocol


def parse_inbound_message(wechat_client, msg):
    text = extract_text(msg)
    try:
        media_payload = wechat_client.collect_inbound_media(msg)
    except Exception as err:
        log(f"处理微信附件失败: {err}")
        media_payload = {"images": [], "files": []}
        if not text:
            text = "用户发送了一条附件消息，但当前附件下载失败。请先告知用户稍后重试，必要时让用户补发文字说明。"

    images = []
    files = []
    for item in media_payload.get("images") or []:
        images.append(
            MediaAttachment(
                path=str(item.get("path") or ""),
                kind="image",
                mime_type=str(item.get("mimeType") or ""),
                file_name=str(item.get("fileName") or ""),
            )
        )

    for item in media_payload.get("files") or []:
        files.append(
            MediaAttachment(
                path=str(item.get("path") or ""),
                kind=str(item.get("kind") or "file"),
                mime_type=str(item.get("mimeType") or ""),
                file_name=str(item.get("fileName") or ""),
            )
        )

    prompt = build_prompt(text, images=images, files=files)
    return InboundMessage(text=text, prompt=prompt, images=images, files=files)
