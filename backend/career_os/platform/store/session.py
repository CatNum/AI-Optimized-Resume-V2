import json
import re
import shutil
import threading
import uuid
from datetime import UTC, datetime, timedelta
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
_DEFAULT_ARTIFACTS: dict[str, Any] = {
    "version": 1,
    "session_id": None,
    "exploration": {},
    "market": {},
    "opportunity": {},
    "strategy": {},
    "resume_outputs": [],
}

_INDEX_VERSION = 1
_DEFAULT_TITLE = "未命名会话"
SESSION_ID_PATTERN = re.compile(r"^sess_[0-9a-f]{32}$")


def slice_chat_rounds(
    messages: list[dict[str, str]],
    *,
    max_rounds: int,
) -> list[dict[str, str]]:
    if max_rounds < 1 or not messages:
        return []
    round_starts: list[int] = []
    for i, m in enumerate(messages):
        if m.get("role") == "user":
            round_starts.append(i)
    if not round_starts:
        return list(messages)
    keep_from = (
        round_starts[-max_rounds] if len(round_starts) >= max_rounds else round_starts[0]
    )
    return list(messages[keep_from:])


def slice_synthesize_chat_history(
    messages: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Last dialogue beat: prior assistant (if any) + current user message."""
    if not messages:
        return []
    if messages[-1].get("role") != "user":
        return list(messages[-1:])
    if len(messages) == 1:
        return list(messages)
    prev = messages[-2]
    if prev.get("role") == "assistant":
        return [prev, messages[-1]]
    return [messages[-1]]


def _set_by_path(data: dict[str, Any], path: str, value: Any) -> None:
    keys = path.split(".")
    current: Any = data
    for key in keys[:-1]:
        if key not in current or not isinstance(current[key], dict):
            current[key] = {}
        current = current[key]
    current[keys[-1]] = value


class SessionStore:
    def __init__(self) -> None:
        self._data_dir = Path(settings.data_dir)
        self._sessions_dir = self._data_dir / "sessions"
        self._max_tokens = settings.chat_history_max_tokens

    def _session_dir(self, session_id: str) -> Path:
        return self._sessions_dir / session_id

    def _messages_path(self, session_id: str) -> Path:
        return self._session_dir(session_id) / "messages.json"

    def _state_path(self, session_id: str) -> Path:
        return self._session_dir(session_id) / "state.json"

    def _artifacts_path(self, session_id: str) -> Path:
        return self._session_dir(session_id) / "artifacts.json"

    def _index_path(self) -> Path:
        return self._sessions_dir / "_index.json"

    def load_index(self) -> dict[str, Any]:
        with _lock:
            return self._read_index_unlocked()

    @staticmethod
    def is_valid_session_id(session_id: str) -> bool:
        return bool(SESSION_ID_PATTERN.match(session_id))

    @staticmethod
    def is_expired(session_state: dict[str, Any]) -> bool:
        from career_os.config import settings

        last_activity = session_state.get("last_activity_at")
        if not last_activity:
            return False
        last_dt = datetime.fromisoformat(last_activity.replace("Z", "+00:00"))
        return datetime.now(UTC) - last_dt > timedelta(seconds=settings.session_idle_ttl)

    def session_exists(self, session_id: str) -> bool:
        return self._session_dir(session_id).exists()

    def load_messages_full(self, session_id: str) -> list[dict[str, str]]:
        with _lock:
            return self._read_messages_unlocked(session_id)

    def patch_index(
        self,
        session_id: str,
        *,
        title: str | None = None,
        title_source: str | None = None,
        archived: bool | None = None,
    ) -> None:
        with _lock:
            index = self._read_index_unlocked()
            row = next(
                (r for r in index.get("sessions", []) if r.get("session_id") == session_id),
                None,
            )
            if row is None:
                raise KeyError(session_id)
            if title is not None:
                row["title"] = title
                row["title_source"] = title_source if title_source is not None else "user"
            if archived is not None:
                row["archived"] = archived
            index["version"] = _INDEX_VERSION
            self._write_index_unlocked(index)

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
            self._write_artifacts_unlocked(
                session_id, {**_DEFAULT_ARTIFACTS, "session_id": session_id}
            )
            self._touch_index_unlocked(session_id)
        return session_id

    def append_message(self, session_id: str, role: str, content: str) -> None:
        schedule_title = False
        with _lock:
            messages = self._read_messages_unlocked(session_id)
            messages.append({"role": role, "content": content})
            self._write_messages_unlocked(session_id, messages)
            state = self._read_state_unlocked(session_id)
            state["last_activity_at"] = datetime.now(UTC).isoformat()
            self._write_state_unlocked(session_id, state)
            self._touch_index_unlocked(session_id)
            if role == "user":
                user_count = sum(1 for m in messages if m.get("role") == "user")
                if user_count == 1:
                    self._apply_first_user_fallback_unlocked(session_id, messages)
                    schedule_title = True
        if schedule_title:
            from career_os.platform.store.session_title import schedule_maybe_generate_title

            schedule_maybe_generate_title(session_id)

    def load_chat_history(
        self, session_id: str
    ) -> tuple[list[dict[str, str]], dict[str, Any]]:
        with _lock:
            messages = self._read_messages_unlocked(session_id)
            token_count = self._estimate_tokens(messages)
            max_tokens = self._max_tokens
            over_limit = token_count > max_tokens if max_tokens > 0 else False
            meta = {
                "total_count": len(messages),
                "loaded_count": len(messages),
                "token_count": token_count,
                "max_tokens": max_tokens,
                "usage_ratio": round(token_count / max_tokens, 4) if max_tokens else 0.0,
                "over_limit": over_limit,
            }
            state = self._read_state_unlocked(session_id)
            state["messages_meta"] = meta
            self._write_state_unlocked(session_id, state)
            return messages, meta

    def get_state(self, session_id: str) -> dict[str, Any]:
        with _lock:
            return self._read_state_unlocked(session_id)

    def update_state(self, session_id: str, patch: dict[str, Any]) -> None:
        with _lock:
            state = self._read_state_unlocked(session_id)
            old_list_type = state.get("list_type")
            state.update(patch)
            self._write_state_unlocked(session_id, state)
            if "list_type" in patch and patch.get("list_type") != old_list_type:
                self._touch_index_unlocked(session_id)

    def get_artifacts(self, session_id: str) -> dict[str, Any]:
        with _lock:
            return self._read_artifacts_unlocked(session_id)

    def patch_artifacts(self, session_id: str, patches: list[dict[str, Any]]) -> None:
        with _lock:
            artifacts = self._read_artifacts_unlocked(session_id)
            for patch in patches:
                if patch.get("op") != "set":
                    continue
                _set_by_path(artifacts, patch["path"], patch.get("value"))
            self._write_artifacts_unlocked(session_id, artifacts)

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
            self._write_artifacts_unlocked(
                session_id, {**_DEFAULT_ARTIFACTS, "session_id": session_id}
            )

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

    def _read_artifacts_unlocked(self, session_id: str) -> dict[str, Any]:
        path = self._artifacts_path(session_id)
        if not path.exists():
            return {**_DEFAULT_ARTIFACTS, "session_id": session_id}
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {**_DEFAULT_ARTIFACTS, "session_id": session_id}
        out = {**_DEFAULT_ARTIFACTS, **data}
        out["session_id"] = session_id
        return out

    def _write_state_unlocked(self, session_id: str, state: dict[str, Any]) -> None:
        path = self._state_path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

    def _write_artifacts_unlocked(self, session_id: str, artifacts: dict[str, Any]) -> None:
        path = self._artifacts_path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {**_DEFAULT_ARTIFACTS, **artifacts, "session_id": session_id}
        with path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

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

    def _apply_first_user_fallback_unlocked(
        self, session_id: str, messages: list[dict[str, str]]
    ) -> None:
        index = self._read_index_unlocked()
        row = next(
            (r for r in index.get("sessions", []) if r.get("session_id") == session_id),
            None,
        )
        if row is None or row.get("title_source") == "user":
            return
        first_user = next((m for m in messages if m.get("role") == "user"), None)
        if first_user is None:
            return
        content = (first_user.get("content") or "").strip()
        row["title"] = content[:20] if content else _DEFAULT_TITLE
        row["title_source"] = "fallback"
        index["version"] = _INDEX_VERSION
        self._write_index_unlocked(index)

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
