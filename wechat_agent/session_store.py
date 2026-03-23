import json
from pathlib import Path

from .util import ensure_parent, load_json, now_utc_iso


DEFAULT_SESSION_KEY = "default"
DEFAULT_SESSION_NAME = "默认会话"


class MultiSessionStore:
    def __init__(self, store_file):
        self.store_file = Path(store_file)
        ensure_parent(self.store_file)
        self.data = self._load()

    def _load(self):
        parsed = load_json(self.store_file)
        return self._migrate(parsed if isinstance(parsed, dict) else {})

    def save(self):
        ensure_parent(self.store_file)
        self.store_file.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def list_sessions(self, user_id):
        user = self.data.get(user_id)
        if not isinstance(user, dict):
            return []
        return self._ordered_sessions(user)

    def get_current_session(self, user_id, create_if_missing=False):
        user = self._ensure_user(user_id) if create_if_missing else self.data.get(user_id)
        if not isinstance(user, dict):
            return None
        current = str(user.get("current") or "").strip()
        sessions = user.get("sessions") or {}
        entry = sessions.get(current)
        if not isinstance(entry, dict):
            return None
        return self._with_meta(current, current == str(user.get("current") or "").strip(), entry)

    def get_current_engine_id(self, user_id, create_if_missing=False):
        session = self.get_current_session(user_id, create_if_missing=create_if_missing)
        if not session:
            return None
        engine_id = session.get("engineId")
        return engine_id if isinstance(engine_id, str) and engine_id.strip() else None

    def set_current_engine_id(self, user_id, engine_id):
        user = self._ensure_user(user_id)
        current = user["current"]
        entry = user["sessions"][current]
        entry["engineId"] = str(engine_id or "").strip() or None
        entry["updatedAt"] = now_utc_iso()

    def clear_current_engine_id(self, user_id):
        user = self._ensure_user(user_id)
        current = user["current"]
        entry = user["sessions"][current]
        entry["engineId"] = None
        entry["updatedAt"] = now_utc_iso()

    def delete_session(self, user_id, target):
        user = self.data.get(user_id)
        if not isinstance(user, dict):
            return None

        selected = self._select_session(user, target)
        if not selected:
            return None

        removed = self._with_meta(selected["key"], selected["current"], user["sessions"][selected["key"]])
        del user["sessions"][selected["key"]]

        if not user["sessions"]:
            self.data.pop(user_id, None)
            return removed

        if user.get("current") == selected["key"]:
            next_session = self._ordered_sessions(user)[0]
            user["current"] = next_session["key"]

        return removed

    def clear_sessions(self, user_id):
        user = self.data.get(user_id)
        if not isinstance(user, dict):
            return 0
        count = len(user.get("sessions") or {})
        self.data.pop(user_id, None)
        return count

    def create_session(self, user_id, name=None):
        user = self.data.get(user_id)
        if not isinstance(user, dict):
            user = {"current": "", "sessions": {}}
            self.data[user_id] = user

        session_key = self._generate_key(user)
        session_name = self._unique_name(user, name or "新会话")
        now = now_utc_iso()
        user["sessions"][session_key] = {
            "name": session_name,
            "engineId": None,
            "createdAt": now,
            "updatedAt": now,
        }
        user["current"] = session_key
        return self._with_meta(session_key, True, user["sessions"][session_key])

    def switch_session(self, user_id, target):
        user = self.data.get(user_id)
        if not isinstance(user, dict):
            return None

        selected = self._select_session(user, target)
        if not selected:
            return None

        user["current"] = selected["key"]
        session = user["sessions"][selected["key"]]
        session["updatedAt"] = now_utc_iso()
        return self._with_meta(selected["key"], True, session)

    def _ensure_user(self, user_id):
        user = self.data.get(user_id)
        if isinstance(user, dict):
            sessions = user.get("sessions")
            if isinstance(sessions, dict) and sessions:
                current = str(user.get("current") or "").strip()
                if current in sessions:
                    return user

        now = now_utc_iso()
        self.data[user_id] = {
            "current": DEFAULT_SESSION_KEY,
            "sessions": {
                DEFAULT_SESSION_KEY: {
                    "name": DEFAULT_SESSION_NAME,
                    "engineId": None,
                    "createdAt": now,
                    "updatedAt": now,
                }
            },
        }
        return self.data[user_id]

    def _ordered_sessions(self, user):
        current = str(user.get("current") or "").strip()
        sessions = user.get("sessions") or {}
        items = []
        for key, entry in sessions.items():
            if not isinstance(entry, dict):
                continue
            items.append(self._with_meta(key, key == current, entry))

        def sort_key(entry):
            return (0 if entry["current"] else 1, -self._time_rank(entry.get("updatedAt")), entry["name"])

        return sorted(items, key=sort_key)

    def _select_session(self, user, target):
        target_text = str(target or "").strip()
        if not target_text:
            return None

        ordered = self._ordered_sessions(user)
        if target_text.isdigit():
            index = int(target_text) - 1
            if 0 <= index < len(ordered):
                return ordered[index]
            return None

        lowered = target_text.casefold()
        for entry in ordered:
            if entry["key"].casefold() == lowered or str(entry.get("name") or "").casefold() == lowered:
                return entry
        return None

    @staticmethod
    def _time_rank(value):
        if not isinstance(value, str) or not value:
            return 0
        digits = "".join(ch for ch in value if ch.isdigit())
        try:
            return int(digits or "0")
        except ValueError:
            return 0

    @staticmethod
    def _with_meta(key, is_current, entry):
        return {
            "key": key,
            "current": is_current,
            "name": str(entry.get("name") or DEFAULT_SESSION_NAME),
            "engineId": entry.get("engineId"),
            "createdAt": entry.get("createdAt"),
            "updatedAt": entry.get("updatedAt"),
        }

    @staticmethod
    def _generate_key(user):
        sessions = user.get("sessions") or {}
        index = len(sessions) + 1
        while True:
            key = f"session-{index}"
            if key not in sessions:
                return key
            index += 1

    @staticmethod
    def _unique_name(user, base_name):
        sessions = user.get("sessions") or {}
        existing = {str((entry or {}).get("name") or "").strip() for entry in sessions.values() if isinstance(entry, dict)}
        name = str(base_name or "").strip() or "新会话"
        if name not in existing:
            return name
        index = 2
        while True:
            candidate = f"{name} {index}"
            if candidate not in existing:
                return candidate
            index += 1

    def _migrate(self, parsed):
        migrated = {}
        for user_id, value in parsed.items():
            if isinstance(value, str):
                now = now_utc_iso()
                migrated[user_id] = {
                    "current": DEFAULT_SESSION_KEY,
                    "sessions": {
                        DEFAULT_SESSION_KEY: {
                            "name": DEFAULT_SESSION_NAME,
                            "engineId": value,
                            "createdAt": now,
                            "updatedAt": now,
                        }
                    },
                }
                continue

            if not isinstance(value, dict):
                continue

            sessions = value.get("sessions")
            if not isinstance(sessions, dict):
                continue

            normalized_sessions = {}
            for key, entry in sessions.items():
                if isinstance(entry, str):
                    now = now_utc_iso()
                    normalized_sessions[str(key)] = {
                        "name": str(key or DEFAULT_SESSION_NAME),
                        "engineId": entry,
                        "createdAt": now,
                        "updatedAt": now,
                    }
                    continue

                if not isinstance(entry, dict):
                    continue

                normalized_sessions[str(key)] = {
                    "name": str(entry.get("name") or key or DEFAULT_SESSION_NAME),
                    "engineId": str(entry.get("engineId") or "").strip() or None,
                    "createdAt": entry.get("createdAt") or now_utc_iso(),
                    "updatedAt": entry.get("updatedAt") or entry.get("createdAt") or now_utc_iso(),
                }

            if not normalized_sessions:
                continue

            current = str(value.get("current") or "").strip()
            if current not in normalized_sessions:
                current = next(iter(normalized_sessions))

            migrated[user_id] = {
                "current": current,
                "sessions": normalized_sessions,
            }

        return migrated
