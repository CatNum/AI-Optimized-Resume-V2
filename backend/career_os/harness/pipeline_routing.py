from __future__ import annotations

from typing import Any

from career_os.harness.explore_closure import explore_continuation_analyze
from career_os.harness.jd_prerequisites import check_jd_prerequisites, is_jd_intent
from career_os.harness.pipeline_gates import is_explore_gate_confirmed
from career_os.platform.pipeline_constants import PHASE_TO_MILESTONE_ID, PIPELINE_PHASES
from career_os.platform.store.task import TaskStore

PHASE_PRIMARY_WORKERS: dict[str, frozenset[str]] = {
    "explore": frozenset({"identity", "capability"}),
    "market": frozenset({"market"}),
    "jd_analysis": frozenset({"opportunity"}),
    "resume_strategy": frozenset({"strategy"}),
    "resume_optimize": frozenset({"resume", "asset"}),
}

JD_PHASES = frozenset({"market", "jd_analysis", "resume_strategy", "resume_optimize"})
JD_CHAIN_WORKERS = frozenset({"market", "opportunity", "strategy", "resume", "asset"})

_LEGACY_LIST_TYPES = frozenset({"explore", "jd"})


def is_pipeline_session(session_state: dict[str, Any]) -> bool:
    return session_state.get("list_type") == "pipeline"


def is_pipeline_explore_phase(session_state: dict[str, Any]) -> bool:
    if not is_pipeline_session(session_state):
        return False
    return get_current_phase(session_state) == "explore"


def infer_pipeline_phase_from_workers(
    workers: list[str],
    session_state: dict[str, Any],
) -> str:
    phase_order = (
        "resume_optimize",
        "resume_strategy",
        "jd_analysis",
        "market",
        "explore",
    )
    for phase in phase_order:
        allowed = PHASE_PRIMARY_WORKERS.get(phase, frozenset())
        if any(worker in allowed for worker in workers):
            return phase
    return get_current_phase(session_state) or "explore"


def as_pipeline_analyze_result(
    result: dict[str, Any],
    session_state: dict[str, Any],
) -> dict[str, Any]:
    workers = list(result.get("workers") or [])
    phase = result.get("pipeline_phase") or infer_pipeline_phase_from_workers(
        workers, session_state
    )
    out: dict[str, Any] = {
        **result,
        "workers": workers,
        "list_type": "pipeline",
        "pipeline_phase": phase,
    }
    return enforce_pipeline_phase_rules(out, session_state, "")


def get_pipeline_meta(session_state: dict[str, Any]) -> dict[str, Any] | None:
    if session_state.get("list_type") != "pipeline":
        return None
    list_id = session_state.get("list_id")
    if not list_id:
        return None
    return TaskStore().get_list_meta(list_id)


def get_current_phase(session_state: dict[str, Any]) -> str | None:
    meta = get_pipeline_meta(session_state)
    if not meta:
        if is_pipeline_session(session_state):
            return "explore"
        return None
    return meta.get("current_phase") or "explore"


def is_pipeline_explore_phase(session_state: dict[str, Any]) -> bool:
    return (
        session_state.get("list_type") == "pipeline"
        and get_current_phase(session_state) == "explore"
    )


def pipeline_analyze_payload(session_state: dict[str, Any]) -> dict[str, Any]:
    phase = get_current_phase(session_state) or "explore"
    flags = (session_state.get("gates") or {}).get("flags") or {}
    allowed = sorted(PHASE_PRIMARY_WORKERS.get(phase, frozenset()))
    return {
        "pipeline_mode": True,
        "current_phase": phase,
        "allowed_workers": allowed,
        "explore_gate_confirmed": is_explore_gate_confirmed(session_state),
        "strategy_complete": bool(flags.get("strategy_complete")),
        "optimize_confirmed": bool(flags.get("optimize_confirmed")),
        "milestone_id": PHASE_TO_MILESTONE_ID.get(phase),
    }


def filter_workers_for_pipeline(
    workers: list[str],
    session_state: dict[str, Any],
    *,
    phase: str | None = None,
) -> list[str]:
    phase = phase or get_current_phase(session_state) or "explore"
    flags = (session_state.get("gates") or {}).get("flags") or {}
    if phase == "resume_optimize" and not flags.get("optimize_confirmed"):
        return []
    if phase == "explore" and is_explore_gate_confirmed(session_state):
        jd_chain = [w for w in workers if w in JD_CHAIN_WORKERS]
        if jd_chain:
            return jd_chain
    allowed = PHASE_PRIMARY_WORKERS.get(phase, frozenset())
    filtered = [w for w in workers if w in allowed]
    if phase == "resume_optimize" and "resume" in filtered and "asset" not in filtered:
        if "asset" in allowed:
            filtered.append("asset")
    return filtered


def enforce_pipeline_phase_rules(
    result: dict[str, Any],
    session_state: dict[str, Any],
    user_message: str,
) -> dict[str, Any]:
    if session_state.get("list_type") != "pipeline":
        return result
    current_phase = get_current_phase(session_state) or "explore"
    inferred_phase = result.get("pipeline_phase") or infer_pipeline_phase_from_workers(
        result.get("workers") or [], session_state
    )
    phase = (
        inferred_phase
        if inferred_phase in PIPELINE_PHASES
        else current_phase
    )
    workers = filter_workers_for_pipeline(
        result.get("workers") or [], session_state, phase=current_phase
    )
    out: dict[str, Any] = {
        "workers": workers,
        "list_type": "pipeline",
        "pipeline_phase": phase,
    }

    if phase in JD_PHASES and workers:
        ready, reason = check_jd_prerequisites(session_state)
        if not ready:
            return {
                "workers": [],
                "list_type": "pipeline",
                "jd_prerequisite_blocked": True,
                "jd_block_reason": reason or "explore",
            }

    if phase == "resume_optimize":
        flags = (session_state.get("gates") or {}).get("flags") or {}
        if not flags.get("optimize_confirmed"):
            return {"workers": [], "list_type": "pipeline", "pipeline_phase": phase}

    if (
        phase != "explore"
        and current_phase == "explore"
        and not is_explore_gate_confirmed(session_state)
        and workers
    ):
        return {
            "workers": [],
            "list_type": "pipeline",
            "pipeline_phase": phase,
            "explore_gate_required": True,
        }

    return out


def pipeline_fallback_workers(
    user_message: str,
    session_state: dict[str, Any],
) -> dict[str, Any] | None:
    if session_state.get("list_type") != "pipeline":
        return None
    phase = get_current_phase(session_state) or "explore"
    text = user_message.lower()
    prior = session_state.get("prior_results") or {}
    flags = (session_state.get("gates") or {}).get("flags") or {}

    if phase == "explore":
        if "初探" in user_message or "explore" in text:
            return enforce_pipeline_phase_rules(
                {"workers": ["identity", "capability"]}, session_state, user_message
            )
        cont = explore_continuation_analyze(session_state)
        if cont:
            return enforce_pipeline_phase_rules(cont, session_state, user_message)
    if phase in {"market", "jd_analysis"} and (
        is_jd_intent(user_message) or "jd" in text or "岗位" in user_message
    ):
        w = ["market"] if phase == "market" else ["opportunity"]
        if phase == "jd_analysis" and "market" in prior and "opportunity" not in prior:
            w = ["opportunity"]
        return enforce_pipeline_phase_rules(
            {"workers": w}, session_state, user_message
        )
    if phase == "resume_strategy" and any(
        k in user_message for k in ("策略", "继续", "下一步", "制定")
    ):
        return enforce_pipeline_phase_rules(
            {"workers": ["strategy"]}, session_state, user_message
        )
    if phase == "resume_optimize" and flags.get("optimize_confirmed"):
        if ("优化" in user_message or "resume" in text) and "resume" not in prior:
            return enforce_pipeline_phase_rules(
                {"workers": ["resume", "asset"]}, session_state, user_message
            )
    return None




def maybe_apply_jd_fingerprint_from_message(
    session_id: str | None,
    session_state: dict[str, Any],
    user_message: str,
) -> dict[str, Any]:
    if not session_id or session_state.get("list_type") != "pipeline":
        return session_state
    phase = get_current_phase(session_state) or "explore"
    if phase not in {"market", "jd_analysis"}:
        return session_state
    if not (is_jd_intent(user_message) or "jd" in user_message.lower()):
        return session_state
    list_id = session_state.get("list_id")
    if not list_id:
        return session_state
    from career_os.harness.jd_change import apply_jd_fingerprint_change, jd_fingerprint

    fp = jd_fingerprint(user_message)
    result = apply_jd_fingerprint_change(session_id, list_id, fp, session_state)
    if isinstance(result, dict) and not result.get("unchanged"):
        session_state = dict(session_state)
    return session_state
