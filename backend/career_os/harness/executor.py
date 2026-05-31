from typing import Any

from career_os.harness.delegate import check_delegate_rules, delegate_worker as run_delegate_worker
from career_os.harness.errors import HarnessError
from career_os.harness.gate import match_gate_intent as run_match_gate_intent
from career_os.platform.trace.writer import TraceWriter
from career_os.platform.tool.handlers.browser_fetch import browser_fetch
from career_os.platform.tool.handlers.outputs import delete_output, register_outputs_index
from career_os.platform.tool.handlers.profile import (
    apply_proposed_patches,
    profile_get,
    profile_patch,
)
from career_os.platform.tool.handlers.resume_html import write_resume_html
from career_os.platform.tool.handlers.resume_read import resume_read
from career_os.platform.tool.handlers.task import (
    apply_proposed_task_completions,
    claim_task,
    complete_task,
    create_task,
    create_task_list,
    list_tasks,
)
from career_os.platform.tool.registry import (
    COORDINATOR_TOOLS,
    WORKER_BUSINESS_TOOLS,
    WORKER_META_TOOLS,
    ToolRegistry,
)


class Harness:
    def __init__(self, trace_writer: TraceWriter | None = None) -> None:
        self.tools = ToolRegistry()
        self.trace = trace_writer or TraceWriter()
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
        self.tools.register("create_task_list", create_task_list, actors={"coordinator"})
        self.tools.register("create_task", create_task, actors={"coordinator"})
        self.tools.register("list_tasks", list_tasks, actors={"coordinator"})
        self.tools.register("claim_task", claim_task, actors={"coordinator"})
        self.tools.register("complete_task", complete_task, actors={"coordinator"})
        self.tools.register(
            "apply_proposed_task_completions",
            apply_proposed_task_completions,
            actors={"coordinator"},
        )
        self.tools.register(
            "match_gate_intent",
            self._match_gate_intent_handler,
            actors={"coordinator"},
        )
        self.tools.register("write_resume_html", write_resume_html, actors={"resume"})
        self.tools.register("resume_read", resume_read, actors={"capability", "resume"})
        self.tools.register(
            "register_outputs_index",
            register_outputs_index,
            actors={"asset"},
        )
        self.tools.register("delete_output", delete_output, actors={"asset"})
        self.tools.register(
            "browser_fetch",
            browser_fetch,
            actors={"market", "opportunity"},
        )

    @staticmethod
    def _match_gate_intent_handler(actor: str, args: dict[str, Any]) -> dict[str, Any]:
        return run_match_gate_intent(
            args.get("user_message", ""),
            args.get("pending_gate"),
        )

    def execute_tool(
        self,
        actor: str,
        tool_name: str,
        args: dict[str, Any],
        *,
        session_id: str | None = None,
    ) -> Any | HarnessError:
        if not self._tool_visible_to_actor(actor, tool_name):
            return HarnessError("tool_not_allowed", f"{actor} cannot use {tool_name}")
        try:
            import time

            started = time.perf_counter()
            result = self.tools.execute(actor, tool_name, args)
            status = "error" if hasattr(result, "code") else "ok"
            self.trace.emit(
                "tool.call",
                session_id=session_id,
                actor=actor,
                tool_name=tool_name,
                status=status,
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
        except (KeyError, PermissionError) as exc:
            self.trace.emit(
                "tool.call",
                session_id=session_id,
                actor=actor,
                tool_name=tool_name,
                status="error",
                detail={"message": str(exc)},
            )
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

    def delegate_worker(
        self,
        actor: str,
        worker_id: str,
        goal: str,
        session_state: dict[str, Any],
        *,
        context: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> Any | HarnessError:
        result = run_delegate_worker(
            actor,
            worker_id,
            goal,
            session_state,
            context=context,
            trace=self.trace,
            session_id=session_id,
        )
        return result

    def check_delegate_rules(
        self, worker_id: str, session_state: dict[str, Any]
    ) -> HarnessError | None:
        return check_delegate_rules(worker_id, session_state)
