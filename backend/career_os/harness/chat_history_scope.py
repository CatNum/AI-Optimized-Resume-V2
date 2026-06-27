"""为 Worker 委托选择聊天历史窗口。"""

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
    """选择委托给 Worker 的聊天历史窗口。

    chat_history_full（完整聊天历史）是当前会话可用的全部消息；
    user_message（用户消息）用于判断是否需要完整上下文；
    messages_meta（消息元数据）当前仅保留签名兼容。
    返回值是二元组：选中的消息列表，以及 scope_label（范围标签），例如 full 或 recent_10。
    """
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
