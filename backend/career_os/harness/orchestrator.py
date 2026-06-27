import threading
from datetime import UTC, datetime
from typing import Any

from career_os.config import settings
from career_os.harness.errors import HarnessError

_chat_lock = threading.Lock()
_active_runs: dict[str, bool] = {}


class ChatOrchestrator:
    """
    ChatOrchestrator（聊天编排器）负责管理单会话对话运行状态和上下文使用提醒。
    """

    def __init__(self) -> None:
        """初始化对象。"""
        self._warn_ratio = settings.chat_history_warn_ratio

    def begin_chat(
        self,
        session_id: str,
        session_state: dict[str, Any],
        messages_meta: dict[str, Any],
    ) -> HarnessError | dict[str, Any]:
        """处理begin chat。"""
        with _chat_lock:
            if _active_runs.get(session_id):
                return HarnessError("chat_in_progress", "Another chat run is active")

            _active_runs[session_id] = True

        recommend_new_session = self._should_recommend_new_session(messages_meta)
        context = {
            "session_id": session_id,
            "recommend_new_session": recommend_new_session,
            "messages_meta": messages_meta,
        }
        if recommend_new_session:
            context["history_notice"] = (
                "对话较长，建议 POST /v1/sessions/new 开新会话；档案与 HTML 仍保留"
            )
        return context

    def end_chat(self, session_id: str) -> None:
        """处理end chat。"""
        with _chat_lock:
            _active_runs.pop(session_id, None)

    def is_chat_in_progress(self, session_id: str) -> bool:
        """判断chat in progress。"""
        with _chat_lock:
            return bool(_active_runs.get(session_id))

    def touch_session(self, session_state: dict[str, Any]) -> dict[str, Any]:
        """刷新session。"""
        state = dict(session_state)
        state["last_activity_at"] = datetime.now(UTC).isoformat()
        return state

    def _should_recommend_new_session(self, messages_meta: dict[str, Any]) -> bool:
        """判断是否需要recommend new session。"""
        if messages_meta.get("over_limit"):
            return True
        usage_ratio = messages_meta.get("usage_ratio") or 0.0
        return usage_ratio >= self._warn_ratio

    def context_usage_payload(self, messages_meta: dict[str, Any]) -> dict[str, Any]:
        """处理context usage payload。"""
        return {
            **messages_meta,
            "recommend_new_session": self._should_recommend_new_session(messages_meta),
        }
