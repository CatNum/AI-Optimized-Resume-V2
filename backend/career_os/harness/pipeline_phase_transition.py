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
    return explore_phase_status(structured) == PHASE_SEGMENT_COMPLETE


def prior_worker_segment_complete(
    prior_results: dict[str, Any], worker_id: str
) -> bool:
    structured = (prior_results or {}).get(worker_id)
    if not isinstance(structured, dict):
        return False
    return structured_segment_complete(structured)


def infer_phase_after_repeat_decline(prior_results: dict[str, Any]) -> str:
    if prior_worker_segment_complete(prior_results, "opportunity"):
        return "jd_analysis"
    return "market"


def apply_list_phase(list_id: str, phase: str) -> TaskStoreError | None:
    return TaskStore().set_current_phase(list_id, phase)


def phase_after_worker_segment_complete(
    worker_id: str, structured: dict[str, Any] | None
) -> str | None:
    if not structured_segment_complete(structured):
        return None
    return WORKER_SEGMENT_PHASE.get(worker_id)


def finalize_explore_path_exit(
    session_state: dict[str, Any], gates: dict[str, Any]
) -> None:
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
    apply_list_phase(list_id, "market")
    return "market"


def on_explore_repeat_declined(
    list_id: str, prior_results: dict[str, Any]
) -> str:
    phase = infer_phase_after_repeat_decline(prior_results)
    apply_list_phase(list_id, phase)
    return phase
