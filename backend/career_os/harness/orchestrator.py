import threading
from datetime import UTC, datetime
from typing import Any

from career_os.config import settings
from career_os.harness.errors import HarnessError

_chat_lock = threading.Lock()
_active_runs: dict[str, bool] = {}


class ChatOrchestrator:
    """ChatOrchestrator（ChatOrchestrator）的项目代码结构说明。

    该类封装当前模块中的一组相关状态或行为，供业务代码、测试代码或运行时流程复用。"""
    def __init__(self) -> None:
        """__init__（初始化对象）的函数说明。

        该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
        self._warn_ratio = settings.chat_history_warn_ratio

    def begin_chat(
        self,
        session_id: str,
        session_state: dict[str, Any],
        messages_meta: dict[str, Any],
    ) -> HarnessError | dict[str, Any]:
        """begin_chat（begin chat）的函数说明。

        session_id（参数）、session_state（参数）、messages_meta（参数）用于向该函数传入运行所需的数据。

        返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
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
        """end_chat（end chat）的函数说明。

        session_id（参数）用于向该函数传入运行所需的数据。

        返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
        with _chat_lock:
            _active_runs.pop(session_id, None)

    def is_chat_in_progress(self, session_id: str) -> bool:
        """is_chat_in_progress（is chat in progress）的函数说明。

        session_id（参数）用于向该函数传入运行所需的数据。

        返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
        with _chat_lock:
            return bool(_active_runs.get(session_id))

    def touch_session(self, session_state: dict[str, Any]) -> dict[str, Any]:
        """touch_session（touch session）的函数说明。

        session_state（参数）用于向该函数传入运行所需的数据。

        返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
        state = dict(session_state)
        state["last_activity_at"] = datetime.now(UTC).isoformat()
        return state

    def _should_recommend_new_session(self, messages_meta: dict[str, Any]) -> bool:
        """_should_recommend_new_session（内部函数 should recommend new session）的函数说明。

        messages_meta（参数）用于向该函数传入运行所需的数据。

        该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
        if messages_meta.get("over_limit"):
            return True
        usage_ratio = messages_meta.get("usage_ratio") or 0.0
        return usage_ratio >= self._warn_ratio

    def context_usage_payload(self, messages_meta: dict[str, Any]) -> dict[str, Any]:
        """context_usage_payload（context usage payload）的函数说明。

        messages_meta（参数）用于向该函数传入运行所需的数据。

        返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
        return {
            **messages_meta,
            "recommend_new_session": self._should_recommend_new_session(messages_meta),
        }
