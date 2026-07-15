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
    "message_idempotency_keys": [],
}
_DEFAULT_ARTIFACTS: dict[str, Any] = {
    "version": 1,
    "session_id": None,
    "exploration": {},
    "market": {
        "schema_version": 1,
        "active_plan_id": None,
        "active_research_id": None,
        "last_research_id": None,
        "active_retry_id": None,
        "last_retry_id": None,
        "result_ref": None,
        "reuse_ref": None,
        "market_result_confirmed": False,
        "confirmed_result_ref": None,
        "legacy_unverified": False,
    },
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
    """按最近用户轮次裁剪聊天历史。"""
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
    """最后一段对话：上一条 assistant 消息（如果存在）加当前 user 消息。"""
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
    """设置by path。"""
    keys = path.split(".")
    current: Any = data
    for key in keys[:-1]:
        if key not in current or not isinstance(current[key], dict):
            current[key] = {}
        current = current[key]
    current[keys[-1]] = value


def _default_market_artifact() -> dict[str, Any]:
    """构造市场阶段方案、运行、结果引用和确认状态的默认生命周期信封。"""
    return dict(_DEFAULT_ARTIFACTS["market"])


def _normalize_market_artifact(raw: Any) -> dict[str, Any]:
    """识别旧市场产物并返回不可向下游传播的版本化生命周期信封。"""
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        return {**_default_market_artifact(), "legacy_unverified": True}
    return {**_default_market_artifact(), **raw, "schema_version": 1}


class SessionStore:
    """
    SessionStore（会话存储）负责读写单个会话的数据。
    """

    def __init__(self) -> None:
        """初始化对象。"""
        self._data_dir = Path(settings.data_dir)
        self._sessions_dir = self._data_dir / "sessions"
        self._max_tokens = settings.chat_history_max_tokens

    def _session_dir(self, session_id: str) -> Path:
        """处理session dir。"""
        return self._sessions_dir / session_id

    def _messages_path(self, session_id: str) -> Path:
        """处理messages path。"""
        return self._session_dir(session_id) / "messages.json"

    def _state_path(self, session_id: str) -> Path:
        """处理state path。"""
        return self._session_dir(session_id) / "state.json"

    def _artifacts_path(self, session_id: str) -> Path:
        """处理artifacts path。"""
        return self._session_dir(session_id) / "artifacts.json"

    def _index_path(self) -> Path:
        """处理index path。"""
        return self._sessions_dir / "_index.json"

    def load_index(self) -> dict[str, Any]:
        """加载index。"""
        with _lock:
            return self._read_index_unlocked()

    @staticmethod
    def is_valid_session_id(session_id: str) -> bool:
        """判断valid session id。"""
        return bool(SESSION_ID_PATTERN.match(session_id))

    @staticmethod
    def is_expired(session_state: dict[str, Any]) -> bool:
        """I2 闲置过期已移除；会话不因闲置时间失效。"""
        _ = session_state
        return False

    def session_exists(self, session_id: str) -> bool:
        """处理session exists。"""
        return self._session_dir(session_id).exists()

    def load_messages_full(self, session_id: str) -> list[dict[str, str]]:
        """加载messages full。"""
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
        """补丁更新index。"""
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
        """刷新index。"""
        with _lock:
            self._touch_index_unlocked(session_id)

    def rebuild_index(self) -> None:
        """处理rebuild index。"""
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
        """创建session。"""
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

    def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        *,
        idempotency_key: str | None = None,
    ) -> bool:
        """追加普通聊天消息；提供幂等键时同一市场报告最多写入一次。"""
        schedule_title = False
        with _lock:
            messages = self._read_messages_unlocked(session_id)
            state = self._read_state_unlocked(session_id)
            keys = list(state.get("message_idempotency_keys") or [])
            if idempotency_key is not None and (
                idempotency_key in keys
                or any(
                    message.get("role") == role and message.get("content") == content
                    for message in messages
                )
            ):
                if idempotency_key not in keys:
                    keys.append(idempotency_key)
                    state["message_idempotency_keys"] = keys
                    self._write_state_unlocked(session_id, state)
                return False
            messages.append({"role": role, "content": content})
            self._write_messages_unlocked(session_id, messages)
            state["last_activity_at"] = datetime.now(UTC).isoformat()
            if idempotency_key is not None:
                state["message_idempotency_keys"] = [*keys, idempotency_key]
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
        return True

    def load_chat_history(
        self, session_id: str
    ) -> tuple[list[dict[str, str]], dict[str, Any]]:
        """加载chat history。"""
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
        """读取会话状态。"""
        with _lock:
            return self._read_state_unlocked(session_id)

    def update_state(self, session_id: str, patch: dict[str, Any]) -> None:
        """增量更新会话状态。"""
        with _lock:
            state = self._read_state_unlocked(session_id)
            old_list_type = state.get("list_type")
            state.update(patch)
            self._write_state_unlocked(session_id, state)
            if "list_type" in patch and patch.get("list_type") != old_list_type:
                self._touch_index_unlocked(session_id)

    def get_artifacts(self, session_id: str) -> dict[str, Any]:
        """读取会话产物。"""
        with _lock:
            return self._read_artifacts_unlocked(session_id)

    def patch_artifacts(self, session_id: str, patches: list[dict[str, Any]]) -> None:
        """按路径补丁更新会话产物。"""
        with _lock:
            artifacts = self._read_artifacts_unlocked(session_id)
            for patch in patches:
                if patch.get("op") != "set":
                    continue
                _set_by_path(artifacts, patch["path"], patch.get("value"))
                if patch["path"] == "market.result_ref" and patch.get("value") is not None:
                    _set_by_path(artifacts, "market.reuse_ref", None)
                    _set_by_path(artifacts, "market.market_result_confirmed", False)
                    _set_by_path(artifacts, "market.confirmed_result_ref", None)
                if patch["path"] == "market.reuse_ref" and patch.get("value") is not None:
                    _set_by_path(artifacts, "market.result_ref", None)
                    _set_by_path(artifacts, "market.market_result_confirmed", False)
                    _set_by_path(artifacts, "market.confirmed_result_ref", None)
            artifacts["market"] = _normalize_market_artifact(artifacts.get("market"))
            self._write_artifacts_unlocked(session_id, artifacts)

    def bind_market_result_for_confirmation(
        self,
        session_id: str,
        result_ref: dict[str, Any],
    ) -> None:
        """原子更新 Session 内市场结果引用、清空复用/确认并登记待确认闸门。"""
        research_id = result_ref.get("research_id")
        result_version = result_ref.get("result_version")
        if not isinstance(research_id, str) or not re.fullmatch(
            r"research_[0-9a-f]+", research_id
        ):
            raise ValueError("invalid market result research_id")
        if not isinstance(result_version, int) or result_version < 1:
            raise ValueError("invalid market result version")
        with _lock:
            artifacts = self._read_artifacts_unlocked(session_id)
            market = _normalize_market_artifact(artifacts.get("market"))
            market.update(
                {
                    "result_ref": dict(result_ref),
                    "reuse_ref": None,
                    "market_result_confirmed": False,
                    "confirmed_result_ref": None,
                }
            )
            artifacts["market"] = market
            self._write_artifacts_unlocked(session_id, artifacts)

            state = self._read_state_unlocked(session_id)
            gates = dict(state.get("gates") or {})
            gates["pending"] = {
                "name": "market_result_confirmation",
                "prompt": "市场调研结果已生成，是否确认使用该结果并继续下一步？",
                "research_id": research_id,
                "result_version": result_version,
            }
            state["gates"] = gates
            self._write_state_unlocked(session_id, state)

    def confirm_market_result_reference(
        self,
        session_id: str,
        expected_ref: dict[str, Any],
    ) -> dict[str, Any]:
        """原子确认当前正式市场结果引用并清除唯一的市场结果确认闸门。"""
        with _lock:
            artifacts = self._read_artifacts_unlocked(session_id)
            market = _normalize_market_artifact(artifacts.get("market"))
            result_ref = market.get("result_ref")
            reuse_ref = market.get("reuse_ref")
            if result_ref is not None and reuse_ref is not None:
                raise ValueError("conflicting market result references")
            current_ref = result_ref if result_ref is not None else reuse_ref
            if current_ref != expected_ref:
                raise ValueError("market result reference changed")
            market["market_result_confirmed"] = True
            market["confirmed_result_ref"] = dict(expected_ref)
            artifacts["market"] = market
            self._write_artifacts_unlocked(session_id, artifacts)

            state = self._read_state_unlocked(session_id)
            gates = dict(state.get("gates") or {})
            pending = gates.get("pending")
            if isinstance(pending, dict) and pending.get("name") == "market_result_confirmation":
                gates["pending"] = None
            flags = dict(gates.get("flags") or {})
            flags["market_result_confirmed"] = True
            gates["flags"] = flags
            state["gates"] = gates
            state["pipeline_phase"] = "jd_analysis"
            self._write_state_unlocked(session_id, state)
            return state

    def bind_market_reuse_for_confirmation(
        self,
        session_id: str,
        reuse_ref: dict[str, Any],
    ) -> None:
        """原子绑定用户选择的单方向复用引用，并要求再次确认后才能进入下游。"""
        with _lock:
            artifacts = self._read_artifacts_unlocked(session_id)
            market = _normalize_market_artifact(artifacts.get("market"))
            market.update(
                {
                    "result_ref": None,
                    "reuse_ref": dict(reuse_ref),
                    "market_result_confirmed": False,
                    "confirmed_result_ref": None,
                }
            )
            artifacts["market"] = market
            self._write_artifacts_unlocked(session_id, artifacts)
            state = self._read_state_unlocked(session_id)
            gates = dict(state.get("gates") or {})
            gates["pending"] = {
                "name": "market_result_confirmation",
                "prompt": "已选择复用一个未过期市场方向，是否确认使用并继续下一步？",
                "research_id": reuse_ref.get("research_id"),
                "result_version": reuse_ref.get("result_version"),
            }
            state["gates"] = gates
            self._write_state_unlocked(session_id, state)

    def sessions_referencing_market_result(self, research_id: str) -> list[str]:
        """列出 result_ref（新结果引用）或 reuse_ref（复用引用）指向该调研的 Session。"""
        with _lock:
            index = self._read_index_unlocked()
            session_ids: list[str] = []
            for row in index.get("sessions") or []:
                session_id = row.get("session_id")
                if not isinstance(session_id, str) or not self.session_exists(session_id):
                    continue
                artifacts = self._read_artifacts_unlocked(session_id)
                market = _normalize_market_artifact(artifacts.get("market"))
                refs = (market.get("result_ref"), market.get("reuse_ref"))
                if any(
                    isinstance(ref, dict) and ref.get("research_id") == research_id
                    for ref in refs
                ):
                    session_ids.append(session_id)
            return sorted(session_ids)

    def invalidate_market_result_references(
        self,
        research_id: str,
    ) -> list[str]:
        """清除指向已删除结果的 Session 引用，并写入需要重新调研的确定性闸门。"""
        affected = self.sessions_referencing_market_result(research_id)
        with _lock:
            for session_id in affected:
                artifacts = self._read_artifacts_unlocked(session_id)
                market = _normalize_market_artifact(artifacts.get("market"))
                market.update(
                    {
                        "result_ref": None,
                        "reuse_ref": None,
                        "market_result_confirmed": False,
                        "confirmed_result_ref": None,
                    }
                )
                artifacts["market"] = market
                self._write_artifacts_unlocked(session_id, artifacts)
                state = self._read_state_unlocked(session_id)
                gates = dict(state.get("gates") or {})
                gates["pending"] = {
                    "name": "market_research_required",
                    "prompt": "此前使用的市场结果已删除，请重新生成并确认调研方案。",
                }
                state["gates"] = gates
                self._write_state_unlocked(session_id, state)
        return affected

    def clear_expired_market_reference(
        self,
        session_id: str,
        expected_ref: dict[str, Any],
    ) -> None:
        """仅在当前引用仍等于过期引用时清除它，并引导重新调研。"""
        with _lock:
            artifacts = self._read_artifacts_unlocked(session_id)
            market = _normalize_market_artifact(artifacts.get("market"))
            current_ref = market.get("result_ref") or market.get("reuse_ref")
            if current_ref != expected_ref:
                return
            market.update(
                {
                    "result_ref": None,
                    "reuse_ref": None,
                    "market_result_confirmed": False,
                    "confirmed_result_ref": None,
                }
            )
            artifacts["market"] = market
            self._write_artifacts_unlocked(session_id, artifacts)
            state = self._read_state_unlocked(session_id)
            gates = dict(state.get("gates") or {})
            gates["pending"] = {
                "name": "market_research_required",
                "prompt": "当前市场结果已超过六个自然月，请重新调研。",
            }
            state["gates"] = gates
            self._write_state_unlocked(session_id, state)

    def delete_session(self, session_id: str) -> None:
        """删除 Session；若存在活动市场调研，必须先取消并完成临时数据清理。"""
        with _lock:
            artifacts = self._read_artifacts_unlocked(session_id)
            market = _normalize_market_artifact(artifacts.get("market"))
            active_research_id = market.get("active_research_id")
            active_retry_id = market.get("active_retry_id")
        active_run_id = active_research_id or active_retry_id
        if isinstance(active_run_id, str) and active_run_id:
            from career_os.platform.market_research.service import (
                get_market_research_service,
            )

            # cancel_for_session_delete（删除 Session 前取消调研）会校验任务归属，
            # 并等待 Runner 删除 temp 和未发布截图后才允许继续删除会话文件。
            get_market_research_service().cancel_for_session_delete(
                active_run_id,
                session_id,
            )
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
        """重置session。"""
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
        """处理estimate tokens。"""
        return sum(len(m.get("content", "")) // 4 + 1 for m in messages)

    def _read_messages_unlocked(self, session_id: str) -> list[dict[str, str]]:
        """读取messages unlocked。"""
        path = self._messages_path(session_id)
        if not path.exists():
            return []
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        return data.get("messages", [])

    def _write_messages_unlocked(
        self, session_id: str, messages: list[dict[str, str]]
    ) -> None:
        """写入messages unlocked。"""
        path = self._messages_path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump({"messages": messages}, f, ensure_ascii=False, indent=2)

    def _read_state_unlocked(self, session_id: str) -> dict[str, Any]:
        """读取state unlocked。"""
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
        """读取artifacts unlocked。"""
        path = self._artifacts_path(session_id)
        if not path.exists():
            return {**_DEFAULT_ARTIFACTS, "session_id": session_id}
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {**_DEFAULT_ARTIFACTS, "session_id": session_id}
        out = {**_DEFAULT_ARTIFACTS, **data}
        out["market"] = _normalize_market_artifact(data.get("market"))
        out["session_id"] = session_id
        return out

    def _write_state_unlocked(self, session_id: str, state: dict[str, Any]) -> None:
        """写入state unlocked。"""
        path = self._state_path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

    def _write_artifacts_unlocked(self, session_id: str, artifacts: dict[str, Any]) -> None:
        """写入artifacts unlocked。"""
        path = self._artifacts_path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {**_DEFAULT_ARTIFACTS, **artifacts, "session_id": session_id}
        payload["market"] = _normalize_market_artifact(artifacts.get("market"))
        with path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    def _read_index_unlocked(self) -> dict[str, Any]:
        """读取index unlocked。"""
        path = self._index_path()
        if not path.exists():
            return {"version": _INDEX_VERSION, "sessions": []}
        with path.open(encoding="utf-8") as f:
            return json.load(f)

    def _write_index_unlocked(self, index: dict[str, Any]) -> None:
        """写入index unlocked。"""
        path = self._index_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)

    def _apply_first_user_fallback_unlocked(
        self, session_id: str, messages: list[dict[str, str]]
    ) -> None:
        """应用first user fallback unlocked。"""
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
        """处理compute preview。"""
        for message in reversed(messages):
            if message.get("role") == "user":
                return message.get("content", "")[:40]
        return ""

    def _touch_index_unlocked(self, session_id: str) -> None:
        """刷新index unlocked。"""
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
