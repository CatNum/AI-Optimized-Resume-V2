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
    """
    Harness（运行时工具门面）负责统一注册、授权和执行 Coordinator 与 Worker 可调用工具。
    """

    def __init__(self, trace_writer: TraceWriter | None = None) -> None:
        """初始化对象。"""
        # 初始化工具注册表和 trace writer，然后集中登记所有可调用工具。
        self.tools = ToolRegistry()
        self.trace = trace_writer or TraceWriter()
        self._register_tools()

    def _register_tools(self) -> None:
        """登记tools。"""
        # Worker 业务工具按 WORKER_BUSINESS_TOOLS 白名单开放，避免 Worker 看到不该调用的工具。
        worker_actors = set(WORKER_BUSINESS_TOOLS.keys())
        self.tools.register("profile_patch", profile_patch, actors=worker_actors)
        # Coordinator 专属工具负责全局状态、任务列表和 gate 流程推进。
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
        # gate 匹配通过 Harness 暴露，方便 Coordinator 统一记录和复用。
        self.tools.register(
            "match_gate_intent",
            self._match_gate_intent_handler,
            actors={"coordinator"},
        )
        # 简历、产物、浏览器和 skill 工具只开放给对应 Worker。
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
        """处理match gate intent handler。"""
        # ToolRegistry 会传入 actor；gate 匹配本身只需要用户消息和当前 pending gate。
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
        """执行tool。"""
        # 先按 actor + tool_name 做可见性检查，防止绕过 ToolRegistry 的角色白名单。
        if not self._tool_visible_to_actor(actor, tool_name):
            return HarnessError("tool_not_allowed", f"{actor} cannot use {tool_name}")
        try:
            import time

            # 复制调用参数并补入 session_id，避免修改调用方传入的 args。
            started = time.perf_counter()
            call_args = dict(args)
            if session_id is not None:
                call_args.setdefault("session_id", session_id)
            result = self.tools.execute(actor, tool_name, call_args)
            status = "error" if hasattr(result, "code") else "ok"
            # 工具正常返回时记录 tool.call trace，包括状态和耗时。
            self.trace.emit(
                "tool.call",
                session_id=session_id,
                actor=actor,
                tool_name=tool_name,
                status=status,
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
        except (KeyError, PermissionError) as exc:
            # 未注册工具或权限错误统一转成 HarnessError，同时写入失败 trace。
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
        """处理tool visible to actor。"""
        # Coordinator 只能看到全局编排工具。
        if actor == "coordinator":
            return tool_name in COORDINATOR_TOOLS
        # Worker 元工具对所有业务 Worker 开放。
        if tool_name in WORKER_META_TOOLS:
            return actor in WORKER_BUSINESS_TOOLS
        # profile_patch 有字段级校验，但仍只允许业务 Worker 调用。
        if tool_name == "profile_patch":
            return actor in WORKER_BUSINESS_TOOLS
        # 其他业务工具按 Worker 维度白名单判断。
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
        """委托worker。"""
        # Worker 委托统一进入 delegate 层，由 delegate rules 先做前置条件和上下文检查。
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
        """检查delegate rules。"""
        # 暴露只读检查入口，供测试或调用方提前判断 Worker 是否可委托。
        return check_delegate_rules(worker_id, session_state)
