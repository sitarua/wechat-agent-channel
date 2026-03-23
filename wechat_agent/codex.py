from dataclasses import dataclass, field
import json
import os
import shutil
import subprocess
import threading
from pathlib import Path

from .constants import DEFAULT_CODEX_TIMEOUT_MS
from .session_store import MultiSessionStore
from .util import ensure_parent, load_json, log


@dataclass
class CodexEventAccumulator:
    thread_id: str = ""
    item_order: list[str] = field(default_factory=list)
    item_text: dict[str, str] = field(default_factory=dict)
    messages: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    turn_failed: bool = False

    def handle_event(self, event):
        event_type = event.get("type")

        if event_type == "thread.started":
            thread_id = event.get("thread_id")
            if isinstance(thread_id, str) and thread_id.strip():
                self.thread_id = thread_id.strip()
            return

        if event_type in {"item.started", "item.delta", "item.completed"}:
            self._handle_item_event(event_type, event.get("item") or event)
            return

        if event_type in {"turn.failed", "error"}:
            self.turn_failed = True
            message = self._extract_error_message(event)
            if message:
                self.errors.append(message)

    def final_text(self):
        parts = []

        for item_id in self.item_order:
            text = self.item_text.get(item_id, "").strip()
            if text:
                parts.append(text)

        parts.extend(message.strip() for message in self.messages if isinstance(message, str) and message.strip())
        return "\n".join(parts).strip()

    def _handle_item_event(self, event_type, payload):
        item = payload if isinstance(payload, dict) else {}
        item_type = item.get("type") or item.get("item_type") or item.get("itemType")
        item_id = item.get("id") or item.get("item_id") or item.get("itemId")

        if item_type not in (None, "", "agent_message"):
            return

        if isinstance(item_id, str) and item_id and item_id not in self.item_order:
            self.item_order.append(item_id)

        if event_type == "item.delta":
            delta = item.get("delta") or payload.get("delta")
            if isinstance(item_id, str) and isinstance(delta, str) and delta:
                self.item_text[item_id] = self.item_text.get(item_id, "") + delta
            return

        text = item.get("text") or payload.get("text")
        if isinstance(text, str) and text:
            if isinstance(item_id, str) and item_id:
                self.item_text[item_id] = text
            else:
                self.messages.append(text)

    @staticmethod
    def _extract_error_message(event):
        for key in ("message", "error", "stderr"):
            value = event.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        error = event.get("error")
        if isinstance(error, dict):
            for key in ("message", "detail", "stderr"):
                value = error.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()

        try:
            return json.dumps(event, ensure_ascii=False)
        except Exception:
            return str(event)


class CodexRunner:
    def __init__(self, store_file):
        self.store_file = Path(store_file)
        ensure_parent(self.store_file)
        self._lock = threading.Lock()
        self.timeout_ms = self._get_timeout_ms()
        self.model = os.environ.get("CODEX_MODEL", "").strip()
        self.session_store = MultiSessionStore(self.store_file)

    def _get_timeout_ms(self):
        raw = os.environ.get("CODEX_TURN_TIMEOUT_MS", "").strip()
        if not raw:
            return DEFAULT_CODEX_TIMEOUT_MS
        try:
            value = int(raw)
            return value if value > 0 else DEFAULT_CODEX_TIMEOUT_MS
        except ValueError:
            return DEFAULT_CODEX_TIMEOUT_MS

    @staticmethod
    def _wrap_powershell_script(script_path):
        shell = shutil.which("pwsh") or shutil.which("powershell")
        if shell and Path(script_path).exists():
            return [shell, "-NoProfile", "-File", str(script_path)]
        return None

    def _resolve_command(self):
        override = os.environ.get("CODEX_BIN", "").strip()
        if override:
            if os.name == "nt" and override.lower().endswith(".ps1"):
                wrapped = self._wrap_powershell_script(override)
                if wrapped:
                    return wrapped
            return [override]

        if os.name == "nt":
            appdata = os.environ.get("APPDATA", "").strip()
            if appdata:
                wrapped = self._wrap_powershell_script(Path(appdata) / "npm" / "codex.ps1")
                if wrapped:
                    return wrapped
            candidates = ["codex.cmd", "codex.exe", "codex"]
        else:
            candidates = ["codex"]

        for candidate in candidates:
            resolved = shutil.which(candidate)
            if resolved:
                return [resolved]

        return ["codex"]

    def _base_args(self):
        args = self._resolve_command() + [
            "-C",
            str(Path.cwd()),
            "-a",
            "never",
            "-s",
            "danger-full-access",
        ]
        if self.model:
            args.extend(["-m", self.model])
        return args

    def _run_once(self, user_id, user_message, existing_thread_id=None):
        args = self._base_args() + ["exec"]
        if existing_thread_id:
            args.extend(["resume", existing_thread_id])
        args.append("--skip-git-repo-check")
        args.extend(["--json", user_message])
        log(
            "[codex] 启动命令: "
            + json.dumps(
                {
                    "cmd": args[0],
                    "resume": bool(existing_thread_id),
                    "cwd": str(Path.cwd()),
                },
                ensure_ascii=False,
            )
        )

        process = subprocess.Popen(
            args,
            cwd=Path.cwd(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
            bufsize=1,
        )
        accumulator = CodexEventAccumulator(thread_id=existing_thread_id or "")

        stdout_error = []
        stderr_chunks = []

        def read_stdout():
            try:
                assert process.stdout is not None
                for line in process.stdout:
                    stripped = line.strip()
                    if not stripped:
                        continue
                    try:
                        event = json.loads(stripped)
                    except json.JSONDecodeError:
                        continue
                    accumulator.handle_event(event)
            except Exception as err:
                stdout_error.append(err)

        def read_stderr():
            try:
                assert process.stderr is not None
                for line in process.stderr:
                    stderr_chunks.append(line)
            except Exception:
                pass

        reader = threading.Thread(target=read_stdout, name="codex-stdout-reader", daemon=True)
        stderr_reader = threading.Thread(target=read_stderr, name="codex-stderr-reader", daemon=True)
        reader.start()
        stderr_reader.start()

        try:
            return_code = process.wait(timeout=self.timeout_ms / 1000)
        except subprocess.TimeoutExpired:
            process.kill()
            reader.join(timeout=2)
            stderr_reader.join(timeout=2)
            raise

        reader.join(timeout=2)
        stderr_reader.join(timeout=2)
        stderr_text = "".join(stderr_chunks).strip()

        if stdout_error:
            raise RuntimeError(str(stdout_error[-1]))

        result_text = accumulator.final_text()

        if accumulator.thread_id:
            with self._lock:
                self.session_store.set_current_engine_id(user_id, accumulator.thread_id)
                self.session_store.save()

        if return_code == 0 and result_text:
            return result_text

        error_message = result_text or (accumulator.errors[-1] if accumulator.errors else "")
        if not error_message and stderr_text:
            lines = [line.strip() for line in stderr_text.splitlines() if line.strip()]
            if lines:
                error_message = lines[-1]

        raise RuntimeError(error_message or f"codex 返回非零退出码: {return_code}")

    def run(self, user_id, user_message):
        with self._lock:
            existing_thread_id = self.session_store.get_current_engine_id(user_id, create_if_missing=True)
            self.session_store.save()
        try:
            return self._run_once(user_id, user_message, existing_thread_id=existing_thread_id)
        except subprocess.TimeoutExpired:
            seconds = max(1, self.timeout_ms // 1000)
            return f"❌ Codex 在 {seconds} 秒内没有返回结果，请稍后重试。"
        except Exception as first_error:
            if existing_thread_id:
                log(f"[codex] 续用会话失败，改为新会话重试: {first_error}")
                with self._lock:
                    self.session_store.clear_current_engine_id(user_id)
                    self.session_store.save()
                try:
                    return self._run_once(user_id, user_message, existing_thread_id=None)
                except subprocess.TimeoutExpired:
                    seconds = max(1, self.timeout_ms // 1000)
                    return f"❌ Codex 在 {seconds} 秒内没有返回结果，请稍后重试。"
                except Exception as second_error:
                    return f"❌ Codex 执行失败：{second_error}"
            return f"❌ Codex 执行失败：{first_error}"

    def create_session(self, user_id, name=None):
        with self._lock:
            session = self.session_store.create_session(user_id, name=name)
            self.session_store.save()
            return session

    def list_sessions(self, user_id):
        with self._lock:
            return self.session_store.list_sessions(user_id)

    def get_current_session(self, user_id):
        with self._lock:
            return self.session_store.get_current_session(user_id, create_if_missing=False)

    def switch_session(self, user_id, target):
        with self._lock:
            session = self.session_store.switch_session(user_id, target)
            if session:
                self.session_store.save()
            return session

    def delete_session(self, user_id, target):
        with self._lock:
            session = self.session_store.delete_session(user_id, target)
            if session:
                self.session_store.save()
            return session

    def clear_sessions(self, user_id):
        with self._lock:
            count = self.session_store.clear_sessions(user_id)
            if count:
                self.session_store.save()
            return count
