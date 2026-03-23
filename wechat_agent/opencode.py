import json
import os
import queue
import shutil
import subprocess
import threading
import time
from pathlib import Path

from .constants import DEFAULT_OPENCODE_TIMEOUT_MS
from .session_store import MultiSessionStore
from .util import ensure_parent


class OpenCodeRunner:
    def __init__(self, store_file):
        self.store_file = Path(store_file)
        ensure_parent(self.store_file)
        self._lock = threading.Lock()
        self.timeout_ms = self._get_timeout_ms()
        self.model = os.environ.get("OPENCODE_MODEL", "").strip()
        self.enable_thinking = os.environ.get("OPENCODE_THINKING", "").strip().lower() in {"1", "true", "yes", "on"}
        self.session_store = MultiSessionStore(self.store_file)

    def _get_timeout_ms(self):
        raw = os.environ.get("OPENCODE_TURN_TIMEOUT_MS", "").strip()
        if not raw:
            return DEFAULT_OPENCODE_TIMEOUT_MS
        try:
            value = int(raw)
            return value if value > 0 else DEFAULT_OPENCODE_TIMEOUT_MS
        except ValueError:
            return DEFAULT_OPENCODE_TIMEOUT_MS

    @staticmethod
    def _wrap_powershell_script(script_path):
        shell = shutil.which("pwsh") or shutil.which("powershell")
        if shell and Path(script_path).exists():
            return [shell, "-NoProfile", "-File", str(script_path)]
        return None

    def _resolve_command(self):
        override = os.environ.get("OPENCODE_BIN", "").strip()
        if override:
            if os.name == "nt" and override.lower().endswith(".ps1"):
                wrapped = self._wrap_powershell_script(override)
                if wrapped:
                    return wrapped
            return [override]

        if os.name == "nt":
            appdata = os.environ.get("APPDATA", "").strip()
            if appdata:
                wrapped = self._wrap_powershell_script(Path(appdata) / "npm" / "opencode.ps1")
                if wrapped:
                    return wrapped
            candidates = ["opencode.cmd", "opencode.exe", "opencode"]
        else:
            candidates = ["opencode"]

        for candidate in candidates:
            resolved = shutil.which(candidate)
            if resolved:
                return [resolved]

        return ["opencode"]

    def _build_args(self, session_id, prompt):
        args = self._resolve_command() + ["run", "--format", "json"]
        if self.enable_thinking:
            args.append("--thinking")
        if session_id:
            args.extend(["--session", session_id])
        if self.model:
            args.extend(["--model", self.model])
        args.extend(["--dir", str(Path.cwd()), prompt])
        return args

    @staticmethod
    def _reader_thread(pipe, output_queue, stream_name):
        buffer = b""
        try:
            while True:
                chunk = pipe.read1(4096) if hasattr(pipe, "read1") else pipe.read(4096)
                if not chunk:
                    break
                buffer += chunk
                while b"\n" in buffer:
                    raw_line, buffer = buffer.split(b"\n", 1)
                    line = raw_line.decode("utf-8", errors="replace").rstrip("\r")
                    output_queue.put((stream_name, line))
            if buffer:
                line = buffer.decode("utf-8", errors="replace").rstrip("\r")
                output_queue.put((stream_name, line))
        finally:
            output_queue.put((stream_name, None))

    @staticmethod
    def _event_part(event):
        part = event.get("part")
        if isinstance(part, dict):
            return part
        properties = event.get("properties")
        if isinstance(properties, dict):
            nested = properties.get("part")
            if isinstance(nested, dict):
                return nested
        return {}

    @staticmethod
    def _event_properties(event):
        properties = event.get("properties")
        return properties if isinstance(properties, dict) else {}

    @staticmethod
    def _merge_text_part(order, store, part_id, text, append=False):
        if not isinstance(text, str) or not text:
            return
        key = part_id if isinstance(part_id, str) and part_id else f"inline:{len(order)}"
        if key not in order:
            order.append(key)
        if append:
            store[key] = store.get(key, "") + text
        else:
            store[key] = text

    def _run_once(self, user_id, user_message, session_id=None):
        process = subprocess.Popen(
            self._build_args(session_id, user_message),
            cwd=Path.cwd(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            bufsize=0,
        )

        next_session_id = session_id
        text_order = []
        text_parts = {}
        errors = []
        stderr_lines = []
        deadline = time.monotonic() + (self.timeout_ms / 1000)
        output_queue = queue.Queue()

        assert process.stdout is not None
        assert process.stderr is not None
        threading.Thread(
            target=self._reader_thread,
            args=(process.stdout, output_queue, "stdout"),
            name="opencode-stdout-reader",
            daemon=True,
        ).start()
        threading.Thread(
            target=self._reader_thread,
            args=(process.stderr, output_queue, "stderr"),
            name="opencode-stderr-reader",
            daemon=True,
        ).start()

        closed_streams = set()

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                process.kill()
                raise subprocess.TimeoutExpired(process.args, self.timeout_ms / 1000)

            try:
                stream_name, line = output_queue.get(timeout=min(remaining, 1))
            except queue.Empty:
                if process.poll() is not None and closed_streams.issuperset({"stdout", "stderr"}):
                    break
                continue

            if line is None:
                closed_streams.add(stream_name)
                if process.poll() is not None and closed_streams.issuperset({"stdout", "stderr"}):
                    break
                continue

            if stream_name == "stderr":
                stripped_err = line.strip()
                if stripped_err:
                    stderr_lines.append(stripped_err)
                continue

            stripped = line.strip()
            if not stripped:
                continue
            try:
                event = json.loads(stripped)
            except json.JSONDecodeError:
                continue

            event_type = event.get("type")
            part = self._event_part(event)
            properties = self._event_properties(event)

            session_candidate = None
            if isinstance(event.get("sessionID"), str) and event.get("sessionID").strip():
                session_candidate = event.get("sessionID").strip()
            elif isinstance(part.get("sessionID"), str) and part.get("sessionID").strip():
                session_candidate = part.get("sessionID").strip()
            elif isinstance(properties.get("sessionID"), str) and properties.get("sessionID").strip():
                session_candidate = properties.get("sessionID").strip()
            if session_candidate:
                next_session_id = session_candidate

            if event_type == "step_start":
                continue
            elif event_type == "text":
                self._merge_text_part(text_order, text_parts, part.get("id"), part.get("text"))
            elif event_type == "message.part.updated":
                if part.get("type") == "text":
                    self._merge_text_part(text_order, text_parts, part.get("id"), part.get("text"))
            elif event_type == "message.part.delta":
                if properties.get("field") == "text":
                    self._merge_text_part(
                        text_order,
                        text_parts,
                        properties.get("partID"),
                        properties.get("delta"),
                        append=True,
                    )
            elif event_type == "message.updated":
                info = properties.get("info")
                if isinstance(info, dict):
                    for item in info.get("parts") or []:
                        if isinstance(item, dict) and item.get("type") == "text":
                            self._merge_text_part(text_order, text_parts, item.get("id"), item.get("text"))
            elif event_type == "error":
                errors.append(self._extract_error_message(event))

        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

        if next_session_id:
            with self._lock:
                self.session_store.set_current_engine_id(user_id, next_session_id)
                self.session_store.save()

        result_text = "".join(text_parts.get(item_id, "") for item_id in text_order).strip()
        if result_text:
            return result_text

        error_message = errors[-1] if errors else ""
        if not error_message and stderr_lines:
            error_message = stderr_lines[-1]

        raise RuntimeError(error_message or f"opencode 返回非零退出码: {process.returncode}")

    def run(self, user_id, user_message):
        with self._lock:
            session_id = self.session_store.get_current_engine_id(user_id, create_if_missing=True)
            self.session_store.save()
        try:
            return self._run_once(user_id, user_message, session_id=session_id)
        except subprocess.TimeoutExpired:
            seconds = max(1, self.timeout_ms // 1000)
            return f"❌ OpenCode 在 {seconds} 秒内没有返回结果，请稍后重试。"
        except FileNotFoundError:
            return "❌ 未找到 opencode CLI，请先安装并确保它在 PATH 中。"
        except Exception as first_error:
            if session_id:
                with self._lock:
                    self.session_store.clear_current_engine_id(user_id)
                    self.session_store.save()
                try:
                    return self._run_once(user_id, user_message, session_id=None)
                except subprocess.TimeoutExpired:
                    seconds = max(1, self.timeout_ms // 1000)
                    return f"❌ OpenCode 在 {seconds} 秒内没有返回结果，请稍后重试。"
                except FileNotFoundError:
                    return "❌ 未找到 opencode CLI，请先安装并确保它在 PATH 中。"
                except Exception as second_error:
                    return f"❌ OpenCode 执行失败：{second_error}"
            return f"❌ OpenCode 执行失败：{first_error}"

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

    @staticmethod
    def _extract_error_message(raw):
        err_obj = raw.get("error")
        if isinstance(err_obj, dict):
            data = err_obj.get("data")
            if isinstance(data, dict):
                msg = data.get("message")
                name = err_obj.get("name")
                if isinstance(msg, str) and msg:
                    if isinstance(name, str) and name:
                        return f"{name}: {msg}"
                    return msg
            msg = err_obj.get("message")
            if isinstance(msg, str) and msg:
                return msg
            name = err_obj.get("name")
            if isinstance(name, str) and name:
                return name
        if isinstance(err_obj, str) and err_obj:
            return err_obj
        part = raw.get("part")
        if isinstance(part, dict):
            for key in ("error", "message"):
                value = part.get(key)
                if isinstance(value, str) and value:
                    return value
        message = raw.get("message")
        if isinstance(message, str) and message:
            return message
        try:
            return json.dumps(raw, ensure_ascii=False)
        except Exception:
            return str(raw)
