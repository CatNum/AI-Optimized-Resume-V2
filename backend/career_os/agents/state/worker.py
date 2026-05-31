from typing import Any, TypedDict


class WorkerState(TypedDict, total=False):
    worker_id: str
    goal: str
    context: dict[str, Any]
    messages: list[dict[str, str]]
    structured_output: dict[str, Any]
    status: str
    error: str | None
