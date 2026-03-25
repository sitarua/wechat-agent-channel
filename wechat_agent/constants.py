import json
import os
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent.parent


def _load_channel_version():
    version_file = PROJECT_DIR / "version.json"
    try:
        parsed = json.loads(version_file.read_text(encoding="utf-8"))
    except Exception:
        return "1.2.1"

    version = str((parsed or {}).get("version") or "").strip()
    return version or "1.2.1"


CHANNEL_NAME = "wechat"
CHANNEL_VERSION = _load_channel_version()
DEFAULT_BASE_URL = "https://ilinkai.weixin.qq.com"
DEFAULT_CDN_BASE_URL = "https://novac2c.cdn.weixin.qq.com/c2c"
SUPPORTED_PROVIDERS = {"claude", "codex", "opencode"}

MAX_CONSECUTIVE_FAILURES = 3
BACKOFF_DELAY_MS = 30_000
RETRY_DELAY_MS = 2_000
LONG_POLL_TIMEOUT_MS = 35_000
DEFAULT_CODEX_TIMEOUT_MS = 900_000
DEFAULT_OPENCODE_TIMEOUT_MS = 900_000

BOT_TYPE = "3"
LOGIN_TIMEOUT_MS = 480_000
STATUS_TIMEOUT_MS = 35_000
MEDIA_CLI_TIMEOUT_MS = 120_000
DEFAULT_OUTBOUND_MEDIA_MAX_BYTES = 50 * 1024 * 1024


def load_outbound_media_max_bytes():
    raw = os.environ.get("WECHAT_OUTBOUND_MEDIA_MAX_BYTES", "").strip()
    if not raw:
        return DEFAULT_OUTBOUND_MEDIA_MAX_BYTES
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_OUTBOUND_MEDIA_MAX_BYTES
    return value if value > 0 else DEFAULT_OUTBOUND_MEDIA_MAX_BYTES

MCP_LATEST_PROTOCOL_VERSION = "2025-11-25"
MCP_SUPPORTED_PROTOCOL_VERSIONS = {
    "2025-11-25",
    "2025-06-18",
    "2025-03-26",
    "2024-11-05",
    "2024-10-07",
}
