"""Lightweight LLM classifiers: gate_intent, history_scope."""

from __future__ import annotations

import json
import time
from typing import Any

from career_os.agents.lc.client import invoke_json, llm_enabled
from career_os.agents.lc.models import LLMRole
from career_os.config import settings
from career_os.harness.gate_rules import is_rule_clear_hit, match_gate_intent_rules
from career_os.harness.micro_classifier_rules import match_history_scope_rules
from career_os.platform.prompt.loader import load_gate_intent_prompt, load_micro_classifier_prompt

_LLM_TIMEOUT_S = 3.0
_TASKS = frozenset({"gate_intent", "history_scope"})


def classify(
    task: str,
    user_message: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if task not in _TASKS:
        raise ValueError(f"unknown micro_classifier task: {task}")
    context = context or {}
    if task == "gate_intent":
        return _classify_gate_intent(user_message, context)
    return _classify_history_scope(user_message)


def _classify_gate_intent(user_message: str, context: dict[str, Any]) -> dict[str, Any]:
    pending_gate = context.get("pending_gate") or {}
    pending_name = pending_gate.get("name")
    rule_result = match_gate_intent_rules(user_message, pending_gate)
    if is_rule_clear_hit(rule_result):
        return rule_result
    if not pending_name:
        return rule_result
    return _classify_gate_intent_llm(user_message, pending_gate)


def _classify_gate_intent_llm(
    user_message: str,
    pending_gate: dict[str, Any],
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
    payload = {
        "user_message": user_message,
        "pending_gate": pending_gate,
    }
    data = _invoke_task("gate_intent", load_gate_intent_prompt(), payload)
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


def _classify_history_scope(user_message: str) -> dict[str, Any]:
    rule = match_history_scope_rules(user_message)
    if rule:
        return rule
    if not llm_enabled():
        return {
            "needs_full_history": False,
            "confidence": 0.0,
            "source": "none",
        }
    payload = {"user_message": user_message}
    data = _invoke_task(
        "history_scope",
        load_micro_classifier_prompt("history_scope"),
        payload,
    )
    if not data:
        return {
            "needs_full_history": False,
            "confidence": 0.0,
            "source": "llm",
        }
    needs_full = bool(data.get("needs_full_history"))
    confidence = float(data.get("confidence") or 0.0)
    threshold = settings.history_scope_llm_accept_threshold
    if needs_full and confidence < threshold:
        needs_full = False
    reason = (data.get("reason") or "")[:120] or None
    return {
        "needs_full_history": needs_full,
        "confidence": confidence,
        "source": "llm",
        "reason": reason,
    }


def _invoke_task(task: str, system: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    user = json.dumps(payload, ensure_ascii=False)
    started = time.perf_counter()
    try:
        data = invoke_json(system, user, role=LLMRole.GATE_INTENT, temperature=0.1)
    except Exception:
        return None
    if time.perf_counter() - started > _LLM_TIMEOUT_S:
        return None
    return data if isinstance(data, dict) else None
