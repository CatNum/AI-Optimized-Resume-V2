from dataclasses import dataclass
from typing import Any

from career_os.platform.tool.handlers.profile import (
    apply_proposed_patches,
    profile_get,
    profile_patch,
)
from career_os.platform.tool.registry import (
    COORDINATOR_TOOLS,
    WORKER_BUSINESS_TOOLS,
    WORKER_META_TOOLS,
    ToolRegistry,
)


@dataclass
class HarnessError:
    code: str
    message: str


class Harness:
    def __init__(self) -> None:
        self.tools = ToolRegistry()
        self._register_tools()

    def _register_tools(self) -> None:
        worker_actors = set(WORKER_BUSINESS_TOOLS.keys())
        self.tools.register("profile_patch", profile_patch, actors=worker_actors)
        self.tools.register(
            "apply_proposed_patches",
            apply_proposed_patches,
            actors={"coordinator"},
        )
        self.tools.register(
            "profile_get",
            profile_get,
            actors={"coordinator"},
        )

    def execute_tool(
        self, actor: str, tool_name: str, args: dict[str, Any]
    ) -> Any | HarnessError:
        if not self._tool_visible_to_actor(actor, tool_name):
            return HarnessError("tool_not_allowed", f"{actor} cannot use {tool_name}")
        try:
            result = self.tools.execute(actor, tool_name, args)
        except (KeyError, PermissionError) as exc:
            return HarnessError("tool_not_allowed", str(exc))
        if hasattr(result, "code"):
            return result
        return result

    def _tool_visible_to_actor(self, actor: str, tool_name: str) -> bool:
        if actor == "coordinator":
            return tool_name in COORDINATOR_TOOLS
        if tool_name in WORKER_META_TOOLS:
            return actor in WORKER_BUSINESS_TOOLS
        if tool_name == "profile_patch":
            return actor in WORKER_BUSINESS_TOOLS
        business = WORKER_BUSINESS_TOOLS.get(actor, set())
        return tool_name in business
