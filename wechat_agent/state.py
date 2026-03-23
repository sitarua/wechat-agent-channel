import json
import os
from pathlib import Path

from .constants import DEFAULT_BASE_URL, DEFAULT_CDN_BASE_URL, PROJECT_DIR, SUPPORTED_PROVIDERS
from .util import ensure_parent, load_json, now_utc_iso


STATE_DIR = Path(
    os.environ.get("WECHAT_AGENT_STATE_DIR", "").strip() or (Path.home() / ".wechat-agent-channel")
)
CREDENTIALS_FILE = STATE_DIR / "wechat" / "account.json"
APP_CONFIG_FILE = STATE_DIR / "config.json"
INSTANCE_LOCK_FILE = STATE_DIR / "wechat-agent.lock"
SYNC_BUF_FILE = Path.home() / ".wechat-agent-sync-buf"
CODEX_THREAD_STORE_FILE = PROJECT_DIR / "sessions" / "codex-threads.json"
OPENCODE_SESSION_STORE_FILE = PROJECT_DIR / "sessions" / "opencode-sessions.json"


def normalize_provider(raw):
    return str(raw or "").strip().lower()


def get_credentials_file():
    return CREDENTIALS_FILE


def get_app_config_file():
    return APP_CONFIG_FILE


def load_account():
    env_token = os.environ.get("BOT_TOKEN", "").strip()
    if env_token:
        return {
            "token": env_token,
            "baseUrl": os.environ.get("WECHAT_BASE_URL", "").strip() or DEFAULT_BASE_URL,
            "cdnBaseUrl": os.environ.get("WECHAT_CDN_BASE_URL", "").strip() or DEFAULT_CDN_BASE_URL,
            "source": "env",
        }

    parsed = load_json(CREDENTIALS_FILE)
    if not isinstance(parsed, dict):
        return None

    token = str(parsed.get("token") or "").strip()
    if not token:
        return None

    return {
        "token": token,
        "baseUrl": str(parsed.get("baseUrl") or "").strip() or DEFAULT_BASE_URL,
        "cdnBaseUrl": str(parsed.get("cdnBaseUrl") or "").strip() or DEFAULT_CDN_BASE_URL,
        "accountId": parsed.get("accountId"),
        "userId": parsed.get("userId"),
        "savedAt": parsed.get("savedAt"),
        "source": "file",
    }


def save_account(account):
    ensure_parent(CREDENTIALS_FILE)
    CREDENTIALS_FILE.write_text(
        json.dumps(account, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    try:
        os.chmod(CREDENTIALS_FILE, 0o600)
    except Exception:
        pass


def load_app_config():
    env_provider = normalize_provider(os.environ.get("WECHAT_AGENT_PROVIDER"))
    if env_provider in SUPPORTED_PROVIDERS:
        return {"defaultProvider": env_provider, "source": "env"}

    parsed = load_json(APP_CONFIG_FILE)
    if not isinstance(parsed, dict):
        return None

    provider = normalize_provider(parsed.get("defaultProvider"))
    if provider not in SUPPORTED_PROVIDERS:
        return None

    return {
        "defaultProvider": provider,
        "savedAt": parsed.get("savedAt"),
        "source": "file",
    }


def save_app_config(config):
    provider = normalize_provider((config or {}).get("defaultProvider"))
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(f"不支持的 provider: {config.get('defaultProvider') if config else None}")

    ensure_parent(APP_CONFIG_FILE)
    APP_CONFIG_FILE.write_text(
        json.dumps(
            {
                "defaultProvider": provider,
                "savedAt": config.get("savedAt") or now_utc_iso(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def route_task(default_provider="codex"):
    provider = normalize_provider(default_provider or "codex")
    return provider if provider in SUPPORTED_PROVIDERS else "codex"
