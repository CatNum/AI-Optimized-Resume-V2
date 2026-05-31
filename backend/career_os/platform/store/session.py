import json
import shutil
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from career_os.config import settings
from career_os.platform.store.task import TaskStore

_lock = threading.Lock()

_DEFAULT_STATE: dict[str, Any] = {
    "prior_results": {},
    "explore_closure": None,
    "messages_meta": {},
    "gates": {},
}

_INDEX_VERSION = 1
_DEFAULT_TITLE = "未命名会话"


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

    def _index_path(self) -> Path:
        return self._sessions_dir / "_index.json"

    def load_index(self) -> dict[str, Any]:
        with _lock:
            return self._read_index_unlocked()

    def touch_index(self, session_id: str) -> None:
        with _lock:
            self._touch_index_unlocked(session_id)

    def rebuild_index(self) -> None:
        with _lock:
            session_ids_on_disk: set[str] = set()
            if self._sessions_dir.exists():
                for item in self._sessions_dir.iterdir():
                    if item.is_dir() and item.name.startswith("sess_"):
                        session_ids_on_disk.add(item.name)

            for session_id in sorted(session_ids_on_disk):
                self._touch_index_unlocked(session_id)

            index = self._read_index_unlocked()
            index["sessions"] = [
                row
                for row in index.get("sessions", [])
                if row.get("session_id") in session_ids_on_disk
            ]
            index["version"] = _INDEX_VERSION
            self._write_index_unlocked(index)

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
            self._touch_index_unlocked(session_id)
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

    def delete_session(self, session_id: str) -> None:
        with _lock:
            session_dir = self._session_dir(session_id)
            if session_dir.exists():
                shutil.rmtree(session_dir)
            index = self._read_index_unlocked()
            index["sessions"] = [
                row
                for row in index.get("sessions", [])
                if row.get("session_id") != session_id
            ]
            index["version"] = _INDEX_VERSION
            self._write_index_unlocked(index)
        TaskStore().delete_lists_for_session(session_id)

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
            return [], self._build_messages_meta([], [], trimmed=False)

        first_user = next((m for m in messages if m["role"] == "user"), None)
        loaded = self._trim_by_count(messages, first_user)
        loaded = self._trim_by_tokens(loaded, first_user)

        loaded_count = len(loaded)
        trimmed = loaded_count < total_count
        meta = self._build_messages_meta(messages, loaded, trimmed=trimmed)
        return loaded, meta

    def _build_messages_meta(
        self,
        all_messages: list[dict[str, str]],
        loaded_messages: list[dict[str, str]],
        *,
        trimmed: bool,
    ) -> dict[str, Any]:
        total_count = len(all_messages)
        loaded_count = len(loaded_messages)
        token_count = self._estimate_tokens(all_messages)
        token_ratio = token_count / self._max_tokens if self._max_tokens > 0 else 0.0
        return {
            "total_count": total_count,
            "loaded_count": loaded_count,
            "trimmed": trimmed,
            "message_count": total_count,
            "max_messages": self._max_messages,
            "token_count": token_count,
            "max_tokens": self._max_tokens,
            "usage_ratio": round(token_ratio, 4),
        }

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

    def _read_index_unlocked(self) -> dict[str, Any]:
        path = self._index_path()
        if not path.exists():
            return {"version": _INDEX_VERSION, "sessions": []}
        with path.open(encoding="utf-8") as f:
            return json.load(f)

    def _write_index_unlocked(self, index: dict[str, Any]) -> None:
        path = self._index_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _compute_preview(messages: list[dict[str, str]]) -> str:
        for message in reversed(messages):
            if message.get("role") == "user":
                return message.get("content", "")[:40]
        return ""

    def _touch_index_unlocked(self, session_id: str) -> None:
        index = self._read_index_unlocked()
        sessions: list[dict[str, Any]] = index.setdefault("sessions", [])
        existing = next(
            (row for row in sessions if row.get("session_id") == session_id),
            None,
        )

        messages = self._read_messages_unlocked(session_id)
        state = self._read_state_unlocked(session_id)
        last_activity_at = state.get("last_activity_at")
        if last_activity_at is None:
            last_activity_at = datetime.now(UTC).isoformat()

        preview = self._compute_preview(messages)
        message_count = len(messages)
        list_type = state.get("list_type")

        if existing is None:
            sessions.append(
                {
                    "session_id": session_id,
                    "title": _DEFAULT_TITLE,
                    "title_source": "fallback",
                    "preview": preview,
                    "created_at": last_activity_at,
                    "last_activity_at": last_activity_at,
                    "message_count": message_count,
                    "list_type": list_type,
                    "archived": False,
                }
            )
        else:
            existing["preview"] = preview
            existing["message_count"] = message_count
            existing["list_type"] = list_type
            existing["last_activity_at"] = last_activity_at

        index["version"] = _INDEX_VERSION
        self._write_index_unlocked(index)
