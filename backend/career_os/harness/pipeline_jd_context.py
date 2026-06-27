"""共享的 JD 和 pipeline 上下文辅助函数，不引入路由模块。"""

from __future__ import annotations

from typing import Any

from career_os.harness.jd_prerequisites import is_jd_intent
from career_os.platform.store.task import TaskStore

_JD_REFERENCE_PHRASES = (
    "这份 jd",
    "这份jd",
    "这个岗位",
    "刚才的评估",
    "刚才的分析",
    "按照这个",
    "按这份",
    "该岗位",
    "此岗位",
)


def has_jd_context(
    session_state: dict[str, Any],
    user_message: str,
    *,
    chat_history: list[dict[str, str]] | None = None,
) -> bool:
    """has_jd_context（has jd context）的函数说明。

    session_state（参数）、user_message（参数）、chat_history（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    list_id = session_state.get("list_id")
    if list_id:
        meta = TaskStore().get_list_meta(list_id) or {}
        if meta.get("related_jd_fingerprint"):
            return True
    prior = session_state.get("prior_results") or {}
    if "market" in prior or "opportunity" in prior:
        return True
    if is_jd_intent(user_message):
        return True
    lower = user_message.lower()
    if any(p in lower or p in user_message for p in _JD_REFERENCE_PHRASES):
        return True
    for message in chat_history or []:
        if message.get("role") != "user":
            continue
        content = message.get("content") or ""
        if is_jd_intent(content):
            return True
        cl = content.lower()
        if any(p in cl or p in content for p in _JD_REFERENCE_PHRASES):
            return True
    return False
