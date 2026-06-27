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
    """判断 Worker 结构化输出是否表示阶段片段完成。"""
    return explore_phase_status(structured) == PHASE_SEGMENT_COMPLETE


def prior_worker_segment_complete(
    prior_results: dict[str, Any], worker_id: str
) -> bool:
    """判断历史 Worker 结果中某个 Worker 是否已完成 segment。"""
    structured = (prior_results or {}).get(worker_id)
    if not isinstance(structured, dict):
        return False
    return structured_segment_complete(structured)


def infer_phase_after_repeat_decline(prior_results: dict[str, Any]) -> str:
    """推断用户拒绝重复初探后应停留的阶段。"""
    # opportunity 已完成说明 JD 分析链路已经走过，拒绝重探后回到 jd_analysis。
    if prior_worker_segment_complete(prior_results, "opportunity"):
        return "jd_analysis"
    # 否则从市场阶段继续。
    return "market"


def apply_list_phase(list_id: str, phase: str) -> TaskStoreError | None:
    """更新任务列表当前阶段。"""
    return TaskStore().set_current_phase(list_id, phase)


def phase_after_worker_segment_complete(
    worker_id: str, structured: dict[str, Any] | None
) -> str | None:
    """根据 Worker 完成结果推断下一阶段。"""
    if not structured_segment_complete(structured):
        return None
    return WORKER_SEGMENT_PHASE.get(worker_id)


def finalize_explore_path_exit(
    session_state: dict[str, Any], gates: dict[str, Any]
) -> None:
    """确认退出探索阶段并固化完成状态。"""
    # 先更新内存态闭环，表示完成 gate 已通过。
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

    # completed_at（完成时间）用于后续判断探索是否过期或是否需要重复初探。
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
        # 记录 intake_baseline（初探基线），以后 intake 发生变化时可判断是否需要重新探索。
        patches.append({"path": "exploration.intake_baseline", "value": intake, "op": "set"})
    try:
        ProfileStore().patch(patches)
    except ValueError:
        # 即使 profile 持久化暂时不可用，也保留当前会话的完成状态。
        pass


def reopen_explore_after_gate_reject(
    session_state: dict[str, Any], gates: dict[str, Any]
) -> None:
    """用户拒绝探索完成 gate 后重新打开探索阶段。"""
    # 清空当前 gate，并记录用户希望继续探索。
    gates["pending"] = None
    flags = dict(gates.get("flags") or {})
    flags.pop("fresh_pass", None)
    flags["explore_continue_requested"] = True
    gates["flags"] = flags
    session_state["gates"] = gates
    set_explore_gate_confirmed(session_state, False)

    # 重置闭环中必需 Worker 的完成状态，让 Coordinator 后续重新派发探索 Worker。
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
        # 有任务列表时，同步持久化 current_phase，保持 session_state 和 TaskStore 一致。
        apply_list_phase(list_id, "explore")
        session_state["pipeline_phase"] = "explore"


def on_explore_complete_confirmed(list_id: str) -> str:
    """用户确认完成初探后推进到市场阶段。"""
    apply_list_phase(list_id, "market")
    return "market"


def on_explore_repeat_declined(
    list_id: str, prior_results: dict[str, Any]
) -> str:
    """用户拒绝重复初探后恢复到合适的后续阶段。"""
    phase = infer_phase_after_repeat_decline(prior_results)
    apply_list_phase(list_id, phase)
    return phase
