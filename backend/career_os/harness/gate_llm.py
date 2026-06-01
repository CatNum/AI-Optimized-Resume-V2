"""LLM fallback for gate intent classification."""

from __future__ import annotations

import json
import time
from typing import Any

from career_os.agents.lc.client import invoke_json, llm_enabled
from career_os.agents.lc.models import LLMRole
from career_os.config import settings
from career_os.harness.pipeline_routing import get_current_phase
from career_os.platform.prompt.loader import load_gate_intent_prompt
from career_os.platform.store.session import SessionStore

_LLM_TIMEOUT_S = 3.0


def build_recent_turns(session_id: str, *, max_turns: int = 2, max_chars: int = 200) -> list[dict[str, str]]:
    messages = SessionStore().load_messages_full(session_id)
    if messages and messages[-1].get("role") == "user":
        messages = messages[:-1]
    pairs: list[dict[str, str]] = []
    buffer: dict[str, str] = {}
    for msg in reversed(messages):
        role = msg.get("role") or ""
        content = (msg.get("content") or "")[:max_chars]
        if role == "assistant":
            buffer["assistant"] = content
        elif role == "user":
            buffer["user"] = content
            if "assistant" in buffer:
                pairs.insert(0, {"user": buffer["user"], "assistant": buffer["assistant"]})
                buffer = {}
            else:
                pairs.insert(0, {"user": buffer["user"], "assistant": ""})
            buffer = {}
        if len(pairs) >= max_turns:
            break
    return pairs[-max_turns:]


def _session_hints(session_state: dict[str, Any] | None) -> dict[str, Any]:
    if not session_state:
        return {}
    hints: dict[str, Any] = {}
    if session_state.get("list_type"):
        hints["list_type"] = session_state["list_type"]
    phase = get_current_phase(session_state)
    if phase:
        hints["current_phase"] = phase
    return hints


def classify_gate_intent_llm(
    user_message: str,
    pending_gate: dict[str, Any],
    *,
    session_id: str | None = None,
    session_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    pending_name = pending_gate.get("name")
    if not llm_enabled():
        return {
            "matched": False,
            "gate_name": pending_name,
            "intent": "unknown",
            "confidence": 0.0,
            "source": "none",
        }

    payload: dict[str, Any] = {
        "user_message": user_message,
        "pending_gate": pending_gate,
        "recent_turns": build_recent_turns(session_id) if session_id else [],
        "session_hints": _session_hints(session_state),
    }
    user = json.dumps(payload, ensure_ascii=False)
    started = time.perf_counter()
    try:
        data = invoke_json(
            load_gate_intent_prompt(),
            user,
            role=LLMRole.GATE_INTENT,
            temperature=0.1,
        )
    except Exception:
        data = None
    if time.perf_counter() - started > _LLM_TIMEOUT_S:
        data = None

    if not data:
        return {
            "matched": False,
            "gate_name": pending_name,
            "intent": "unknown",
            "confidence": 0.0,
            "source": "llm",
        }

    intent = data.get("intent") or "unknown"
    if intent not in {"confirm", "reject", "unknown"}:
        intent = "unknown"
    gate_name = data.get("gate_name") or pending_name
    if gate_name != pending_name:
        intent = "unknown"
    confidence = float(data.get("confidence") or 0.0)
    threshold = settings.gate_llm_accept_threshold
    matched = intent in {"confirm", "reject"} and confidence >= threshold
    reason = (data.get("reason") or "")[:120] or None
    return {
        "matched": matched,
        "gate_name": gate_name,
        "intent": intent if matched else "unknown",
        "confidence": confidence,
        "source": "llm",
        "reason": reason,
    }
