import json
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from career_os.config import settings

_lock = threading.Lock()

_DEFAULT_STATE: dict[str, Any] = {
    "prior_results": {},
    "explore_closure": None,
    "messages_meta": {},
    "gates": {},
}


class SessionStore:
    def __init__(self) -> None:
        self._data_dir = Path(settings.data_dir)
        self._sessions_dir = self._data_dir / "sessions"
        self._max_messages = settings.chat_history_max_messages
        self._max_tokens = settings.chat_history_max_tokens

    def _session_dir(self, session_id: str) -> Path:
        return self._sessions_dir / session_id

    def _messages_path(self, session_id: str) -> Path:
        return self._session_dir(session_id) / "messages.json"

    def _state_path(self, session_id: str) -> Path:
        return self._session_dir(session_id) / "state.json"

    def create_session(self) -> str:
        session_id = f"sess_{uuid.uuid4().hex}"
        with _lock:
            session_dir = self._session_dir(session_id)
            session_dir.mkdir(parents=True, exist_ok=True)
            now = datetime.now(UTC).isoformat()
            state = {
                **_DEFAULT_STATE,
                "session_id": session_id,
                "list_id": None,
                "last_activity_at": now,
            }
            self._write_state_unlocked(session_id, state)
            self._write_messages_unlocked(session_id, [])
        return session_id

    def append_message(self, session_id: str, role: str, content: str) -> None:
        with _lock:
            messages = self._read_messages_unlocked(session_id)
            messages.append({"role": role, "content": content})
            self._write_messages_unlocked(session_id, messages)
            state = self._read_state_unlocked(session_id)
            state["last_activity_at"] = datetime.now(UTC).isoformat()
            self._write_state_unlocked(session_id, state)

    def load_messages_for_coordinator(
        self, session_id: str
    ) -> tuple[list[dict[str, str]], dict[str, Any]]:
        with _lock:
            messages = self._read_messages_unlocked(session_id)
            loaded, meta = self._apply_m1_trim(messages)
            state = self._read_state_unlocked(session_id)
            state["messages_meta"] = meta
            self._write_state_unlocked(session_id, state)
            return loaded, meta

    def get_state(self, session_id: str) -> dict[str, Any]:
        with _lock:
            return self._read_state_unlocked(session_id)

    def update_state(self, session_id: str, patch: dict[str, Any]) -> None:
        with _lock:
            state = self._read_state_unlocked(session_id)
            state.update(patch)
            self._write_state_unlocked(session_id, state)

    def reset_session(self, session_id: str) -> None:
        with _lock:
            session_dir = self._session_dir(session_id)
            if session_dir.exists():
                for path in session_dir.iterdir():
                    if path.is_file():
                        path.unlink()
            now = datetime.now(UTC).isoformat()
            state = {
                **_DEFAULT_STATE,
                "session_id": session_id,
                "list_id": None,
                "last_activity_at": now,
            }
            session_dir.mkdir(parents=True, exist_ok=True)
            self._write_state_unlocked(session_id, state)
            self._write_messages_unlocked(session_id, [])

    def _apply_m1_trim(
        self, messages: list[dict[str, str]]
    ) -> tuple[list[dict[str, str]], dict[str, Any]]:
        total_count = len(messages)
        if total_count == 0:
            meta = {
                "total_count": 0,
                "loaded_count": 0,
                "trimmed": False,
                "usage_ratio": 0.0,
            }
            return [], meta

        first_user = next((m for m in messages if m["role"] == "user"), None)
        loaded = self._trim_by_count(messages, first_user)
        loaded = self._trim_by_tokens(loaded, first_user)

        loaded_count = len(loaded)
        trimmed = loaded_count < total_count
        denominator = min(total_count, self._max_messages)
        usage_ratio = loaded_count / denominator if denominator > 0 else 0.0

        meta = {
            "total_count": total_count,
            "loaded_count": loaded_count,
            "trimmed": trimmed,
            "usage_ratio": round(usage_ratio, 4),
        }
        return loaded, meta

    def _trim_by_count(
        self, messages: list[dict[str, str]], first_user: dict[str, str] | None
    ) -> list[dict[str, str]]:
        if len(messages) <= self._max_messages:
            return list(messages)

        tail_count = self._max_messages - (1 if first_user else 0)
        tail = messages[-tail_count:] if tail_count > 0 else []

        if first_user is None:
            return messages[-self._max_messages :]

        if first_user in tail:
            return messages[-self._max_messages :]

        return [first_user, *tail]

    def _trim_by_tokens(
        self, messages: list[dict[str, str]], first_user: dict[str, str] | None
    ) -> list[dict[str, str]]:
        if self._estimate_tokens(messages) <= self._max_tokens:
            return messages

        result = list(messages)
        while len(result) > 1 and self._estimate_tokens(result) > self._max_tokens:
            if first_user and result[0] is first_user:
                if len(result) > 2:
                    result.pop(1)
                else:
                    break
            else:
                result.pop(0)
        return result

    @staticmethod
    def _estimate_tokens(messages: list[dict[str, str]]) -> int:
        return sum(len(m.get("content", "")) // 4 + 1 for m in messages)

    def _read_messages_unlocked(self, session_id: str) -> list[dict[str, str]]:
        path = self._messages_path(session_id)
        if not path.exists():
            return []
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        return data.get("messages", [])

    def _write_messages_unlocked(
        self, session_id: str, messages: list[dict[str, str]]
    ) -> None:
        path = self._messages_path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump({"messages": messages}, f, ensure_ascii=False, indent=2)

    def _read_state_unlocked(self, session_id: str) -> dict[str, Any]:
        path = self._state_path(session_id)
        if not path.exists():
            return {
                **_DEFAULT_STATE,
                "session_id": session_id,
                "list_id": None,
                "last_activity_at": None,
            }
        with path.open(encoding="utf-8") as f:
            return json.load(f)

    def _write_state_unlocked(self, session_id: str, state: dict[str, Any]) -> None:
        path = self._state_path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
