from dataclasses import dataclass
from typing import Any, Callable

ToolHandler = Callable[[str, dict[str, Any]], Any]


@dataclass
class ToolDefinition:
    """ToolDefinition（ToolDefinition）的项目代码结构说明。

    该类封装当前模块中的一组相关状态或行为，供业务代码、测试代码或运行时流程复用。"""
    name: str
    actors: set[str]
    handler: ToolHandler


COORDINATOR_TOOLS = {
    "delegate_worker",
    "create_task_list",
    "create_task",
    "start_task_list",
    "abandon_task_list",
    "list_tasks",
    "get_task",
    "jump_to_phase",
    "advance_current_phase",
    "ensure_milestone_works",
    "apply_proposed_work_tasks",
    "claim_task",
    "complete_task",
    "apply_proposed_task_completions",
    "profile_get",
    "apply_proposed_patches",
    "match_gate_intent",
}

WORKER_META_TOOLS = {"list_skills", "load_skill"}

WORKER_BUSINESS_TOOLS: dict[str, set[str]] = {
    "identity": {"profile_patch"},
    "capability": {"profile_patch", "resume_read"},
    "market": {"profile_patch", "browser_fetch"},
    "opportunity": {"profile_patch", "browser_fetch"},
    "strategy": {"profile_patch"},
    "resume": {"profile_patch", "resume_read", "write_resume_html"},
    "asset": {"register_outputs_index", "delete_output"},
}


class ToolRegistry:
    """ToolRegistry（ToolRegistry）的项目代码结构说明。

    该类封装当前模块中的一组相关状态或行为，供业务代码、测试代码或运行时流程复用。"""
    def __init__(self) -> None:
        """__init__（初始化对象）的函数说明。

        该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
        self._handlers: dict[str, ToolDefinition] = {}

    def register(
        self, name: str, handler: ToolHandler, *, actors: set[str]
    ) -> None:
        """register（register）的函数说明。

        name（参数）、handler（参数）、actors（参数）用于向该函数传入运行所需的数据。

        返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
        self._handlers[name] = ToolDefinition(name=name, actors=actors, handler=handler)

    def is_allowed(self, actor: str, tool_name: str) -> bool:
        """is_allowed（is allowed）的函数说明。

        actor（参数）、tool_name（参数）用于向该函数传入运行所需的数据。

        返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
        tool = self._handlers.get(tool_name)
        if tool is None:
            return False
        return actor in tool.actors

    def execute(self, actor: str, tool_name: str, args: dict[str, Any]) -> Any:
        """execute（execute）的函数说明。

        actor（参数）、tool_name（参数）、args（参数）用于向该函数传入运行所需的数据。

        返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
        tool = self._handlers.get(tool_name)
        if tool is None:
            raise KeyError(tool_name)
        if actor not in tool.actors:
            raise PermissionError(f"{actor} cannot call {tool_name}")
        return tool.handler(actor, args)
