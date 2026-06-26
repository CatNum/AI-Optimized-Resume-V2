from dataclasses import dataclass
from typing import Any

from career_os.harness.pipeline_gates import (
    PipelineGateError,
    advance_current_phase,
    apply_proposed_work_tasks,
    ensure_milestone_works,
    jump_to_phase,
)
from career_os.platform.store.session import SessionStore
from career_os.platform.store.task import TaskStore, TaskStoreError


@dataclass
class TaskToolError:
    """TaskToolError（TaskToolError）的项目代码结构说明。

    该类封装当前模块中的一组相关状态或行为，供业务代码、测试代码或运行时流程复用。"""
    code: str
    message: str


def _store_error(err: TaskStoreError) -> TaskToolError:
    """_store_error（内部函数 store error）的函数说明。

    err（参数）用于向该函数传入运行所需的数据。

    该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
    return TaskToolError(code=err.code, message=err.message)


def _gate_error(err: PipelineGateError) -> TaskToolError:
    """_gate_error（内部函数 gate error）的函数说明。

    err（参数）用于向该函数传入运行所需的数据。

    该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
    return TaskToolError(code=err.code, message=err.message)


def _sync_state_list_id(session_id: str, list_id: str | None) -> None:
    """_sync_state_list_id（内部函数 sync state list id）的函数说明。

    session_id（参数）、list_id（参数）用于向该函数传入运行所需的数据。

    该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
    SessionStore().update_state(session_id, {"list_id": list_id})


def create_task_list(actor: str, args: dict[str, Any]) -> TaskToolError | dict[str, Any]:
    """create_task_list（create task list）的函数说明。

    actor（参数）、args（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
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
    """create_task（create task）的函数说明。

    actor（参数）、args（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    if actor != "coordinator":
        return TaskToolError("tool_not_allowed", "create_task is coordinator-only")
    store = TaskStore()
    result = store.create_task(
        args["list_id"],
        args["task_id"],
        args.get("subject") or args.get("title", ""),
        kind=args.get("kind", "work"),
        worker_id=args.get("worker_id"),
        parent_milestone_id=args.get("parent_milestone_id"),
        pipeline_phase=args.get("pipeline_phase"),
        description=args.get("description"),
        sort_order=args.get("sort_order"),
        blocked_by=args.get("blocked_by"),
        requires_user_confirm=args.get("requires_user_confirm"),
    )
    if isinstance(result, TaskStoreError):
        return _store_error(result)
    return {"task": result}


def get_task(actor: str, args: dict[str, Any]) -> TaskToolError | dict[str, Any]:
    """get_task（get task）的函数说明。

    actor（参数）、args（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    if actor != "coordinator":
        return TaskToolError("tool_not_allowed", "get_task is coordinator-only")
    store = TaskStore()
    task = store.get_task(args["list_id"], args["task_id"])
    if task is None:
        return TaskToolError("task_not_found", f"Task {args['task_id']} not found")
    return {"task": task}


def jump_to_phase_tool(actor: str, args: dict[str, Any]) -> TaskToolError | dict[str, Any]:
    """jump_to_phase_tool（jump to phase tool）的函数说明。

    actor（参数）、args（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    if actor != "coordinator":
        return TaskToolError("tool_not_allowed", "jump_to_phase is coordinator-only")
    session_id = args.get("session_id")
    if not session_id:
        return TaskToolError("session_required", "session_id required")
    session_store = SessionStore()
    state = session_store.get_state(session_id)
    list_id = args.get("list_id") or state.get("list_id")
    if not list_id:
        return TaskToolError("list_not_found", "No pipeline list for session")
    result = jump_to_phase(session_id, list_id, args["target_phase"], state)
    if isinstance(result, PipelineGateError):
        return _gate_error(result)
    session_store.update_state(session_id, state)
    return result


def advance_current_phase_tool(
    actor: str, args: dict[str, Any]
) -> TaskToolError | dict[str, Any]:
    """advance_current_phase_tool（advance current phase tool）的函数说明。

    actor（参数）、args（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    if actor != "coordinator":
        return TaskToolError(
            "tool_not_allowed", "advance_current_phase is coordinator-only"
        )
    session_id = args.get("session_id")
    if not session_id:
        return TaskToolError("session_required", "session_id required")
    session_store = SessionStore()
    state = session_store.get_state(session_id)
    list_id = args.get("list_id") or state.get("list_id")
    if not list_id:
        return TaskToolError("list_not_found", "No pipeline list for session")
    target = args.get("target_phase", "resume_optimize")
    result = advance_current_phase(session_id, list_id, target, state)
    if isinstance(result, PipelineGateError):
        return _gate_error(result)
    return result


def ensure_milestone_works_tool(
    actor: str, args: dict[str, Any]
) -> TaskToolError | dict[str, Any]:
    """ensure_milestone_works_tool（ensure milestone works tool）的函数说明。

    actor（参数）、args（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    allowed = {"coordinator", "identity", "capability", "market", "opportunity", "strategy", "resume", "asset"}
    if actor not in allowed:
        return TaskToolError("tool_not_allowed", "ensure_milestone_works not allowed")
    session_store = SessionStore()
    state: dict[str, Any] = {}
    session_id = args.get("session_id")
    if session_id:
        state = session_store.get_state(session_id)
    list_id = args.get("list_id") or state.get("list_id")
    if not list_id:
        return TaskToolError("list_not_found", "list_id required")
    phase = args.get("phase")
    if not phase:
        meta = TaskStore().get_list_meta(list_id)
        phase = (meta or {}).get("current_phase")
    if not phase:
        return TaskToolError("invalid_phase", "phase required")
    result = ensure_milestone_works(list_id, phase, session_state=state)
    if isinstance(result, PipelineGateError):
        return _gate_error(result)
    return result


def apply_proposed_work_tasks_tool(
    actor: str, args: dict[str, Any]
) -> TaskToolError | dict[str, Any]:
    """apply_proposed_work_tasks_tool（apply proposed work tasks tool）的函数说明。

    actor（参数）、args（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    if actor not in {"coordinator"}:
        return TaskToolError(
            "tool_not_allowed",
            "apply_proposed_work_tasks is coordinator-only",
        )
    session_id = args.get("session_id")
    if not session_id:
        return TaskToolError("session_required", "session_id required")
    state = SessionStore().get_state(session_id)
    list_id = args.get("list_id") or state.get("list_id")
    if not list_id:
        return TaskToolError("list_not_found", "No pipeline list for session")
    proposals = args.get("proposals") or args.get("proposed_work_tasks") or []
    result = apply_proposed_work_tasks(list_id, proposals, state)
    if isinstance(result, PipelineGateError):
        return _gate_error(result)
    return result


def list_tasks(actor: str, args: dict[str, Any]) -> TaskToolError | dict[str, Any]:
    """list_tasks（list tasks）的函数说明。

    actor（参数）、args（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
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
    """start_task_list（start task list）的函数说明。

    actor（参数）、args（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
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
    """abandon_task_list（abandon task list）的函数说明。

    actor（参数）、args（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
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
    """claim_task（claim task）的函数说明。

    actor（参数）、args（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    if actor != "coordinator":
        return TaskToolError("tool_not_allowed", "claim_task is coordinator-only")
    store = TaskStore()
    result = store.claim_task(args["list_id"], args["task_id"])
    if isinstance(result, TaskStoreError):
        return _store_error(result)
    return {"task": result}


def complete_task(actor: str, args: dict[str, Any]) -> TaskToolError | dict[str, Any]:
    """complete_task（complete task）的函数说明。

    actor（参数）、args（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
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
    """apply_proposed_task_completions（apply proposed task completions）的函数说明。

    actor（参数）、args（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
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
