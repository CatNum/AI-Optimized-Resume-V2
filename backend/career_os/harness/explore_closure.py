from typing import Any

EXPLORE_GATE_NAMES = {"explore_complete", "explore_review_complete"}
DEFAULT_REQUIRED_WORKERS = ["identity", "capability"]
EXPLORE_WORKERS = frozenset(DEFAULT_REQUIRED_WORKERS)
PHASE_IN_PROGRESS = "in_progress"
PHASE_SEGMENT_COMPLETE = "segment_complete"
EXPLORE_DISPATCH_ORDER = ["identity", "capability"]


def init_explore_closure(
    *,
    gate_name: str = "explore_complete",
    required_workers: list[str] | None = None,
) -> dict[str, Any]:
    required = required_workers or DEFAULT_REQUIRED_WORKERS
    worker_done = {
        worker_id: worker_id not in required for worker_id in DEFAULT_REQUIRED_WORKERS
    }
    for worker_id in required:
        worker_done[worker_id] = False
    return {
        "gate_name": gate_name,
        "required_workers": required,
        "worker_done": worker_done,
        "gate_pending": False,
    }


def explore_phase_status(structured_output: dict[str, Any] | None) -> str:
    if not structured_output:
        return PHASE_IN_PROGRESS
    status = structured_output.get("phase_status")
    if status == PHASE_SEGMENT_COMPLETE:
        return PHASE_SEGMENT_COMPLETE
    return PHASE_IN_PROGRESS


def is_explore_segment_complete(
    worker_id: str, structured_output: dict[str, Any] | None
) -> bool:
    if worker_id not in EXPLORE_WORKERS:
        return True
    return explore_phase_status(structured_output) == PHASE_SEGMENT_COMPLETE


def incomplete_explore_workers(session_state: dict[str, Any]) -> list[str]:
    closure = session_state.get("explore_closure")
    if not closure:
        return list(EXPLORE_DISPATCH_ORDER)
    required = closure.get("required_workers") or DEFAULT_REQUIRED_WORKERS
    worker_done = closure.get("worker_done") or {}
    return [worker_id for worker_id in required if not worker_done.get(worker_id, False)]


def plan_explore_worker_dispatch(
    workers: list[str],
    session_state: dict[str, Any],
) -> list[str]:
    if not any(worker_id in EXPLORE_WORKERS for worker_id in workers):
        return workers
    incomplete = incomplete_explore_workers(session_state)
    if incomplete:
        return [incomplete[0]]
    ordered = [worker_id for worker_id in EXPLORE_DISPATCH_ORDER if worker_id in workers]
    return ordered[:1] if ordered else workers


def explore_continuation_analyze(session_state: dict[str, Any]) -> dict[str, Any] | None:
    from career_os.harness.pipeline_routing import get_current_phase, is_pipeline_explore_phase

    if not is_pipeline_explore_phase(session_state):
        return None
    closure = session_state.get("explore_closure") or {}
    if closure.get("completed"):
        return None
    incomplete = incomplete_explore_workers(session_state)
    if not incomplete:
        return None
    return {
        "workers": [incomplete[0]],
        "list_type": "pipeline",
        "pipeline_phase": get_current_phase(session_state) or "explore",
    }


def mark_worker_done(
    explore_closure: dict[str, Any] | None,
    worker_id: str,
    *,
    structured_output: dict[str, Any] | None = None,
) -> dict[str, Any]:
    state = dict(explore_closure or init_explore_closure())
    required = state.get("required_workers") or DEFAULT_REQUIRED_WORKERS
    worker_done = dict(state.get("worker_done") or {})
    if worker_id in required:
        if not is_explore_segment_complete(worker_id, structured_output):
            state["worker_done"] = worker_done
            return state
        worker_done[worker_id] = True
    state["worker_done"] = worker_done
    return state


def is_closure_ready(explore_closure: dict[str, Any] | None) -> bool:
    if not explore_closure:
        return False
    required = explore_closure.get("required_workers") or DEFAULT_REQUIRED_WORKERS
    worker_done = explore_closure.get("worker_done") or {}
    return all(worker_done.get(worker_id, False) for worker_id in required)


def can_set_explore_gate_pending(explore_closure: dict[str, Any] | None) -> bool:
    if not explore_closure:
        return False
    if explore_closure.get("completed"):
        return False
    if explore_closure.get("gate_pending"):
        return False
    return is_closure_ready(explore_closure)


def validate_worker_structured_output(
    worker_id: str, structured_output: dict[str, Any]
) -> str | None:
    gate_prompt = structured_output.get("gate_prompt")
    if not gate_prompt:
        return None
    gate_name = gate_prompt.get("name") or gate_prompt.get("gate_name")
    if worker_id in EXPLORE_WORKERS and gate_name in EXPLORE_GATE_NAMES:
        return f"{worker_id} must not emit explore gate_prompt (E2)"
    return None
