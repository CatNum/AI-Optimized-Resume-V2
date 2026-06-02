"""LLM fallback for gate intent — delegates to micro_classifier."""

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
    _ = session_id, session_state
    return classify(
        "gate_intent",
        user_message,
        {"pending_gate": pending_gate},
    )
