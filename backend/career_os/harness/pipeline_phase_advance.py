"""根据 Coordinator 分析输出向前推进 pipeline 阶段，优先采用 LLM 判断。"""

from __future__ import annotations

from typing import Any

from career_os.harness.jd_prerequisites import check_jd_prerequisites, is_jd_intent
from career_os.harness.pipeline_gates import is_explore_gate_confirmed
from career_os.harness.pipeline_jd_context import has_jd_context
from career_os.harness.pipeline_phase_transition import apply_list_phase
from career_os.platform.pipeline_constants import PIPELINE_PHASES
from career_os.platform.store.profile import ProfileStore
from career_os.platform.store.task import TaskStore

PHASE_RANK: dict[str, int] = {phase: index for index, phase in enumerate(PIPELINE_PHASES)}


def can_enter_pipeline_phase(
    target_phase: str,
    session_state: dict[str, Any],
    user_message: str,
) -> bool:
    """校验分析阶段声明的前进目标阶段，B 表示宽松 JD 上下文。"""
    if target_phase not in PIPELINE_PHASES:
        return False
    if target_phase == "explore":
        return True
    if target_phase in {"market", "jd_analysis", "resume_strategy"}:
        ready, _ = check_jd_prerequisites(session_state)
        if not ready:
            return False
        profile = ProfileStore().get(["exploration"])
        exploration = profile.get("exploration") or {}
        if not is_explore_gate_confirmed(session_state):
            closure = session_state.get("explore_closure") or {}
            if not closure.get("completed") and not exploration.get("completed_at"):
                return False
        if target_phase == "resume_strategy":
            return has_jd_context(session_state, user_message)
        if target_phase == "jd_analysis":
            return has_jd_context(session_state, user_message) or is_jd_intent(
                user_message
            )
        return True
    if target_phase == "resume_optimize":
        flags = (session_state.get("gates") or {}).get("flags") or {}
        return bool(flags.get("optimize_confirmed"))
    return False


def resolve_analyze_target_phase(
    result: dict[str, Any],
    session_state: dict[str, Any],
) -> str | None:
    """合并声明的 pipeline_phase 和由 workers 推断出的阶段，选择更靠后的阶段。"""
    from career_os.harness.pipeline_routing import (
        get_current_phase,
        infer_pipeline_phase_from_workers,
    )

    current = get_current_phase(session_state) or "explore"
    declared = result.get("pipeline_phase")
    if declared and declared not in PIPELINE_PHASES:
        declared = None
    inferred = infer_pipeline_phase_from_workers(
        list(result.get("workers") or []), session_state
    )
    best: str | None = None
    best_rank = PHASE_RANK.get(current, 0)
    for phase in (declared, inferred):
        if not phase or phase not in PIPELINE_PHASES:
            continue
        rank = PHASE_RANK.get(phase, -1)
        if rank > best_rank:
            best_rank = rank
            best = phase
    return best


def maybe_advance_phase_from_analyze(
    result: dict[str, Any],
    session_state: dict[str, Any],
    user_message: str,
) -> str:
    """当分析结果请求前进时持久化阶段，并返回用于 Worker 过滤的阶段。"""
    from career_os.harness.pipeline_routing import get_current_phase, is_pipeline_session

    current = get_current_phase(session_state) or "explore"
    if not is_pipeline_session(session_state):
        return current
    gates = session_state.get("gates") or {}
    if gates.get("pending"):
        return current

    meta = TaskStore().get_list_meta(session_state.get("list_id") or "")
    if meta and meta.get("status") == "ready" and current == "explore":
        return current

    target = resolve_analyze_target_phase(result, session_state)
    if not target or PHASE_RANK.get(target, -1) <= PHASE_RANK.get(current, -1):
        return current
    if not can_enter_pipeline_phase(target, session_state, user_message):
        return current

    list_id = session_state.get("list_id")
    if list_id:
        apply_list_phase(list_id, target)
        session_state["last_phase_transition"] = {
            "from_phase": current,
            "to_phase": target,
            "source": "analyze",
        }
    return target
