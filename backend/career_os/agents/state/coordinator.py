from typing import Any, TypedDict


class CoordinatorState(TypedDict, total=False):
    messages: list[dict[str, str]]
    messages_meta: dict[str, Any]
    session_id: str
    session_state: dict[str, Any]
    worker_index: list[dict[str, Any]]
    pending_workers: list[str]
    current_worker_id: str | None
    last_worker_result: dict[str, Any] | None
    stop_delegate: bool
    synthesis_text: str
    synthesis_draft: str
    delegate_count: int
    user_message: str
    request_context: dict[str, Any]
