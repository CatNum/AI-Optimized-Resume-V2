"""Gate intent matching: hard rules first, then LLM fallback."""

from __future__ import annotations

from typing import Any

from career_os.harness.gate_llm import classify_gate_intent_llm
from career_os.harness.gate_patterns import (
    EXPLORE_COMPLETE_AFFIRMATIVE,
    GATE_PATTERNS,
    matches_explore_complete_affirmative,
)
from career_os.harness.gate_rules import is_rule_clear_hit, match_gate_intent_rules
from career_os.platform.trace.writer import TraceWriter

GATE_REPLY_HINTS: dict[str, str] = {
    "explore_repeat": "请回复：不需要 / 需要",
    "explore_complete": "请回复：确认完成初探 / 还要继续聊聊",
    "explore_review_complete": "请回复：确认复盘完成 / 再想想",
    "optimize_confirm": "请回复：确认优化 / 先不优化",
    "strategy_complete": "请回复：策略可以了 / 还要改策略",
}

GATE_CLARIFY_SUFFIX = "我没完全理解您的意思，请补充说明您的选择或下一步打算。"

_DEFAULT_HINT = "请明确回复「同意」或「暂不」"


def gate_reply_hint(gate_name: str | None) -> str:
    if not gate_name:
        return _DEFAULT_HINT
    return GATE_REPLY_HINTS.get(gate_name, _DEFAULT_HINT)


def append_gate_reply_hint(text: str, gate_name: str | None) -> str:
    hint = gate_reply_hint(gate_name)
    body = (text or "").rstrip()
    if not body:
        return hint
    if hint in body:
        return body
    return f"{body}\n\n{hint}"


def build_gate_clarify_text(pending_gate: dict[str, Any] | None) -> str:
    pending = pending_gate or {}
    prompt = (pending.get("prompt") or "").strip()
    name = pending.get("name")
    parts = [p for p in (prompt, GATE_CLARIFY_SUFFIX) if p]
    return append_gate_reply_hint("\n\n".join(parts), name)


def _emit_gate_trace(
    trace: TraceWriter | None,
    session_id: str | None,
    result: dict[str, Any],
) -> None:
    if not trace or not session_id:
        return
    source = result.get("source")
    gate_name = result.get("gate_name")
    if source == "rule" and result.get("matched"):
        trace.emit(
            "gate.rule_hit",
            session_id=session_id,
            actor="harness",
            tool_name="match_gate_intent",
            detail={
                "gate_name": gate_name,
                "intent": result.get("intent"),
                "pattern": result.get("pattern"),
                "source": source,
            },
        )
    elif source == "llm":
        trace.emit(
            "gate.llm_classify",
            session_id=session_id,
            actor="harness",
            tool_name="match_gate_intent",
            detail={
                "gate_name": gate_name,
                "intent": result.get("intent"),
                "confidence": result.get("confidence"),
                "matched": result.get("matched"),
                "reason": result.get("reason"),
                "source": source,
            },
        )


def match_gate_intent(
    user_message: str,
    pending_gate: dict[str, Any] | None = None,
    *,
    session_id: str | None = None,
    session_state: dict[str, Any] | None = None,
    trace_writer: TraceWriter | None = None,
) -> dict[str, Any]:
    rule_result = match_gate_intent_rules(user_message, pending_gate)
    if is_rule_clear_hit(rule_result):
        _emit_gate_trace(trace_writer, session_id, rule_result)
        return rule_result

    pending_name = (pending_gate or {}).get("name")
    if not pending_name:
        return rule_result
    if pending_name == "explore_complete":
        return rule_result

    llm_result = classify_gate_intent_llm(
        user_message,
        pending_gate or {},
        session_id=session_id,
        session_state=session_state,
    )
    _emit_gate_trace(trace_writer, session_id, llm_result)
    return llm_result


# Re-export for tests / legacy imports
_matches_explore_complete_affirmative = matches_explore_complete_affirmative
_EXPLORE_COMPLETE_AFFIRMATIVE = EXPLORE_COMPLETE_AFFIRMATIVE
