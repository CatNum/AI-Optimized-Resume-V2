from dataclasses import dataclass
from typing import Any, Callable

ToolHandler = Callable[[str, dict[str, Any]], Any]


@dataclass
class ToolDefinition:
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
    "claim_task",
    "complete_task",
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
    def __init__(self) -> None:
        self._handlers: dict[str, ToolDefinition] = {}

    def register(
        self, name: str, handler: ToolHandler, *, actors: set[str]
    ) -> None:
        self._handlers[name] = ToolDefinition(name=name, actors=actors, handler=handler)

    def is_allowed(self, actor: str, tool_name: str) -> bool:
        tool = self._handlers.get(tool_name)
        if tool is None:
            return False
        return actor in tool.actors

    def execute(self, actor: str, tool_name: str, args: dict[str, Any]) -> Any:
        tool = self._handlers.get(tool_name)
        if tool is None:
            raise KeyError(tool_name)
        if actor not in tool.actors:
            raise PermissionError(f"{actor} cannot call {tool_name}")
        return tool.handler(actor, args)
