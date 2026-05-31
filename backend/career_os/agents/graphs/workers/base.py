from typing import Any, Callable

from career_os.agents.schemas.workers import validate_structured_output
from career_os.agents.state.worker import WorkerState


def run_worker_emit(
    state: WorkerState,
    *,
    raw_output: dict[str, Any] | None = None,
) -> WorkerState:
    payload = raw_output or state.get("structured_output") or {}
    validated, error = validate_structured_output(state["worker_id"], payload)
    if error:
        return {
            **state,
            "status": "failed",
            "error": error,
        }
    return {
        **state,
        "status": "completed",
        "structured_output": validated or {},
        "error": None,
    }


def finalize_worker_result(worker_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    state: WorkerState = {
        "worker_id": worker_id,
        "goal": "",
        "context": {},
        "messages": [],
        "structured_output": payload,
        "status": "pending",
    }
    emitted = run_worker_emit(state, raw_output=payload)
    return {
        "worker_id": worker_id,
        "status": emitted["status"],
        "structured_output": emitted.get("structured_output"),
        "error": emitted.get("error"),
    }


def build_stub_worker_runner(
    responses: dict[str, dict[str, Any]],
) -> Callable[[str, str, dict[str, Any], dict[str, Any]], dict[str, Any]]:
    def runner(
        worker_id: str,
        goal: str,
        session_state: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        payload = responses.get(worker_id, {"user_visible_summary": goal})
        return finalize_worker_result(worker_id, payload)

    return runner
