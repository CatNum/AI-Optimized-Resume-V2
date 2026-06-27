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
    """选择委托给 Worker 的聊天历史窗口。"""
    # messages_meta（消息元数据）当前不参与判断，保留参数用于未来扩展和调用签名稳定。
    _ = messages_meta
    # 先用轻量分类器判断本轮 Worker 是否需要完整历史。
    decision = classify("history_scope", user_message, {})
    threshold = settings.history_scope_llm_accept_threshold
    use_full = bool(
        decision.get("needs_full_history")
        and (decision.get("confidence") or 0) >= threshold
    )
    # 分类器明确且置信度达标时传完整历史，否则只传最近窗口。
    if use_full:
        return list(chat_history_full), "full"
    window = slice_chat_rounds(
        chat_history_full,
        max_rounds=settings.worker_default_max_rounds,
    )
    return window, "recent_10"
