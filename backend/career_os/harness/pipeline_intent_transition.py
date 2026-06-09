"""Pipeline phase transitions driven by user intent (table-driven, precondition B)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import re

from career_os.harness.jd_prerequisites import check_jd_prerequisites, is_jd_intent
from career_os.harness.micro_classifier import classify
from career_os.harness.micro_classifier import is_chat_only_intent
from career_os.harness.micro_classifier_rules import match_pipeline_intent_rule_ids
from career_os.harness.pipeline_gates import PipelineGateError, is_explore_gate_confirmed
from career_os.harness.pipeline_gates import jump_to_phase
from career_os.harness.pipeline_jd_context import has_jd_context
from career_os.harness.pipeline_routing import get_current_phase, is_pipeline_session
from career_os.harness.pipeline_phase_transition import apply_list_phase
from career_os.platform.pipeline_constants import JUMP_TARGET_PHASES, PIPELINE_PHASES

PHASE_RANK: dict[str, int] = {phase: index for index, phase in enumerate(PIPELINE_PHASES)}

_SMALL_TALK_PHRASES = frozenset(
    {
        "你好",
        "您好",
        "hi",
        "hello",
        "hey",
        "在吗",
        "在不在",
        "你好吗",
        "早上好",
        "晚上好",
        "哈喽",
        "嗨",
    }
)


_JUMP_TARGET_WORKERS: dict[str, tuple[str, ...]] = {
    "explore": ("identity", "capability"),
    "market": ("market",),
    "jd_analysis": ("opportunity",),
    "resume_strategy": ("strategy",),
}


def _is_small_talk(user_message: str) -> bool:
    text = user_message.strip().lower()
    if not text:
        return True
    normalized = re.sub(r"[!！。.?？~～,\，、\s]+", "", text)
    return normalized in _SMALL_TALK_PHRASES


@dataclass(frozen=True)
class IntentTransition:
    from_phases: frozenset[str]
    to_phase: str
    rule_id: str
    preconditions: frozenset[str]
    suggested_workers: tuple[str, ...]


# Table order: when multiple rules match, pick highest PHASE_RANK[to_phase].
INTENT_TRANSITIONS: tuple[IntentTransition, ...] = (
    IntentTransition(
        frozenset({"resume_strategy"}),
        "resume_optimize",
        "intent_resume_optimize",
        frozenset({"P0", "P5", "P6"}),
        ("resume", "asset"),
    ),
    IntentTransition(
        frozenset({"jd_analysis", "market"}),
        "resume_strategy",
        "intent_resume_strategy",
        frozenset({"P0", "P1", "P3", "P6"}),
        ("strategy",),
    ),
    IntentTransition(
        frozenset({"jd_analysis", "market"}),
        "resume_strategy",
        "intent_declare_agent_project",
        frozenset({"P0", "P1", "P2", "P6"}),
        ("strategy",),
    ),
    IntentTransition(
        frozenset({"explore", "market"}),
        "jd_analysis",
        "intent_jd_eval",
        frozenset({"P0", "P1", "P2", "P4", "P6"}),
        ("opportunity",),
    ),
    IntentTransition(
        frozenset({"explore"}),
        "market",
        "intent_market",
        frozenset({"P0", "P4", "P6"}),
        ("market",),
    ),
)


def _explore_gate_precondition(session_state: dict[str, Any]) -> bool:
    if is_explore_gate_confirmed(session_state):
        return True
    closure = session_state.get("explore_closure") or {}
    return bool(closure.get("completed"))


def _check_precondition(
    precondition_id: str,
    session_state: dict[str, Any],
    user_message: str,
    *,
    chat_history: list[dict[str, str]] | None = None,
) -> bool:
    if precondition_id == "P0":
        return bool(session_state.get("list_id")) and is_pipeline_session(session_state)
    if precondition_id == "P1":
        ready, _ = check_jd_prerequisites(session_state)
        return ready
    if precondition_id == "P2":
        return has_jd_context(session_state, user_message, chat_history=chat_history)
    if precondition_id == "P3":
        return has_jd_context(
            session_state, user_message, chat_history=chat_history
        ) and "intent_resume_strategy" in match_pipeline_intent_rule_ids(user_message)
    if precondition_id == "P4":
        return _explore_gate_precondition(session_state)
    if precondition_id == "P5":
        flags = (session_state.get("gates") or {}).get("flags") or {}
        return bool(flags.get("optimize_confirmed"))
    if precondition_id == "P6":
        return not _is_small_talk(user_message)
    return False


def _preconditions_met(
    transition: IntentTransition,
    session_state: dict[str, Any],
    user_message: str,
    *,
    chat_history: list[dict[str, str]] | None = None,
) -> bool:
    return all(
        _check_precondition(
            pid, session_state, user_message, chat_history=chat_history
        )
        for pid in transition.preconditions
    )


def _resolve_via_rules(
    current_phase: str,
    session_state: dict[str, Any],
    user_message: str,
    *,
    chat_history: list[dict[str, str]] | None = None,
) -> IntentTransition | None:
    rule_ids = set(match_pipeline_intent_rule_ids(user_message))
    if not rule_ids:
        return None
    best: IntentTransition | None = None
    best_rank = -1
    for transition in INTENT_TRANSITIONS:
        if transition.rule_id not in rule_ids:
            continue
        if current_phase not in transition.from_phases:
            continue
        if not _preconditions_met(
            transition, session_state, user_message, chat_history=chat_history
        ):
            continue
        rank = PHASE_RANK.get(transition.to_phase, -1)
        if rank > best_rank:
            best_rank = rank
            best = transition
    return best


def _resolve_via_classifier(
    current_phase: str,
    session_state: dict[str, Any],
    user_message: str,
) -> IntentTransition | None:
    prior = session_state.get("prior_results") or {}
    data = classify(
        "pipeline_phase_intent",
        user_message,
        context={
            "current_phase": current_phase,
            "prior_workers": list(prior.keys()),
            "has_jd_context": has_jd_context(session_state, user_message),
            "gates_pending": (session_state.get("gates") or {}).get("pending"),
        },
    )
    target = data.get("target_phase")
    if not target or target not in PIPELINE_PHASES:
        return None
    if target in JUMP_TARGET_PHASES:
        if target == current_phase:
            return None
        for transition in INTENT_TRANSITIONS:
            if transition.to_phase != target:
                continue
            if current_phase not in transition.from_phases:
                continue
            if not _preconditions_met(transition, session_state, user_message):
                continue
            return transition
        return IntentTransition(
            frozenset({current_phase}),
            target,
            f"intent_jump_{target}",
            frozenset(),
            _JUMP_TARGET_WORKERS.get(target, tuple()),
        )
    if target == "resume_optimize":
        return None
    for transition in INTENT_TRANSITIONS:
        if transition.to_phase != target:
            continue
        if current_phase not in transition.from_phases:
            continue
        if not _preconditions_met(transition, session_state, user_message):
            continue
        return transition
    return None


def resolve_intent_phase_transition(
    user_message: str,
    session_state: dict[str, Any],
    *,
    chat_history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Return transition metadata; does not write disk."""
    current = get_current_phase(session_state) or "explore"
    empty: dict[str, Any] = {
        "applied": False,
        "from_phase": current,
        "to_phase": None,
        "rule_id": None,
        "suggested_workers": [],
        "source": None,
    }
    if not is_pipeline_session(session_state):
        return empty
    gates = session_state.get("gates") or {}
    if gates.get("pending"):
        return empty
    if is_chat_only_intent(user_message):
        return empty
    if _is_small_talk(user_message):
        return empty

    transition = _resolve_via_rules(
        current, session_state, user_message, chat_history=chat_history
    )
    source = "rule" if transition else None
    if not transition:
        transition = _resolve_via_classifier(current, session_state, user_message)
        source = "classifier" if transition else None
    if not transition:
        return empty

    target = transition.to_phase
    if target in JUMP_TARGET_PHASES:
        return {
            "applied": False,
            "from_phase": current,
            "to_phase": target,
            "rule_id": transition.rule_id,
            "suggested_workers": list(transition.suggested_workers),
            "source": source,
        }
    if PHASE_RANK.get(target, -1) <= PHASE_RANK.get(current, -1):
        return empty

    return {
        "applied": False,
        "from_phase": current,
        "to_phase": target,
        "rule_id": transition.rule_id,
        "suggested_workers": list(transition.suggested_workers),
        "source": source,
    }


def apply_intent_phase_transition(
    user_message: str,
    session_state: dict[str, Any],
    *,
    chat_history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Resolve and persist phase when preconditions pass."""
    resolved = resolve_intent_phase_transition(
        user_message, session_state, chat_history=chat_history
    )
    if not resolved.get("to_phase"):
        return resolved

    current = resolved["from_phase"]
    target = resolved["to_phase"]
    if target == current:
        return resolved

    list_id = session_state.get("list_id")
    if list_id:
        if target in JUMP_TARGET_PHASES:
            jump_result = jump_to_phase(
                session_state.get("session_id") or "",
                list_id,
                target,
                session_state,
            )
            if isinstance(jump_result, PipelineGateError):
                resolved["applied"] = False
                resolved["error_code"] = jump_result.code
                resolved["error_message"] = jump_result.message
                return resolved
        else:
            apply_list_phase(list_id, target)

    session_state["intent_suggested_workers"] = resolved.get("suggested_workers") or []
    session_state["last_phase_transition"] = {
        "from_phase": current,
        "to_phase": target,
        "rule_id": resolved.get("rule_id"),
        "source": resolved.get("source"),
    }
    resolved["applied"] = True
    return resolved
