from typing import Any, TypedDict


class WorkerState(TypedDict, total=False):
    worker_id: str
    goal: str
    context: dict[str, Any]
    session_state: dict[str, Any]
    iteration: int
    max_iterations: int
    messages: list[dict[str, Any]]
    structured_output: dict[str, Any]
    status: str
    error: str | None
