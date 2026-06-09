"""Lightweight LLM classifiers: gate_intent, history_scope."""

from __future__ import annotations

import json
import time
from typing import Any

from career_os.agents.lc.client import invoke_json, llm_enabled
from career_os.agents.lc.models import LLMRole
from career_os.config import settings
from career_os.harness.gate_rules import is_rule_clear_hit, match_gate_intent_rules
from career_os.harness.micro_classifier_rules import (
    match_chat_only_intent_rules,
    match_history_scope_rules,
    match_pipeline_intent_rule_ids,
    match_profile_memory_rules,
)
from career_os.platform.pipeline_constants import PIPELINE_PHASES
from career_os.platform.prompt.loader import load_gate_intent_prompt, load_micro_classifier_prompt

_LLM_TIMEOUT_S = 3.0
_TASKS = frozenset(
    {
        "chat_only_intent",
        "gate_intent",
        "history_scope",
        "profile_memory_scope",
        "pipeline_phase_intent",
    }
)

_EXPLICIT_PHASE_TRANSITION_PHRASES = (
    "转换到",
    "切到",
    "切回",
    "回到",
    "进入",
    "转到",
)


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
    if task == "chat_only_intent":
        return _classify_chat_only_intent(user_message)
    if task == "history_scope":
        return _classify_history_scope(user_message)
    if task == "profile_memory_scope":
        return _classify_profile_memory_scope(user_message, context)
    return _classify_pipeline_phase_intent(user_message, context)


def _classify_chat_only_intent(user_message: str) -> dict[str, Any]:
    rule = match_chat_only_intent_rules(user_message)
    if rule:
        return rule
    if not llm_enabled():
        return {
            "chat_only": False,
            "confidence": 0.0,
            "source": "none",
        }
    system = (
        "你是 chat_only_intent 分类器：仅根据用户当前这一条消息，判断用户是否明确要求进入闲聊/随便聊聊状态，"
        "且本轮不分配任何任务、不推进任何流程。"
        "输出 JSON，对象字段必须包含 chat_only (boolean)、confidence (0到1)、reason (简短字符串)。"
        "若用户只是普通问候、继续当前流程、或仍在询问职业规划相关内容，则 chat_only=false。"
    )
    payload = {"user_message": user_message}
    data = _invoke_task("chat_only_intent", system, payload)
    if not data:
        return {
            "chat_only": False,
            "confidence": 0.0,
            "source": "llm",
        }
    chat_only = bool(data.get("chat_only"))
    confidence = float(data.get("confidence") or 0.0)
    threshold = settings.history_scope_llm_accept_threshold
    if not chat_only or confidence < threshold:
        chat_only = False
    return {
        "chat_only": chat_only,
        "confidence": confidence,
        "source": "llm",
        "reason": (data.get("reason") or "")[:120] or None,
    }


def is_chat_only_intent(user_message: str, context: dict[str, Any] | None = None) -> bool:
    data = classify("chat_only_intent", user_message, context or {})
    return bool(data.get("chat_only"))


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


def _classify_profile_memory_scope(
    user_message: str,
    context: dict[str, Any],
) -> dict[str, Any]:
    rule_sections = match_profile_memory_rules(user_message)
    if rule_sections:
        return {
            "sections": sorted(rule_sections),
            "confidence": 0.95,
            "source": "rule",
            "reason": "keyword_match",
        }
    if not llm_enabled():
        return {"sections": [], "confidence": 0.0, "source": "none"}
    payload = {
        "user_message": user_message,
        "current_phase": context.get("current_phase"),
        "worker_id": context.get("worker_id"),
        "list_type": context.get("list_type"),
    }
    data = _invoke_task(
        "profile_memory_scope",
        load_micro_classifier_prompt("profile_memory_scope"),
        payload,
    )
    if not data:
        return {"sections": [], "confidence": 0.0, "source": "llm"}
    sections = [
        s for s in (data.get("sections") or []) if isinstance(s, str) and s in {
            "resume",
            "basic_intent",
            "exploration",
            "market",
            "strategy",
            "capability",
        }
    ]
    confidence = float(data.get("confidence") or 0.0)
    threshold = settings.history_scope_llm_accept_threshold
    if confidence < threshold:
        sections = []
    return {
        "sections": sections,
        "confidence": confidence,
        "source": "llm",
        "reason": (data.get("reason") or "")[:120] or None,
    }


def _classify_pipeline_phase_intent(
    user_message: str,
    context: dict[str, Any],
) -> dict[str, Any]:
    rule_ids = match_pipeline_intent_rule_ids(user_message)
    if rule_ids and not _looks_like_explicit_phase_transition(user_message):
        return {
            "target_phase": None,
            "confidence": 0.95,
            "source": "rule",
            "reason": f"rules:{','.join(rule_ids)}",
        }
    if not llm_enabled():
        return {"target_phase": None, "confidence": 0.0, "source": "none"}
    payload = {
        "user_message": user_message,
        "current_phase": context.get("current_phase"),
        "prior_workers": context.get("prior_workers") or [],
        "has_jd_context": context.get("has_jd_context"),
        "gates_pending": context.get("gates_pending"),
    }
    data = _invoke_task(
        "pipeline_phase_intent",
        load_micro_classifier_prompt("pipeline_phase_intent"),
        payload,
    )
    if not data:
        return {"target_phase": None, "confidence": 0.0, "source": "llm"}
    target = data.get("target_phase")
    if target is not None and target not in PIPELINE_PHASES:
        target = None
    confidence = float(data.get("confidence") or 0.0)
    threshold = settings.history_scope_llm_accept_threshold
    if confidence < threshold:
        target = None
    return {
        "target_phase": target,
        "confidence": confidence,
        "source": "llm",
        "reason": (data.get("reason") or "")[:120] or None,
    }


def _looks_like_explicit_phase_transition(user_message: str) -> bool:
    text = (user_message or "").strip()
    if not text:
        return False
    return any(phrase in text for phrase in _EXPLICIT_PHASE_TRANSITION_PHRASES)


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
