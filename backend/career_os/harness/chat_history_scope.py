"""Select chat history window for Worker delegation."""

from __future__ import annotations

from typing import Any

from career_os.config import settings
from career_os.harness.micro_classifier import classify
from career_os.platform.store.session import slice_chat_rounds


def select_worker_chat_history(
    chat_history_full: list[dict[str, str]],
    user_message: str,
    messages_meta: dict[str, Any] | None = None,
) -> tuple[list[dict[str, str]], str]:
    _ = messages_meta
    decision = classify("history_scope", user_message, {})
    threshold = settings.history_scope_llm_accept_threshold
    use_full = bool(
        decision.get("needs_full_history")
        and (decision.get("confidence") or 0) >= threshold
    )
    if use_full:
        return list(chat_history_full), "full"
    window = slice_chat_rounds(
        chat_history_full,
        max_rounds=settings.worker_default_max_rounds,
    )
    return window, "recent_10"
