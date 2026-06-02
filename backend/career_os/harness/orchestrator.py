import threading
from datetime import UTC, datetime, timedelta
from typing import Any

from career_os.config import settings
from career_os.harness.errors import HarnessError

_chat_lock = threading.Lock()
_active_runs: dict[str, bool] = {}


class ChatOrchestrator:
    def __init__(self) -> None:
        self._session_idle_ttl = settings.session_idle_ttl
        self._warn_ratio = settings.chat_history_warn_ratio

    def begin_chat(
        self,
        session_id: str,
        session_state: dict[str, Any],
        messages_meta: dict[str, Any],
    ) -> HarnessError | dict[str, Any]:
        with _chat_lock:
            if _active_runs.get(session_id):
                return HarnessError("chat_in_progress", "Another chat run is active")

            expired = self._is_session_expired(session_state)
            if expired:
                return HarnessError("session_expired", "Session idle TTL exceeded")

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
        with _chat_lock:
            _active_runs.pop(session_id, None)

    def is_chat_in_progress(self, session_id: str) -> bool:
        with _chat_lock:
            return bool(_active_runs.get(session_id))

    def touch_session(self, session_state: dict[str, Any]) -> dict[str, Any]:
        state = dict(session_state)
        state["last_activity_at"] = datetime.now(UTC).isoformat()
        return state

    def _is_session_expired(self, session_state: dict[str, Any]) -> bool:
        last_activity = session_state.get("last_activity_at")
        if not last_activity:
            return False
        last_dt = datetime.fromisoformat(last_activity.replace("Z", "+00:00"))
        return datetime.now(UTC) - last_dt > timedelta(seconds=self._session_idle_ttl)

    def _should_recommend_new_session(self, messages_meta: dict[str, Any]) -> bool:
        if messages_meta.get("over_limit"):
            return True
        usage_ratio = messages_meta.get("usage_ratio") or 0.0
        return usage_ratio >= self._warn_ratio

    def context_usage_payload(self, messages_meta: dict[str, Any]) -> dict[str, Any]:
        return {
            **messages_meta,
            "recommend_new_session": self._should_recommend_new_session(messages_meta),
        }
