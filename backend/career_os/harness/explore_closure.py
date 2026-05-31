from typing import Any

EXPLORE_GATE_NAMES = {"explore_complete", "explore_review_complete"}
DEFAULT_REQUIRED_WORKERS = ["identity", "capability"]


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


def mark_worker_done(
    explore_closure: dict[str, Any] | None, worker_id: str
) -> dict[str, Any]:
    state = dict(explore_closure or init_explore_closure())
    required = state.get("required_workers") or DEFAULT_REQUIRED_WORKERS
    worker_done = dict(state.get("worker_done") or {})
    if worker_id in required:
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
    if worker_id in {"identity", "capability"} and gate_name in EXPLORE_GATE_NAMES:
        return f"{worker_id} must not emit explore gate_prompt (E2)"
    return None
