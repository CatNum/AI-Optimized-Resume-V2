from typing import Any, Callable

from langgraph.graph import END, StateGraph

from career_os.agents.lc.coordinator_llm import (
    analyze_workers,
    chat_only_synthesis_draft,
    explore_intake_draft,
    explore_complete_synthesis_draft,
    explore_repeat_draft,
    fallback_analyze_workers,
    is_small_talk,
    jd_prerequisites_draft,
)
from career_os.harness.micro_classifier import is_chat_only_intent
from career_os.agents.state.coordinator import CoordinatorState
from career_os.config import settings
from career_os.harness.chat_history_scope import select_worker_chat_history
from career_os.agents.lc.coordinator_llm import build_phase_synthesis_draft
from career_os.harness.profile_memory import attach_profile_memory_to_context
from career_os.harness.pipeline_gates import compute_needs_full_explore
from career_os.platform.store.session import slice_chat_rounds
from career_os.harness.pipeline_phase_transition import (
    apply_list_phase,
    phase_after_worker_segment_complete,
)
from career_os.harness.explore_closure import (
    EXPLORE_WORKERS,
    can_set_explore_gate_pending,
    explore_continuation_analyze,
    explore_phase_status,
    is_explore_segment_complete,
    mark_worker_done,
    plan_explore_worker_dispatch,
)
from career_os.harness.session_activity import (
    explore_continue_synthesis_draft,
    explore_flow_active,
)
from career_os.harness.explore_intake import enforce_explore_intake, needs_repeat_intake
from career_os.harness.gate import append_gate_reply_hint, build_gate_clarify_text
from career_os.harness.explore_guidance import (
    build_explore_guidance_synthesis_draft,
    format_revealed_options,
    mark_explore_guidance_revealed,
    persist_worker_guidance,
    should_reveal_explore_guidance,
    supports_explore_guidance,
)
from career_os.harness.errors import HarnessError
from career_os.harness.jd_prerequisites import parse_jd_b1_block_reason
from career_os.harness.pipeline_intent_transition import apply_intent_phase_transition
from career_os.platform.worker.registry import WorkerRegistry
from career_os.platform.store.profile import ProfileStore
from career_os.platform.store.session import SessionStore
from career_os.platform.market_research.models import DirectionProposal
from career_os.platform.market_research.plans import MarketResearchPlanStore
from career_os.platform.market_research.errors import MarketResearchError

WorkerRunner = Callable[[str, str, dict[str, Any], dict[str, Any]], dict[str, Any]]
"""WorkerRunner（工作者运行函数）描述 Coordinator 调用 Worker 的统一函数签名。"""

_LEGACY_SESSION_LIST_TYPES = frozenset({"explore", "jd"})


def _compact_prior_result(worker_id: str, structured: dict[str, Any]) -> dict[str, Any]:
    """压缩 Worker 历史结果。"""
    # Worker 异常或测试替身可能返回非 dict，这里直接降级为空摘要，避免污染 session_state。
    if not isinstance(structured, dict):
        return {}
    # 先保留所有 Worker 通用的阶段状态、用户可见摘要和门禁提示。
    keep_keys = {"phase_status", "user_visible_summary", "gate_prompt"}
    # opportunity（机会分析）会产出 JD 推荐和指纹，后续 JD 链路需要继续复用。
    if worker_id == "opportunity":
        keep_keys |= {"recommendation", "jd_fingerprint"}
    # resume/asset（简历与资产 Worker）的 HTML 产物需要留给合成和页面展示。
    if worker_id == "resume":
        keep_keys |= {"html_deliveries"}
    if worker_id == "asset":
        keep_keys |= {"html_deliveries", "reuse_recommendation"}
    return {k: structured.get(k) for k in keep_keys if k in structured}


def _sync_session_list_type_from_analysis(
    session_state: dict[str, Any],
    result: dict[str, Any],
) -> None:
    """根据分析结果同步会话列表类型。"""
    # 已有 pipeline 标记或 list_id（任务列表标识）时，说明会话已经绑定任务列表，
    # 不能被旧版 explore/jd list_type 覆盖。
    if session_state.get("list_type") == "pipeline" or session_state.get("list_id"):
        session_state["list_type"] = "pipeline"
        return
    # 没有绑定 pipeline 时，才接受分析结果中的新 list_type。
    list_type = result.get("list_type")
    if list_type and list_type not in _LEGACY_SESSION_LIST_TYPES:
        session_state["list_type"] = list_type


def _emit_coordinator_analyze_trace(
    harness: Any,
    *,
    session_id: str | None,
    source: str,
    workers: list[str],
    list_type: str | None,
) -> None:
    """记录 Coordinator 分析阶段 trace。"""
    # harness（运行时工具门面）可能没有 trace 能力；没有时静默跳过，不影响主流程。
    trace = getattr(harness, "trace", None)
    if trace is None:
        return
    # detail（trace 详情）记录路由来源、候选队列和首个即将执行的 Worker，便于回放决策。
    detail: dict[str, Any] = {"source": source, "workers": workers}
    if list_type:
        detail["list_type"] = list_type
    if workers:
        detail["next_worker"] = workers[0]
    trace.emit(
        "coordinator.analyze",
        session_id=session_id,
        actor="coordinator",
        worker_id=workers[0] if workers else None,
        status="ok",
        detail=detail,
    )


def _default_worker_runner(
    worker_id: str,
    goal: str,
    session_state: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    """默认 Worker runner。"""
    return {
        "worker_id": worker_id,
        "status": "completed",
        "structured_output": {"user_visible_summary": goal},
    }


def build_coordinator_graph(
    harness: Any,
    *,
    worker_runner: WorkerRunner | None = None,
) -> Any:
    """构建 Coordinator 状态图。"""
    # 未注入真实 runner 时使用默认 runner，让图在测试或 dry-run 场景中仍可执行。
    runner = worker_runner or _default_worker_runner

    def analyze(state: CoordinatorState) -> CoordinatorState:
        """分析当前用户消息并决定下一步 Worker。"""
        # 上一节点已经要求停止委派时，analyze 不再重新路由，直接把状态交给 synthesize。
        if state.get("stop_delegate"):
            return state
        # pending_workers（待执行 Worker 队列）是跨节点传递的队列；session_state 复制后再改，
        # 避免在局部流程失败时直接修改调用方传入的原对象。
        pending = list(state.get("pending_workers") or [])
        session_state = dict(state.get("session_state") or {})
        from career_os.harness.pipeline_routing import maybe_apply_jd_fingerprint_from_message

        # 先把本轮用户消息中可能携带的 JD 指纹合并进 session_state（会话状态），
        # 再清理上一轮遗留的临时阻断标记，避免旧 gate 影响新一轮路由。
        session_state = maybe_apply_jd_fingerprint_from_message(
            state.get("session_id"),
            session_state,
            state.get("user_message", ""),
        )
        session_state.pop("jd_prerequisite_blocked", None)
        session_state.pop("jd_block_reason", None)
        session_state.pop("market_result_blocked", None)
        session_state.pop("market_result_error_code", None)
        session_state.pop("market_result_error_message", None)
        # 如果当前不是“重复初探且需要重新填表”，清理旧的 explore_intake_blocked，
        # 避免上一轮表单阻断继续影响本轮正常路由。
        if not needs_repeat_intake(session_state):
            session_state.pop("explore_intake_blocked", None)
        # 每轮 analyze 都重新判断是否展示探索选项，因此先清掉上一轮待展示标记。
        session_state.pop("explore_guidance_reveal_pending", None)

        # chat_only_requested（仅聊天请求）用于绕过 Worker 调度，直接进入 synthesize。
        if is_chat_only_intent(state.get("user_message", "")):
            session_state["chat_only_requested"] = True
            session_state.pop("gate_clarify_pending", None)
            return {
                **state,
                "session_state": session_state,
                "current_worker_id": None,
                "pending_workers": [],
                "stop_delegate": True,
            }

        # explore_guidance_reveal_pending（探索指引待展示）由 synthesize 消费，
        # 判断是否只展示可选项。
        if should_reveal_explore_guidance(state.get("user_message", ""), session_state):
            mark_explore_guidance_revealed(session_state)
            return {
                **state,
                "session_state": session_state,
                "current_worker_id": None,
                "pending_workers": [],
                "stop_delegate": True,
            }

        # history_analyze（分析用聊天历史）只保留最近若干轮对话，
        # 给意图识别使用，避免完整历史过长影响路由判断。
        history_analyze = slice_chat_rounds(
            state.get("messages") or [],
            max_rounds=settings.coordinator_analyze_max_rounds,
        )
        # apply_intent_phase_transition（应用意图阶段切换）根据用户本轮消息和短历史，
        # 判断是否需要切换 pipeline 阶段，并把阶段结果写回 session_state（会话状态）。
        intent_transition = apply_intent_phase_transition(
            state.get("user_message", ""),
            session_state,
            chat_history=history_analyze,
        )
        # applied（已应用）为 True 时，说明 session_state 已被阶段切换逻辑更新，
        # 这里把更新后的 session_state 放回 CoordinatorState（协调器状态）。
        if intent_transition.get("applied"):
            state = {**state, "session_state": session_state}

        # analysis（路由分析结果）保存 LLM 或 fallback 的 Worker 选择结果；
        # source（来源）记录结果来自 llm、fallback、queue、continuation 等路径。
        analysis: dict[str, Any] | None = None
        source: str | None = None

        def _apply_analysis(result: dict[str, Any] | None) -> list[str]:
            """应用一次路由分析结果。"""
            nonlocal session_state
            # 空分析结果表示 LLM/fallback 没有给出可用路由。
            if not result:
                return []
            # JD 前置条件不满足时，只写阻断原因，不派发 JD 链路 Worker。
            if result.get("jd_prerequisite_blocked"):
                session_state["jd_prerequisite_blocked"] = True
                session_state["jd_block_reason"] = result.get("jd_block_reason")
                return []
            if result.get("market_result_blocked"):
                session_state["market_result_blocked"] = True
                session_state["market_result_error_code"] = result.get(
                    "market_result_error_code"
                )
                session_state["market_result_error_message"] = result.get(
                    "market_result_error_message"
                )
                return []
            # 初探信息表未完成时，只记录阻断标记，让 synthesize 输出填表引导。
            if result.get("explore_intake_blocked"):
                session_state["explore_intake_blocked"] = True
                _sync_session_list_type_from_analysis(session_state, result)
                return []
            # 已完成过探索但用户尚未确认是否重走时，暂停 Worker，交给 gate 回复处理。
            if result.get("explore_repeat_blocked"):
                session_state["explore_repeat_blocked"] = True
                _sync_session_list_type_from_analysis(session_state, result)
                return []
            # 正常路由只返回 workers，同时同步 list_type，保证后续 helper 识别 pipeline 流程。
            workers = result.get("workers") or []
            _sync_session_list_type_from_analysis(session_state, result)
            return workers

        # pending_workers（待执行 Worker 队列）优先级最高；没有预置队列时，
        # 再按闲聊、LLM 路由、fallback 路由的顺序决定本轮 workers。
        if pending:
            source = "queue" if state.get("delegate_count", 0) > 0 else "preset"
        elif is_small_talk(state.get("user_message", "")):
            source = "fallback"
            pending = []
        else:
            # analyze_workers（Worker 分析器）优先尝试 LLM 路由，结合短历史和 Worker 索引选择队列。
            analysis = analyze_workers(
                state.get("user_message", ""),
                session_state,
                state.get("worker_index") or [],
                chat_history=history_analyze,
                messages_meta=state.get("messages_meta"),
            )
            if analysis is not None:
                source = "llm"
                pending = _apply_analysis(analysis)
            else:
                # LLM 没有可用结果时，再使用 fallback_analyze_workers（规则回退路由）。
                analysis = fallback_analyze_workers(
                    state.get("user_message", ""),
                    session_state,
                )
                if analysis is not None:
                    source = "fallback"
                    pending = _apply_analysis(analysis)
                else:
                    source = "none"
                    pending = []

        # explore_continuation_analyze（探索续跑分析）用于补齐尚未完成的探索段：
        # 当主路由没有给出 Worker 时，根据 explore_closure（探索闭环状态）继续派发。
        if (
            not pending
            and not session_state.get("explore_intake_blocked")
            and not is_small_talk(state.get("user_message", ""))
        ):
            continued = explore_continuation_analyze(session_state)
            if continued and continued.get("workers"):
                pending = continued["workers"]
                _sync_session_list_type_from_analysis(session_state, continued)
                source = "continuation" if source in (None, "llm", "none", "fallback") else source

        # enforce_explore_intake（强制探索信息收集）会在 Worker 执行前拦截：
        # 如果基础信息不足，清空 pending，让 synthesize 输出引导用户补信息的回复。
        if pending and not session_state.get("explore_intake_blocked"):
            intake_payload: dict[str, Any] = {"workers": pending}
            if session_state.get("list_type"):
                intake_payload["list_type"] = session_state["list_type"]
            intake_check = enforce_explore_intake(intake_payload, session_state)
            if intake_check.get("explore_intake_blocked"):
                session_state["explore_intake_blocked"] = True
                _sync_session_list_type_from_analysis(session_state, intake_check)
                pending = []
            elif intake_check.get("explore_repeat_blocked"):
                session_state["explore_repeat_blocked"] = True
                _sync_session_list_type_from_analysis(session_state, intake_check)
                pending = []
            elif not intake_check.get("workers"):
                pending = []

        state = {**state, "session_state": session_state}

        if source:
            _emit_coordinator_analyze_trace(
                harness,
                session_id=state.get("session_id"),
                source=source,
                workers=pending,
                list_type=session_state.get("list_type"),
            )

        # plan_explore_worker_dispatch（探索 Worker 调度计划）会把 identity/capability
        # 限制为一次只执行一个，防止探索闭环还没完成就越过下一个问题。
        planned = plan_explore_worker_dispatch(pending, session_state)

        # pending 为空表示本轮没有 Worker 可执行，直接进入 synthesize。
        if not pending:
            return {
                **state,
                "session_state": session_state,
                "current_worker_id": None,
                "pending_workers": [],
            }
        # planned（计划调度结果）为空时不立即委托 Worker，保留 pending_workers 给后续轮次或合成逻辑处理。
        if not planned:
            return {
                **state,
                "session_state": session_state,
                "current_worker_id": None,
                "pending_workers": pending,
            }
        return {
            **state,
            "session_state": session_state,
            "pending_workers": pending,
            "current_worker_id": planned[0],
        }

    def delegate(state: CoordinatorState) -> CoordinatorState:
        """委托当前 Worker 执行任务。"""
        # current_worker_id（当前工作者标识）为空表示没有可委托对象；stop_delegate 表示前序已要求停下。
        worker_id = state.get("current_worker_id")
        if not worker_id or state.get("stop_delegate"):
            return state

        session_state = dict(state.get("session_state") or {})
        full_history = state.get("messages") or []
        # select_worker_chat_history（选择 Worker 聊天历史）会裁剪上下文，
        # 避免把无关历史全部塞给下游 Worker。
        worker_history, scope_label = select_worker_chat_history(
            full_history,
            state.get("user_message", ""),
            state.get("messages_meta"),
        )
        delegate_context: dict[str, Any] = {
            "chat_history": worker_history,
            "chat_history_scope": scope_label,
            "messages_meta": state.get("messages_meta") or {},
        }
        # request_context（请求上下文）承载接口层额外信息，合并后统一交给 Worker。
        request_context = state.get("request_context") or {}
        if request_context:
            delegate_context.update(request_context)
        # attach_profile_memory_to_context（附加档案记忆）按当前 Worker 和阶段加载简历、
        # 市场、策略等长期记忆，减少 Worker 自行查找上下文的成本。
        attach_profile_memory_to_context(
            delegate_context,
            state.get("user_message", ""),
            session_state,
            worker_id=worker_id,
        )
        if worker_id == "market" and state.get("session_id"):
            market_artifact = SessionStore().get_artifacts(state["session_id"]).get("market")
            if isinstance(market_artifact, dict):
                # market_lifecycle（市场生命周期上下文）只暴露等待启动的方案编号，
                # 不把结果引用、确认状态或旧市场数据当成 Worker 可自行信任的业务上下文。
                delegate_context["market_lifecycle"] = {
                    "active_plan_id": market_artifact.get("active_plan_id")
                }
        # harness.delegate_worker（委托 Worker）先做权限、前置条件和上下文包装；
        # 只有它通过后才会调用真正 runner。
        result = harness.delegate_worker(
            "coordinator",
            worker_id,
            state.get("user_message", ""),
            session_state,
            session_id=state.get("session_id"),
            context=delegate_context,
        )
        if isinstance(result, HarnessError):
            session_state = dict(state.get("session_state") or {})
            # JD-B1 阻断说明 JD 链路前置条件未满足，记录阻断原因给 synthesize 生成确定性回复。
            block_reason = parse_jd_b1_block_reason(result.message)
            if block_reason:
                session_state["jd_prerequisite_blocked"] = True
                session_state["jd_block_reason"] = block_reason
            if result.code.startswith("market_"):
                session_state["market_result_blocked"] = True
                session_state["market_result_error_code"] = result.code
                session_state["market_result_error_message"] = result.message
            return {
                **state,
                "session_state": session_state,
                "stop_delegate": True,
                "last_worker_result": {"status": "failed", "error": result.message},
            }

        # runner（工作者运行函数）负责真正执行 Worker；harness.delegate_worker
        # 返回的 context（上下文）已经包含权限检查和委托层补充信息。
        worker_result = runner(
            worker_id,
            state.get("user_message", ""),
            session_state,
            result.get("context") or {},
        )
        structured = worker_result.get("structured_output") or {}
        if worker_id == "market" and worker_result.get("status") == "accepted_async":
            research_id = structured.get("research_id")
            plan_id = structured.get("plan_id")
            initial_status = structured.get("status")
            if not all(
                isinstance(value, str)
                for value in (research_id, plan_id, initial_status)
            ):
                return {
                    **state,
                    "session_state": session_state,
                    "last_worker_result": {
                        "worker_id": worker_id,
                        "status": "failed",
                        "structured_output": None,
                        "error": "invalid accepted_async market payload",
                    },
                    "stop_delegate": True,
                    "pending_workers": [],
                    "delegate_count": state.get("delegate_count", 0) + 1,
                    "current_worker_id": None,
                }
            SessionStore().patch_artifacts(
                state["session_id"],
                [
                    {
                        "path": "market.active_research_id",
                        "value": research_id,
                        "op": "set",
                    }
                ],
            )
            session_state["market_research"] = {
                "research_id": research_id,
                "plan_id": plan_id,
                "status": initial_status,
            }
            pending = list(state.get("pending_workers") or [])
            if worker_id in pending:
                pending.remove(worker_id)
            return {
                **state,
                "session_state": session_state,
                "last_worker_result": worker_result,
                "stop_delegate": True,
                "pending_workers": pending,
                "delegate_count": state.get("delegate_count", 0) + 1,
                "current_worker_id": None,
            }
        if (
            worker_id == "market"
            and worker_result.get("status") == "completed"
            and structured.get("mode") == "plan_proposal"
        ):
            try:
                proposal = structured.get("proposal") or {}
                directions = [
                    DirectionProposal.model_validate(direction)
                    for direction in proposal.get("directions") or []
                ]
                plan = MarketResearchPlanStore().create_draft(
                    state["session_id"], directions
                )
            except (MarketResearchError, ValueError) as error:
                return {
                    **state,
                    "session_state": session_state,
                    "last_worker_result": {
                        "worker_id": worker_id,
                        "status": "failed",
                        "structured_output": None,
                        "error": str(error),
                    },
                    "stop_delegate": True,
                    "pending_workers": [],
                    "delegate_count": state.get("delegate_count", 0) + 1,
                    "current_worker_id": None,
                }
            SessionStore().patch_artifacts(
                state["session_id"],
                [
                    {
                        "path": "market.active_plan_id",
                        "value": plan.plan_id,
                        "op": "set",
                    }
                ],
            )
            pending = list(state.get("pending_workers") or [])
            if worker_id in pending:
                pending.remove(worker_id)
            return {
                **state,
                "session_state": session_state,
                "last_worker_result": worker_result,
                "stop_delegate": True,
                "pending_workers": pending,
                "delegate_count": state.get("delegate_count", 0) + 1,
                "current_worker_id": None,
            }
        prior_results = dict(session_state.get("prior_results") or {})
        # prior_results（历史 Worker 结果）只保存压缩摘要，供后续 Worker 和合成阶段引用。
        if worker_result.get("status") == "completed":
            prior_results[worker_id] = _compact_prior_result(
                worker_id, worker_result.get("structured_output") or {}
            )
        session_state["prior_results"] = prior_results
        if worker_result.get("status") == "completed" and state.get("session_id"):
            structured_out = worker_result.get("structured_output") or {}
            artifact_patches: list[dict[str, Any]] = []
            # artifact_patches（产物补丁）把关键 Worker 结果同步到会话产物区，
            # 便于页面或后续流程读取结构化成果。
            if worker_id in {"market", "opportunity", "strategy"}:
                artifact_patches.append(
                    {"path": worker_id, "value": structured_out, "op": "set"}
                )
            if worker_id in {"identity", "capability"}:
                artifact_patches.append(
                    {
                        "path": f"exploration.{worker_id}",
                        "value": structured_out,
                        "op": "set",
                    }
                )
            if worker_id == "asset":
                artifact_patches.append(
                    {
                        "path": "resume_outputs",
                        "value": structured_out.get("html_deliveries") or [],
                        "op": "set",
                    }
                )
            if artifact_patches:
                SessionStore().patch_artifacts(state["session_id"], artifact_patches)

        # 支持延迟展示选项的探索 Worker 会把 guidance_options 写入 session_state，
        # 但不会立刻展示，等用户明确要“选项/例子”时再揭示。
        if worker_result.get("status") == "completed" and supports_explore_guidance(worker_id):
            persist_worker_guidance(session_state, worker_id, structured)
        # gate_prompt（门禁提示）表示 Worker 需要用户确认；一旦存在就暂停后续派发。
        gate_prompt = structured.get("gate_prompt")
        # mark_worker_done（标记探索 Worker 完成）只在探索 Worker 返回 segment_complete 时更新闭环进度。
        explore_closure = mark_worker_done(
            session_state.get("explore_closure"),
            worker_id,
            structured_output=structured,
        )
        session_state["explore_closure"] = explore_closure

        if worker_result.get("status") == "completed":
            list_id = session_state.get("list_id")
            if list_id:
                # 非探索阶段的 Worker 完成一个 segment 后，推动任务列表进入下一个 pipeline 阶段。
                advanced = phase_after_worker_segment_complete(
                    worker_id, structured
                )
                if advanced:
                    apply_list_phase(list_id, advanced)
                    session_state["pipeline_phase"] = advanced

        # stop_delegate（停止委托）控制是否继续派发下一个 Worker：
        # 有 gate_prompt、探索段未完成、或探索闭环需要用户确认时都必须先停下来合成回复。
        stop_delegate = bool(gate_prompt)
        if (
            worker_id in EXPLORE_WORKERS
            and explore_phase_status(structured) != "segment_complete"
        ):
            stop_delegate = True
        elif can_set_explore_gate_pending(explore_closure):
            stop_delegate = True

        pending = list(state.get("pending_workers") or [])
        # 普通 Worker 完成后从队列移除；探索 Worker 必须返回 segment_complete 才算完成当前片段。
        if worker_id in pending and (
            worker_id not in EXPLORE_WORKERS
            or is_explore_segment_complete(worker_id, structured)
        ):
            pending.remove(worker_id)

        return {
            **state,
            "session_state": session_state,
            "last_worker_result": worker_result,
            "stop_delegate": stop_delegate,
            "pending_workers": pending,
            "delegate_count": state.get("delegate_count", 0) + 1,
            "current_worker_id": None,
        }

    def synthesize(state: CoordinatorState) -> CoordinatorState:
        """合成本轮最终回复。"""
        session_state = dict(state.get("session_state") or {})
        last = state.get("last_worker_result") or {}
        structured = last.get("structured_output") or {}

        # gate_clarify_pending（门禁澄清待处理）优先级最高：
        # 用户需要先确认关键决策，不能被普通 Worker 摘要覆盖。
        if session_state.get("gate_clarify_pending"):
            pending_gate = (session_state.get("gates") or {}).get("pending") or {}
            text = build_gate_clarify_text(pending_gate)
            session_state.pop("gate_clarify_pending", None)
            return {
                **state,
                "session_state": session_state,
                "synthesis_text": text,
                "synthesis_draft": text,
                "last_worker_result": last or state.get("last_worker_result"),
            }

        # chat_only_requested（仅聊天请求）由 analyze 设置，这里生成不依赖 Worker 的闲聊回复。
        if session_state.pop("chat_only_requested", False):
            text = chat_only_synthesis_draft(session_state)
            return {
                **state,
                "session_state": session_state,
                "synthesis_text": text,
                "synthesis_draft": text,
                "last_worker_result": last or state.get("last_worker_result"),
            }

        from career_os.harness.explore_depth import can_offer_explore_complete
        from career_os.platform.store.profile import ProfileStore

        # 读取 profile（用户画像）用于判断当前探索深度是否足以发出“完成初探”确认。
        profile = ProfileStore().get(
            ["basic", "intent", "exploration", "resume", "capability"]
        )
        list_type = session_state.get("list_type")
        offer_explore, _diag = can_offer_explore_complete(profile, session_state)
        text: str | None = None
        # 以下分支按业务优先级合成回复：探索完成 gate、Worker 自带 gate、
        # JD 前置阻断、探索信息补齐、探索指引展示，最后才回落到普通摘要。
        if (
            list_type == "pipeline"
            and offer_explore
            and can_set_explore_gate_pending(session_state.get("explore_closure"))
        ):
            # pipeline 初探达到深度要求且闭环 Worker 都完成时，发出完成初探 gate。
            explore_prompt = explore_complete_synthesis_draft()
            text = append_gate_reply_hint(explore_prompt, "explore_complete")
            gates = dict(session_state.get("gates") or {})
            gates["pending"] = {
                "name": "explore_complete",
                "prompt": explore_prompt,
            }
            session_state["gates"] = gates
            explore = dict(session_state.get("explore_closure") or {})
            explore["gate_pending"] = True
            session_state["explore_closure"] = explore
        elif can_set_explore_gate_pending(session_state.get("explore_closure")):
            # 非 pipeline 或旧链路中，只要闭环完成且未挂 gate，也同样发出完成确认。
            explore_prompt = explore_complete_synthesis_draft()
            text = append_gate_reply_hint(explore_prompt, "explore_complete")
            gates = dict(session_state.get("gates") or {})
            gates["pending"] = {
                "name": "explore_complete",
                "prompt": explore_prompt,
            }
            session_state["gates"] = gates
            explore = dict(session_state.get("explore_closure") or {})
            explore["gate_pending"] = True
            session_state["explore_closure"] = explore
        elif structured.get("gate_prompt"):
            # Worker 自带 gate_prompt 时，把它登记为当前 pending gate，并追加标准回复格式。
            gate = structured["gate_prompt"]
            gate_name = gate.get("name") or gate.get("gate_name")
            prompt = gate.get("prompt") or structured.get("user_visible_summary", "")
            text = append_gate_reply_hint(prompt, gate_name)
            gates = dict(session_state.get("gates") or {})
            gates["pending"] = {"name": gate_name, "prompt": prompt}
            session_state["gates"] = gates
        elif session_state.get("jd_prerequisite_blocked"):
            # JD 前置条件未满足时，输出固定阻断文案，引导用户先完成 onboarding/explore。
            text = jd_prerequisites_draft(session_state.get("jd_block_reason"))
        elif session_state.get("market_result_blocked"):
            # 市场正式结果仍在运行、未确认、过期或已删除时使用 Harness 的确定性阻断说明。
            text = str(
                session_state.get("market_result_error_message")
                or "请先完成并确认当前市场调研结果，再继续岗位分析。"
            )
        elif session_state.get("explore_repeat_blocked"):
            # 用户已完成过探索但系统判断需要重走时，先询问是否重新初探。
            prompt = explore_repeat_draft()
            text = append_gate_reply_hint(prompt, "explore_repeat")
            gates = dict(session_state.get("gates") or {})
            gates["pending"] = {"name": "explore_repeat", "prompt": prompt}
            session_state["gates"] = gates
            session_state.pop("explore_repeat_blocked", None)
        elif session_state.get("explore_intake_blocked") and compute_needs_full_explore(
            ProfileStore().get(["exploration", "intent"]), session_state
        ):
            # 初探信息表缺失或重复初探需要新表单时，返回填表引导。
            text = explore_intake_draft()
        elif session_state.pop("explore_guidance_reveal_pending", False):
            # 用户明确要参考选项时，展示之前隐藏的 guidance_options。
            text = format_revealed_options(session_state.get("explore_guidance") or {})
        else:
            if state.get("delegate_count", 0) == 0 and not structured:
                # 本轮没有执行 Worker 且没有结构化结果时，按当前流程状态生成阶段草稿。
                if explore_flow_active(session_state):
                    text = explore_continue_synthesis_draft(session_state)
                else:
                    text = build_phase_synthesis_draft(
                        state.get("user_message", ""), session_state
                    )
            elif worker_id := (last.get("worker_id") or state.get("current_worker_id")):
                # 刚执行过 Worker 时优先使用 Worker 摘要；探索引导 Worker 会额外追加“可要选项”的提示。
                if supports_explore_guidance(worker_id) and structured:
                    text = build_explore_guidance_synthesis_draft(structured, session_state)
                else:
                    text = structured.get("user_visible_summary") or "已完成本轮处理。"
            else:
                text = structured.get("user_visible_summary") or "已完成本轮处理。"

        # 理论上前面所有分支都会产生 text；兜底到阶段感知草稿，保证接口永远有回复。
        if text is None:
            text = build_phase_synthesis_draft(
                state.get("user_message", ""), session_state
            )

        return {
            **state,
            "session_state": session_state,
            "synthesis_text": text,
            "synthesis_draft": text,
            "last_worker_result": last or state.get("last_worker_result"),
        }

    def route_after_analyze(state: CoordinatorState) -> str:
        """决定 analyze 节点之后的路由。"""
        # analyze 没有选出 current_worker_id，或显式 stop_delegate 时，直接生成回复。
        if state.get("stop_delegate") or not state.get("current_worker_id"):
            return "synthesize"
        return "delegate"

    def route_after_delegate(state: CoordinatorState) -> str:
        """决定 delegate 节点之后的路由。"""
        # delegate 后如果还有 pending_workers 且没有 gate/阻断，就回 analyze 继续派发下一个 Worker。
        if state.get("stop_delegate") or not state.get("pending_workers"):
            return "synthesize"
        return "analyze"

    graph = StateGraph(CoordinatorState)
    # analyze（分析节点）负责路由决策；delegate（委托节点）执行 Worker；
    # synthesize（合成节点）生成最终回复。条件边让图在多 Worker 队列中循环，直到需要回复用户。
    graph.add_node("analyze", analyze)
    graph.add_node("delegate", delegate)
    graph.add_node("synthesize", synthesize)
    graph.set_entry_point("analyze")
    graph.add_conditional_edges("analyze", route_after_analyze)
    graph.add_conditional_edges("delegate", route_after_delegate)
    graph.add_edge("synthesize", END)
    return graph.compile()


def run_coordinator_turn(
    harness: Any,
    *,
    session_id: str,
    session_state: dict[str, Any],
    user_message: str,
    chat_history: list[dict[str, str]] | None = None,
    messages_meta: dict[str, Any] | None = None,
    pending_workers: list[str] | None = None,
    worker_runner: WorkerRunner | None = None,
    request_context: dict[str, Any] | None = None,
) -> CoordinatorState:
    """运行一轮 Coordinator 对话。"""
    # WorkerRegistry（工作者注册表）提供 Coordinator 可见的 Worker 索引，供 analyze_workers 路由使用。
    worker_registry = WorkerRegistry()
    # initial（初始协调器状态）把接口入参统一整理成 LangGraph 节点之间传递的状态结构。
    initial: CoordinatorState = {
        "messages": list(chat_history or []),
        "messages_meta": dict(messages_meta or {}),
        "session_id": session_id,
        "session_state": session_state,
        "worker_index": worker_registry.get_worker_index(),
        "pending_workers": pending_workers or [],
        "user_message": user_message,
        "request_context": dict(request_context or {}),
        "stop_delegate": False,
        "delegate_count": 0,
    }
    # 构建并执行状态图：analyze 决策、delegate 执行、synthesize 产出最终回复。
    graph = build_coordinator_graph(harness, worker_runner=worker_runner)
    return graph.invoke(initial)
