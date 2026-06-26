from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from career_os.harness.explore_closure import (
    DEFAULT_REQUIRED_WORKERS,
    PHASE_SEGMENT_COMPLETE,
    explore_phase_status,
)
from career_os.harness.pipeline_gates import set_explore_gate_confirmed
from career_os.platform.store.profile import ProfileStore
from career_os.platform.store.session import SessionStore
from career_os.platform.store.task import TaskStore, TaskStoreError

WORKER_SEGMENT_PHASE: dict[str, str] = {
    "market": "market",
    "opportunity": "jd_analysis",
    "strategy": "resume_strategy",
}


def structured_segment_complete(structured: dict[str, Any] | None) -> bool:
    """structured_segment_complete（structured segment complete）的函数说明。

    structured（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    return explore_phase_status(structured) == PHASE_SEGMENT_COMPLETE


def prior_worker_segment_complete(
    prior_results: dict[str, Any], worker_id: str
) -> bool:
    """prior_worker_segment_complete（prior worker segment complete）的函数说明。

    prior_results（参数）、worker_id（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    structured = (prior_results or {}).get(worker_id)
    if not isinstance(structured, dict):
        return False
    return structured_segment_complete(structured)


def infer_phase_after_repeat_decline(prior_results: dict[str, Any]) -> str:
    """infer_phase_after_repeat_decline（infer phase after repeat decline）的函数说明。

    prior_results（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    if prior_worker_segment_complete(prior_results, "opportunity"):
        return "jd_analysis"
    return "market"


def apply_list_phase(list_id: str, phase: str) -> TaskStoreError | None:
    """更新任务列表当前阶段。

    list_id（列表标识）定位 pipeline 任务列表；phase（阶段）是要写入的阶段名。
    返回值是 TaskStoreError 或 None，表示阶段写入是否失败。
    """
    return TaskStore().set_current_phase(list_id, phase)


def phase_after_worker_segment_complete(
    worker_id: str, structured: dict[str, Any] | None
) -> str | None:
    """根据 Worker 完成结果推断下一阶段。

    worker_id（工作者标识）表示刚完成的 Worker；
    structured（结构化输出）用于判断 phase_status 是否 segment_complete。
    返回值是完成该 Worker 后应推进到的 pipeline 阶段；不满足完成条件时返回 None。
    """
    if not structured_segment_complete(structured):
        return None
    return WORKER_SEGMENT_PHASE.get(worker_id)


def finalize_explore_path_exit(
    session_state: dict[str, Any], gates: dict[str, Any]
) -> None:
    """finalize_explore_path_exit（finalize explore path exit）的函数说明。

    session_state（参数）、gates（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    explore = dict(session_state.get("explore_closure") or {})
    explore["gate_pending"] = False
    explore["completed"] = True
    session_state["explore_closure"] = explore
    set_explore_gate_confirmed(session_state, True)
    flags = dict(gates.get("flags") or {})
    flags["explore_gate_confirmed"] = True
    flags["fresh_pass"] = True
    flags.pop("explore_return_requested", None)
    flags.pop("explore_continue_requested", None)
    gates["flags"] = flags
    session_state["gates"] = gates

    completed_at = datetime.now(UTC).isoformat()
    session_id = session_state.get("session_id")
    if session_id:
        SessionStore().update_state(
            session_id,
            {
                "explore_completed_at": completed_at,
            },
        )
    intake = {}
    if session_id:
        intake = (ProfileStore().get(["exploration"]).get("exploration") or {}).get(
            "intake", {}
        )
    patches = [{"path": "exploration.completed_at", "value": completed_at, "op": "set"}]
    if intake:
        patches.append({"path": "exploration.intake_baseline", "value": intake, "op": "set"})
    try:
        ProfileStore().patch(patches)
    except ValueError:
        # Keep session completion even if profile persistence is temporarily unavailable.
        pass


def reopen_explore_after_gate_reject(
    session_state: dict[str, Any], gates: dict[str, Any]
) -> None:
    """reopen_explore_after_gate_reject（reopen explore after gate reject）的函数说明。

    session_state（参数）、gates（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    gates["pending"] = None
    flags = dict(gates.get("flags") or {})
    flags.pop("fresh_pass", None)
    flags["explore_continue_requested"] = True
    gates["flags"] = flags
    session_state["gates"] = gates
    set_explore_gate_confirmed(session_state, False)

    explore = dict(session_state.get("explore_closure") or {})
    required = explore.get("required_workers") or DEFAULT_REQUIRED_WORKERS
    explore["required_workers"] = required
    explore["gate_pending"] = False
    explore["completed"] = False
    worker_done = dict(explore.get("worker_done") or {})
    for worker_id in required:
        worker_done[worker_id] = False
    explore["worker_done"] = worker_done
    session_state["explore_closure"] = explore

    list_id = session_state.get("list_id")
    if list_id:
        apply_list_phase(list_id, "explore")
        session_state["pipeline_phase"] = "explore"


def on_explore_complete_confirmed(list_id: str) -> str:
    """on_explore_complete_confirmed（on explore complete confirmed）的函数说明。

    list_id（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    apply_list_phase(list_id, "market")
    return "market"


def on_explore_repeat_declined(
    list_id: str, prior_results: dict[str, Any]
) -> str:
    """on_explore_repeat_declined（on explore repeat declined）的函数说明。

    list_id（参数）、prior_results（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    phase = infer_phase_after_repeat_decline(prior_results)
    apply_list_phase(list_id, phase)
    return phase
