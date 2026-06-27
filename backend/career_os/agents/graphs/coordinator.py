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

WorkerRunner = Callable[[str, str, dict[str, Any], dict[str, Any]], dict[str, Any]]
"""WorkerRunner（工作者运行函数）描述 Coordinator 调用 Worker 的统一函数签名。"""

_LEGACY_SESSION_LIST_TYPES = frozenset({"explore", "jd"})


def _compact_prior_result(worker_id: str, structured: dict[str, Any]) -> dict[str, Any]:
    """压缩 Worker 历史结果。

    worker_id（工作者标识）用于决定需要保留哪些关键字段；
    structured（结构化输出）是 Worker 完整输出。返回值只保留后续路由和合成需要的
    phase_status、user_visible_summary、gate_prompt 等轻量字段，避免 session_state 过大。
    """
    if not isinstance(structured, dict):
        return {}
    keep_keys = {"phase_status", "user_visible_summary", "gate_prompt"}
    if worker_id == "opportunity":
        keep_keys |= {"recommendation", "jd_fingerprint"}
    if worker_id == "resume":
        keep_keys |= {"html_deliveries"}
    if worker_id == "asset":
        keep_keys |= {"html_deliveries", "reuse_recommendation"}
    return {k: structured.get(k) for k in keep_keys if k in structured}


def _sync_session_list_type_from_analysis(
    session_state: dict[str, Any],
    result: dict[str, Any],
) -> None:
    """根据分析结果同步会话列表类型。

    session_state（会话状态）会被原地更新；result（分析结果）可能包含 list_type。
    该函数确保已有 pipeline/list_id 的会话继续保持 pipeline 类型。
    """
    if session_state.get("list_type") == "pipeline" or session_state.get("list_id"):
        session_state["list_type"] = "pipeline"
        return
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
    """记录 Coordinator 分析阶段 trace。

    harness（运行时工具门面）提供 trace.emit；session_id（会话标识）关联当前会话；
    source（来源）说明路由来自 llm、fallback、queue 等；
    workers（工作者列表）是本轮待调度 Worker；list_type（列表类型）标记 pipeline 等类型。
    """
    trace = getattr(harness, "trace", None)
    if trace is None:
        return
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
    """默认 Worker runner。

    worker_id（工作者标识）、goal（目标）、session_state（会话状态）和 context（上下文）
    保持真实 runner 签名兼容。返回值是一个最小 completed 结果，主要用于未注入 runner 的场景。
    """
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
    """构建 Coordinator 状态图。

    harness（运行时工具门面）负责委托 Worker、记录 trace 和执行权限控制；
    worker_runner（工作者运行函数）可注入真实 ReAct runner 或测试 runner。
    返回值是编译后的 LangGraph 图，包含 analyze、delegate、synthesize 三个节点。
    """
    runner = worker_runner or _default_worker_runner

    def analyze(state: CoordinatorState) -> CoordinatorState:
        """分析当前用户消息并决定下一步 Worker。

        state（协调器状态）包含用户消息、会话状态、待执行 Worker 队列等。
        返回值是更新后的 CoordinatorState：可能设置 current_worker_id，也可能直接进入合成。
        """
        # 如果 停止委派
        if state.get("stop_delegate"):
            return state
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
        # 不需要重新填写初探 intake
        if not needs_repeat_intake(session_state):
            session_state.pop("explore_intake_blocked", None)
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
            """应用一次路由分析结果。

            result（分析结果）可能来自 LLM、fallback 或 continuation。
            返回值是可执行的 workers（工作者列表）；如果命中 JD/初探阻断，会更新
            session_state 并返回空列表。
            """
            nonlocal session_state
            if not result:
                return []
            if result.get("jd_prerequisite_blocked"):
                session_state["jd_prerequisite_blocked"] = True
                session_state["jd_block_reason"] = result.get("jd_block_reason")
                return []
            if result.get("explore_intake_blocked"):
                session_state["explore_intake_blocked"] = True
                _sync_session_list_type_from_analysis(session_state, result)
                return []
            if result.get("explore_repeat_blocked"):
                session_state["explore_repeat_blocked"] = True
                _sync_session_list_type_from_analysis(session_state, result)
                return []
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

        planned = plan_explore_worker_dispatch(pending, session_state)

        # planned（计划调度结果）为空时不立即委托 Worker，保留 pending_workers 给后续轮次或合成逻辑处理。
        if not pending:
            return {
                **state,
                "session_state": session_state,
                "current_worker_id": None,
                "pending_workers": [],
            }
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
        """委托当前 Worker 执行任务。

        state（协调器状态）需要包含 current_worker_id。函数会选择适合 Worker 的聊天历史、
        附加档案记忆，先经过 harness.delegate_worker 做权限/上下文处理，再调用 runner。
        返回值会写入 last_worker_result、prior_results、pending_workers 和 stop_delegate。
        """
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
        request_context = state.get("request_context") or {}
        if request_context:
            delegate_context.update(request_context)
        attach_profile_memory_to_context(
            delegate_context,
            state.get("user_message", ""),
            session_state,
            worker_id=worker_id,
        )
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
            block_reason = parse_jd_b1_block_reason(result.message)
            if block_reason:
                session_state["jd_prerequisite_blocked"] = True
                session_state["jd_block_reason"] = block_reason
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

        structured = worker_result.get("structured_output") or {}
        if worker_result.get("status") == "completed" and supports_explore_guidance(worker_id):
            persist_worker_guidance(session_state, worker_id, structured)
        gate_prompt = structured.get("gate_prompt")
        explore_closure = mark_worker_done(
            session_state.get("explore_closure"),
            worker_id,
            structured_output=structured,
        )
        session_state["explore_closure"] = explore_closure

        if worker_result.get("status") == "completed":
            list_id = session_state.get("list_id")
            if list_id:
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
        """合成本轮最终回复。

        state（协调器状态）提供 session_state、last_worker_result 和 delegate_count。
        函数会优先处理门禁、JD 前置阻断、初探信息表、探索完成确认等确定性回复；
        否则使用 Worker 的 user_visible_summary 或阶段感知草稿。返回值写入 synthesis_text。
        """
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
            gate = structured["gate_prompt"]
            gate_name = gate.get("name") or gate.get("gate_name")
            prompt = gate.get("prompt") or structured.get("user_visible_summary", "")
            text = append_gate_reply_hint(prompt, gate_name)
            gates = dict(session_state.get("gates") or {})
            gates["pending"] = {"name": gate_name, "prompt": prompt}
            session_state["gates"] = gates
        elif session_state.get("jd_prerequisite_blocked"):
            text = jd_prerequisites_draft(session_state.get("jd_block_reason"))
        elif session_state.get("explore_repeat_blocked"):
            prompt = explore_repeat_draft()
            text = append_gate_reply_hint(prompt, "explore_repeat")
            gates = dict(session_state.get("gates") or {})
            gates["pending"] = {"name": "explore_repeat", "prompt": prompt}
            session_state["gates"] = gates
            session_state.pop("explore_repeat_blocked", None)
        elif session_state.get("explore_intake_blocked") and compute_needs_full_explore(
            ProfileStore().get(["exploration", "intent"]), session_state
        ):
            text = explore_intake_draft()
        elif session_state.pop("explore_guidance_reveal_pending", False):
            text = format_revealed_options(session_state.get("explore_guidance") or {})
        else:
            if state.get("delegate_count", 0) == 0 and not structured:
                if explore_flow_active(session_state):
                    text = explore_continue_synthesis_draft(session_state)
                else:
                    text = build_phase_synthesis_draft(
                        state.get("user_message", ""), session_state
                    )
            elif worker_id := (last.get("worker_id") or state.get("current_worker_id")):
                if supports_explore_guidance(worker_id) and structured:
                    text = build_explore_guidance_synthesis_draft(structured, session_state)
                else:
                    text = structured.get("user_visible_summary") or "已完成本轮处理。"
            else:
                text = structured.get("user_visible_summary") or "已完成本轮处理。"

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
        """决定 analyze 节点之后的路由。

        state（协调器状态）如果没有 current_worker_id 或已 stop_delegate，则进入 synthesize；
        否则进入 delegate。返回值是下一个节点名。
        """
        if state.get("stop_delegate") or not state.get("current_worker_id"):
            return "synthesize"
        return "delegate"

    def route_after_delegate(state: CoordinatorState) -> str:
        """决定 delegate 节点之后的路由。

        state（协调器状态）如果停止分发或无 pending_workers，则进入 synthesize；
        否则回到 analyze 继续选择下一个 Worker。返回值是下一个节点名。
        """
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
    """运行一轮 Coordinator 对话。

    harness（运行时工具门面）提供委托、权限和 trace 能力；
    session_id（会话标识）关联当前会话；session_state（会话状态）保存业务状态；
    user_message（用户消息）是本轮输入；chat_history（聊天历史）提供上下文；
    messages_meta（消息元数据）提供上下文统计；pending_workers（待执行工作者）可预置队列；
    worker_runner（工作者运行函数）可替换真实 Worker；request_context（请求上下文）传给 Worker。
    返回值是图执行后的 CoordinatorState，包含 synthesis_text 和更新后的 session_state。
    """
    worker_registry = WorkerRegistry()
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
    graph = build_coordinator_graph(harness, worker_runner=worker_runner)
    return graph.invoke(initial)
