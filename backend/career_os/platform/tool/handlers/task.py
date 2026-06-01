from dataclasses import dataclass
from typing import Any

from career_os.platform.store.session import SessionStore
from career_os.platform.store.task import TaskStore, TaskStoreError


@dataclass
class TaskToolError:
    code: str
    message: str


def _store_error(err: TaskStoreError) -> TaskToolError:
    return TaskToolError(code=err.code, message=err.message)


def _sync_state_list_id(session_id: str, list_id: str | None) -> None:
    SessionStore().update_state(session_id, {"list_id": list_id})


def create_task_list(actor: str, args: dict[str, Any]) -> TaskToolError | dict[str, Any]:
    if actor != "coordinator":
        return TaskToolError("tool_not_allowed", "create_task_list is coordinator-only")
    store = TaskStore()
    result = store.create_task_list(
        args["session_id"],
        list_type=args["list_type"],
        status=args.get("status", "ready"),
    )
    if isinstance(result, TaskStoreError):
        return _store_error(result)
    _sync_state_list_id(args["session_id"], result)
    return {"list_id": result}


def create_task(actor: str, args: dict[str, Any]) -> TaskToolError | dict[str, Any]:
    if actor != "coordinator":
        return TaskToolError("tool_not_allowed", "create_task is coordinator-only")
    store = TaskStore()
    task = store.create_task(
        args["list_id"],
        args["task_id"],
        args.get("subject") or args.get("title", ""),
        kind=args.get("kind", "work"),
        worker_id=args.get("worker_id"),
    )
    return {"task": task}


def list_tasks(actor: str, args: dict[str, Any]) -> TaskToolError | dict[str, Any]:
    if actor != "coordinator":
        return TaskToolError("tool_not_allowed", "list_tasks is coordinator-only")
    store = TaskStore()
    list_id = args.get("list_id")
    if not list_id:
        session_id = args.get("session_id")
        if not session_id:
            return TaskToolError("list_not_found", "list_id or session_id required")
        list_id = SessionStore().get_state(session_id).get("list_id")
        if not list_id:
            return TaskToolError("list_not_found", "No active list for session")
    tasks = store.list_tasks(list_id)
    return {"tasks": tasks}


def start_task_list(actor: str, args: dict[str, Any]) -> TaskToolError | dict[str, Any]:
    if actor != "coordinator":
        return TaskToolError("tool_not_allowed", "start_task_list is coordinator-only")
    store = TaskStore()
    list_id = args["list_id"]
    meta = store.get_task_list(list_id)
    if meta is None:
        return TaskToolError("list_not_found", f"List {list_id} not found")
    session_id = meta.get("session_id")
    if not session_id:
        return TaskToolError("list_not_found", f"List {list_id} not found")
    result = store.start_task_list(list_id)
    if isinstance(result, TaskStoreError):
        return _store_error(result)
    _sync_state_list_id(session_id, list_id)
    return {"list_id": list_id, "status": "active"}


def abandon_task_list(actor: str, args: dict[str, Any]) -> TaskToolError | dict[str, Any]:
    if actor != "coordinator":
        return TaskToolError("tool_not_allowed", "abandon_task_list is coordinator-only")
    store = TaskStore()
    list_id = args["list_id"]
    meta = store.get_task_list(list_id)
    if meta is None:
        return TaskToolError("list_not_found", f"List {list_id} not found")
    session_id = meta.get("session_id")
    result = store.abandon_task_list(list_id)
    if isinstance(result, TaskStoreError):
        return _store_error(result)
    if session_id:
        state = SessionStore().get_state(session_id)
        if state.get("list_id") == list_id:
            _sync_state_list_id(session_id, None)
    return {"ok": True, "list_id": list_id}


def claim_task(actor: str, args: dict[str, Any]) -> TaskToolError | dict[str, Any]:
    if actor != "coordinator":
        return TaskToolError("tool_not_allowed", "claim_task is coordinator-only")
    store = TaskStore()
    result = store.claim_task(args["list_id"], args["task_id"])
    if isinstance(result, TaskStoreError):
        return _store_error(result)
    return {"task": result}


def complete_task(actor: str, args: dict[str, Any]) -> TaskToolError | dict[str, Any]:
    if actor != "coordinator":
        return TaskToolError("tool_not_allowed", "complete_task is coordinator-only")
    store = TaskStore()
    result = store.complete_task(args["list_id"], args["task_id"])
    if isinstance(result, TaskStoreError):
        return _store_error(result)
    return {"ok": True, "task_id": args["task_id"]}


def apply_proposed_task_completions(
    actor: str, args: dict[str, Any]
) -> TaskToolError | dict[str, Any]:
    if actor != "coordinator":
        return TaskToolError(
            "tool_not_allowed",
            "apply_proposed_task_completions is coordinator-only",
        )
    proposed = args.get("proposed_task_completions") or []
    return {
        "proposed": proposed,
        "completed": [],
        "note": "Worker proposed completions require coordinator complete_task",
    }
