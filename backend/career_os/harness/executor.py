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
from career_os.platform.tool.handlers.skill import list_skills, load_skill
from career_os.platform.tool.handlers.task import (
    abandon_task_list,
    advance_current_phase_tool,
    apply_proposed_task_completions,
    apply_proposed_work_tasks_tool,
    claim_task,
    complete_task,
    create_task,
    create_task_list,
    ensure_milestone_works_tool,
    get_task,
    jump_to_phase_tool,
    list_tasks,
    start_task_list,
)
from career_os.platform.tool.registry import (
    COORDINATOR_TOOLS,
    WORKER_BUSINESS_TOOLS,
    WORKER_META_TOOLS,
    ToolRegistry,
)


class Harness:
    """Harness（Harness）的项目代码结构说明。

    该类封装当前模块中的一组相关状态或行为，供业务代码、测试代码或运行时流程复用。"""
    def __init__(self, trace_writer: TraceWriter | None = None) -> None:
        """__init__（初始化对象）的函数说明。

        trace_writer（参数）用于向该函数传入运行所需的数据。

        该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
        self.tools = ToolRegistry()
        self.trace = trace_writer or TraceWriter()
        self._register_tools()

    def _register_tools(self) -> None:
        """_register_tools（内部函数 register tools）的函数说明。

        该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
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
        self.tools.register("start_task_list", start_task_list, actors={"coordinator"})
        self.tools.register("abandon_task_list", abandon_task_list, actors={"coordinator"})
        self.tools.register("list_tasks", list_tasks, actors={"coordinator"})
        self.tools.register("get_task", get_task, actors={"coordinator"})
        self.tools.register("jump_to_phase", jump_to_phase_tool, actors={"coordinator"})
        self.tools.register(
            "advance_current_phase",
            advance_current_phase_tool,
            actors={"coordinator"},
        )
        worker_actors = set(WORKER_BUSINESS_TOOLS.keys())
        self.tools.register(
            "ensure_milestone_works",
            ensure_milestone_works_tool,
            actors={"coordinator", *worker_actors},
        )
        self.tools.register(
            "apply_proposed_work_tasks",
            apply_proposed_work_tasks_tool,
            actors={"coordinator"},
        )
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
        self.tools.register("load_skill", load_skill, actors=worker_actors)
        self.tools.register("list_skills", list_skills, actors=worker_actors)

    @staticmethod
    def _match_gate_intent_handler(actor: str, args: dict[str, Any]) -> dict[str, Any]:
        """_match_gate_intent_handler（内部函数 match gate intent handler）的函数说明。

        actor（参数）、args（参数）用于向该函数传入运行所需的数据。

        该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
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
        """execute_tool（execute tool）的函数说明。

        actor（参数）、tool_name（参数）、args（参数）、session_id（参数）用于向该函数传入运行所需的数据。

        返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
        if not self._tool_visible_to_actor(actor, tool_name):
            return HarnessError("tool_not_allowed", f"{actor} cannot use {tool_name}")
        try:
            import time

            started = time.perf_counter()
            call_args = dict(args)
            if session_id is not None:
                call_args.setdefault("session_id", session_id)
            result = self.tools.execute(actor, tool_name, call_args)
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
        """_tool_visible_to_actor（内部函数 tool visible to actor）的函数说明。

        actor（参数）、tool_name（参数）用于向该函数传入运行所需的数据。

        该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
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
        """delegate_worker（delegate worker）的函数说明。

        actor（参数）、worker_id（参数）、goal（参数）、session_state（参数）、context（参数）、session_id（参数）用于向该函数传入运行所需的数据。

        返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
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
        """check_delegate_rules（check delegate rules）的函数说明。

        worker_id（参数）、session_state（参数）用于向该函数传入运行所需的数据。

        返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
        return check_delegate_rules(worker_id, session_state)
