"""闸门意图的 LLM 回退逻辑，委托给 micro_classifier。"""

from __future__ import annotations

from typing import Any

from career_os.harness.micro_classifier import classify


def classify_gate_intent_llm(
    user_message: str,
    pending_gate: dict[str, Any],
    *,
    session_id: str | None = None,
    session_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """classify_gate_intent_llm（classify gate intent llm）的函数说明。

    user_message（参数）、pending_gate（参数）、session_id（参数）、session_state（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    _ = session_id, session_state
    return classify(
        "gate_intent",
        user_message,
        {"pending_gate": pending_gate},
    )
