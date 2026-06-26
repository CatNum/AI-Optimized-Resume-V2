import json
import re
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
    """按最近用户轮次裁剪聊天历史。

    messages（消息列表）包含 user/assistant 等对话消息；max_rounds（最大轮次）
    表示最多保留多少个用户发言轮次。返回值是裁剪后的消息列表。
    """
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
    """_set_by_path（内部函数 set by path）的函数说明。

    data（参数）、path（参数）、value（参数）用于向该函数传入运行所需的数据。

    该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
    keys = path.split(".")
    current: Any = data
    for key in keys[:-1]:
        if key not in current or not isinstance(current[key], dict):
            current[key] = {}
        current = current[key]
    current[keys[-1]] = value


class SessionStore:
    """SessionStore（会话存储）负责读写单个会话的数据。

    会话数据包括 messages.json（消息）、state.json（运行状态）和 artifacts.json（产物）。
    Agent 通过它保存 prior_results、gates、pipeline 状态和 Worker 产物。
    """

    def __init__(self) -> None:
        """__init__（初始化对象）的函数说明。

        该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
        self._data_dir = Path(settings.data_dir)
        self._sessions_dir = self._data_dir / "sessions"
        self._max_tokens = settings.chat_history_max_tokens

    def _session_dir(self, session_id: str) -> Path:
        """_session_dir（内部函数 session dir）的函数说明。

        session_id（参数）用于向该函数传入运行所需的数据。

        该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
        return self._sessions_dir / session_id

    def _messages_path(self, session_id: str) -> Path:
        """_messages_path（内部函数 messages path）的函数说明。

        session_id（参数）用于向该函数传入运行所需的数据。

        该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
        return self._session_dir(session_id) / "messages.json"

    def _state_path(self, session_id: str) -> Path:
        """_state_path（内部函数 state path）的函数说明。

        session_id（参数）用于向该函数传入运行所需的数据。

        该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
        return self._session_dir(session_id) / "state.json"

    def _artifacts_path(self, session_id: str) -> Path:
        """_artifacts_path（内部函数 artifacts path）的函数说明。

        session_id（参数）用于向该函数传入运行所需的数据。

        该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
        return self._session_dir(session_id) / "artifacts.json"

    def _index_path(self) -> Path:
        """_index_path（内部函数 index path）的函数说明。

        该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
        return self._sessions_dir / "_index.json"

    def load_index(self) -> dict[str, Any]:
        """load_index（load index）的函数说明。

        返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
        with _lock:
            return self._read_index_unlocked()

    @staticmethod
    def is_valid_session_id(session_id: str) -> bool:
        """is_valid_session_id（is valid session id）的函数说明。

        session_id（参数）用于向该函数传入运行所需的数据。

        返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
        return bool(SESSION_ID_PATTERN.match(session_id))

    @staticmethod
    def is_expired(session_state: dict[str, Any]) -> bool:
        """I2 闲置过期已移除；会话不因闲置时间失效。"""
        _ = session_state
        return False

    def session_exists(self, session_id: str) -> bool:
        """session_exists（session exists）的函数说明。

        session_id（参数）用于向该函数传入运行所需的数据。

        返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
        return self._session_dir(session_id).exists()

    def load_messages_full(self, session_id: str) -> list[dict[str, str]]:
        """load_messages_full（load messages full）的函数说明。

        session_id（参数）用于向该函数传入运行所需的数据。

        返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
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
        """patch_index（patch index）的函数说明。

        session_id（参数）、title（参数）、title_source（参数）、archived（参数）用于向该函数传入运行所需的数据。

        返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
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
        """touch_index（touch index）的函数说明。

        session_id（参数）用于向该函数传入运行所需的数据。

        返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
        with _lock:
            self._touch_index_unlocked(session_id)

    def rebuild_index(self) -> None:
        """rebuild_index（rebuild index）的函数说明。

        返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
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
        """create_session（create session）的函数说明。

        返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
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
        """append_message（append message）的函数说明。

        session_id（参数）、role（参数）、content（参数）用于向该函数传入运行所需的数据。

        返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
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
        """load_chat_history（load chat history）的函数说明。

        session_id（参数）用于向该函数传入运行所需的数据。

        返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
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
        """读取会话状态。

        session_id（会话标识）定位 sessions 目录下的 state.json。
        返回值是完整 session_state（会话状态）。
        """
        with _lock:
            return self._read_state_unlocked(session_id)

    def update_state(self, session_id: str, patch: dict[str, Any]) -> None:
        """增量更新会话状态。

        session_id（会话标识）定位 state.json；patch（补丁）会直接 update 到状态字典。
        如果 list_type 变化，会同步触碰会话索引。
        """
        with _lock:
            state = self._read_state_unlocked(session_id)
            old_list_type = state.get("list_type")
            state.update(patch)
            self._write_state_unlocked(session_id, state)
            if "list_type" in patch and patch.get("list_type") != old_list_type:
                self._touch_index_unlocked(session_id)

    def get_artifacts(self, session_id: str) -> dict[str, Any]:
        """读取会话产物。

        session_id（会话标识）定位 artifacts.json。
        返回值包含 exploration、market、strategy、resume_outputs 等产物字段。
        """
        with _lock:
            return self._read_artifacts_unlocked(session_id)

    def patch_artifacts(self, session_id: str, patches: list[dict[str, Any]]) -> None:
        """按路径补丁更新会话产物。

        session_id（会话标识）定位 artifacts.json；patches（补丁列表）每项包含
        path、value、op。当前只处理 op=set，用于写入 Worker 结构化产物。
        """
        with _lock:
            artifacts = self._read_artifacts_unlocked(session_id)
            for patch in patches:
                if patch.get("op") != "set":
                    continue
                _set_by_path(artifacts, patch["path"], patch.get("value"))
            self._write_artifacts_unlocked(session_id, artifacts)

    def delete_session(self, session_id: str) -> None:
        """delete_session（delete session）的函数说明。

        session_id（参数）用于向该函数传入运行所需的数据。

        返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
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
        """reset_session（reset session）的函数说明。

        session_id（参数）用于向该函数传入运行所需的数据。

        返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
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
        """_estimate_tokens（内部函数 estimate tokens）的函数说明。

        messages（参数）用于向该函数传入运行所需的数据。

        该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
        return sum(len(m.get("content", "")) // 4 + 1 for m in messages)

    def _read_messages_unlocked(self, session_id: str) -> list[dict[str, str]]:
        """_read_messages_unlocked（内部函数 read messages unlocked）的函数说明。

        session_id（参数）用于向该函数传入运行所需的数据。

        该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
        path = self._messages_path(session_id)
        if not path.exists():
            return []
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        return data.get("messages", [])

    def _write_messages_unlocked(
        self, session_id: str, messages: list[dict[str, str]]
    ) -> None:
        """_write_messages_unlocked（内部函数 write messages unlocked）的函数说明。

        session_id（参数）、messages（参数）用于向该函数传入运行所需的数据。

        该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
        path = self._messages_path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump({"messages": messages}, f, ensure_ascii=False, indent=2)

    def _read_state_unlocked(self, session_id: str) -> dict[str, Any]:
        """_read_state_unlocked（内部函数 read state unlocked）的函数说明。

        session_id（参数）用于向该函数传入运行所需的数据。

        该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
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
        """_read_artifacts_unlocked（内部函数 read artifacts unlocked）的函数说明。

        session_id（参数）用于向该函数传入运行所需的数据。

        该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
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
        """_write_state_unlocked（内部函数 write state unlocked）的函数说明。

        session_id（参数）、state（参数）用于向该函数传入运行所需的数据。

        该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
        path = self._state_path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

    def _write_artifacts_unlocked(self, session_id: str, artifacts: dict[str, Any]) -> None:
        """_write_artifacts_unlocked（内部函数 write artifacts unlocked）的函数说明。

        session_id（参数）、artifacts（参数）用于向该函数传入运行所需的数据。

        该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
        path = self._artifacts_path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {**_DEFAULT_ARTIFACTS, **artifacts, "session_id": session_id}
        with path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    def _read_index_unlocked(self) -> dict[str, Any]:
        """_read_index_unlocked（内部函数 read index unlocked）的函数说明。

        该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
        path = self._index_path()
        if not path.exists():
            return {"version": _INDEX_VERSION, "sessions": []}
        with path.open(encoding="utf-8") as f:
            return json.load(f)

    def _write_index_unlocked(self, index: dict[str, Any]) -> None:
        """_write_index_unlocked（内部函数 write index unlocked）的函数说明。

        index（参数）用于向该函数传入运行所需的数据。

        该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
        path = self._index_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)

    def _apply_first_user_fallback_unlocked(
        self, session_id: str, messages: list[dict[str, str]]
    ) -> None:
        """_apply_first_user_fallback_unlocked（内部函数 apply first user fallback unlocked）的函数说明。

        session_id（参数）、messages（参数）用于向该函数传入运行所需的数据。

        该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
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
        """_compute_preview（内部函数 compute preview）的函数说明。

        messages（参数）用于向该函数传入运行所需的数据。

        该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
        for message in reversed(messages):
            if message.get("role") == "user":
                return message.get("content", "")[:40]
        return ""

    def _touch_index_unlocked(self, session_id: str) -> None:
        """_touch_index_unlocked（内部函数 touch index unlocked）的函数说明。

        session_id（参数）用于向该函数传入运行所需的数据。

        该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
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
