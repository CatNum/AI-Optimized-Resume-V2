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
    """判断当前会话是否是 pipeline 模式。

    session_state（会话状态）保存 list_type（列表类型）。
    返回值为 True 表示当前对话运行在阶段化 pipeline 中。
    """
    return session_state.get("list_type") == "pipeline"


def is_pipeline_explore_phase(session_state: dict[str, Any]) -> bool:
    """is_pipeline_explore_phase（is pipeline explore phase）的函数说明。

    session_state（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    if not is_pipeline_session(session_state):
        return False
    return get_current_phase(session_state) == "explore"


def infer_pipeline_phase_from_workers(
    workers: list[str],
    session_state: dict[str, Any],
) -> str:
    """根据 Worker 列表推断 pipeline 阶段。

    workers（工作者列表）是候选调度结果；session_state（会话状态）提供当前阶段兜底。
    返回值是 resume_optimize、resume_strategy、jd_analysis、market 或 explore。
    """
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
    """把普通分析结果转换为 pipeline 分析结果。

    result（分析结果）包含 workers 和可选 pipeline_phase；
    session_state（会话状态）用于推断当前阶段并应用阶段规则。
    返回值固定包含 list_type=pipeline、workers 和 pipeline_phase。
    """
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
    """get_pipeline_meta（get pipeline meta）的函数说明。

    session_state（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    if session_state.get("list_type") != "pipeline":
        return None
    list_id = session_state.get("list_id")
    if not list_id:
        return None
    return TaskStore().get_list_meta(list_id)


def get_current_phase(session_state: dict[str, Any]) -> str | None:
    """读取当前 pipeline 阶段。

    session_state（会话状态）提供 list_type 和 list_id。
    返回值是 TaskStore 中记录的 current_phase；如果是 pipeline 但没有元数据，则兜底为 explore。
    """
    meta = get_pipeline_meta(session_state)
    if not meta:
        if is_pipeline_session(session_state):
            return "explore"
        return None
    return meta.get("current_phase") or "explore"


def is_pipeline_explore_phase(session_state: dict[str, Any]) -> bool:
    """is_pipeline_explore_phase（is pipeline explore phase）的函数说明。

    session_state（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    return (
        session_state.get("list_type") == "pipeline"
        and get_current_phase(session_state) == "explore"
    )


def pipeline_analyze_payload(
    session_state: dict[str, Any],
    user_message: str = "",
) -> dict[str, Any]:
    """构造给 Coordinator LLM 的 pipeline 分析负载。

    session_state（会话状态）提供当前阶段、门禁 flags 和 list_id；
    user_message（用户消息）用于判断是否已有 JD 上下文。
    返回值包含当前阶段、允许 Worker、里程碑和阶段推进策略说明。
    """
    from career_os.harness.pipeline_jd_context import has_jd_context

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
        "has_jd_context": has_jd_context(session_state, user_message),
        "phase_advance_policy": (
            "pipeline_phase 表示本轮用户意图对应的目标阶段，可 forward 于 current_phase；"
            "填写后系统会先推进阶段再按该阶段过滤 workers。"
            "用户询问简历策略、说明在做的 Agent 项目、或要求按 JD 改简历时，"
            "若 current_phase 为 jd_analysis，应设 pipeline_phase=resume_strategy、workers=[\"strategy\"]。"
            "workers 与 pipeline_phase 须一致，勿在 jd_analysis 阶段单独派 strategy 而不改 phase。"
        ),
    }


def filter_workers_for_pipeline(
    workers: list[str],
    session_state: dict[str, Any],
    *,
    phase: str | None = None,
) -> list[str]:
    """filter_workers_for_pipeline（filter workers for pipeline）的函数说明。

    workers（参数）、session_state（参数）、phase（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
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
    """强制执行 pipeline 阶段和 Worker 过滤规则。

    result（分析结果）是 LLM 或规则给出的候选 workers/pipeline_phase；
    session_state（会话状态）提供当前阶段、门禁和 JD 前置条件；
    user_message（用户消息）用于判断是否可推进阶段。
    返回值会过滤不属于当前阶段的 Worker，并在必要时返回阻断标记。
    """
    if session_state.get("list_type") != "pipeline":
        return result
    from career_os.harness.pipeline_phase_advance import (
        PHASE_RANK,
        maybe_advance_phase_from_analyze,
    )

    current_phase = maybe_advance_phase_from_analyze(
        result, session_state, user_message
    )
    inferred_phase = result.get("pipeline_phase") or infer_pipeline_phase_from_workers(
        result.get("workers") or [], session_state
    )
    pipeline_phase = (
        inferred_phase if inferred_phase in PIPELINE_PHASES else current_phase
    )
    if PHASE_RANK.get(pipeline_phase, -1) < PHASE_RANK.get(current_phase, 0):
        pipeline_phase = current_phase
    requested_workers = list(result.get("workers") or [])
    workers = filter_workers_for_pipeline(
        requested_workers, session_state, phase=current_phase
    )
    out: dict[str, Any] = {
        "workers": workers,
        "list_type": "pipeline",
        "pipeline_phase": pipeline_phase,
    }

    if current_phase in JD_PHASES and workers:
        ready, reason = check_jd_prerequisites(session_state)
        if not ready:
            return {
                "workers": [],
                "list_type": "pipeline",
                "jd_prerequisite_blocked": True,
                "jd_block_reason": reason or "explore",
                "pipeline_phase": pipeline_phase,
            }

    if current_phase == "resume_optimize":
        flags = (session_state.get("gates") or {}).get("flags") or {}
        if not flags.get("optimize_confirmed"):
            return {
                "workers": [],
                "list_type": "pipeline",
                "pipeline_phase": pipeline_phase,
            }

    if (
        pipeline_phase != "explore"
        and current_phase == "explore"
        and not is_explore_gate_confirmed(session_state)
        and (workers or requested_workers)
    ):
        return {
            "workers": [],
            "list_type": "pipeline",
            "pipeline_phase": pipeline_phase,
            "explore_gate_required": True,
        }

    return out


def pipeline_fallback_workers(
    user_message: str,
    session_state: dict[str, Any],
) -> dict[str, Any] | None:
    """按规则兜底推断 pipeline Worker。

    user_message（用户消息）用于匹配初探、JD、策略、优化等意图；
    session_state（会话状态）提供当前阶段、prior_results 和 gates.flags。
    返回值是经过 enforce_pipeline_phase_rules 处理的分析结果；无法判断时返回 None。
    """
    if session_state.get("list_type") != "pipeline":
        return None
    suggested = session_state.pop("intent_suggested_workers", None)
    if suggested:
        return enforce_pipeline_phase_rules(
            {"workers": list(suggested)}, session_state, user_message
        )
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
        k in user_message
        for k in ("策略", "继续", "下一步", "制定", "优化", "改简历", "项目", "agent")
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
    """尝试从用户消息中应用 JD 指纹变更。

    session_id（会话标识）用于定位当前会话；session_state（会话状态）保存
    list_type、list_id、pipeline_phase 等 pipeline 运行信息；user_message（用户消息）
    是用户本轮输入，可能包含新的 JD 文本或 JD 相关意图。

    这个函数只在 pipeline 的 market（市场分析）或 jd_analysis（JD 分析）阶段生效。
    当用户输入被判断为 JD 意图时，会用 jd_fingerprint（JD 指纹）计算当前消息的指纹，
    再通过 apply_jd_fingerprint_change（应用 JD 指纹变更）处理 JD 是否变化。
    如果 JD 指纹发生变化，底层会负责同步会话/list 的相关状态；本函数返回更新后的
    session_state（会话状态）。
    """
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
