import json
from typing import Any, AsyncIterator, Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict

from career_os.agents.graphs.coordinator import run_coordinator_turn
from career_os.agents.graphs.workers.registry import build_harness_worker_runner
from career_os.agents.lc.client import llm_enabled, stream_text
from career_os.agents.lc.models import LLMRole
from career_os.agents.lc.coordinator_llm import build_synthesis_messages
from career_os.harness.executor import Harness
from career_os.harness.explore_intake import explore_intake_submitted
from career_os.harness.explore_intake import resolve_explore_intake
from career_os.harness.gate import match_gate_intent
from career_os.harness.micro_classifier import is_chat_only_intent
from career_os.harness.market_research_result import confirm_market_result
from career_os.harness.pipeline_gates import compute_needs_full_explore
from career_os.harness.pipeline_gates import PipelineGateError, advance_current_phase
from career_os.harness.pipeline_phase_transition import (
    finalize_explore_path_exit,
    on_explore_complete_confirmed,
    on_explore_repeat_declined,
    reopen_explore_after_gate_reject,
)
from career_os.platform.store.task import TaskStore
from career_os.platform.pipeline_template import (
    seed_session_explore_completion_from_profile,
)
from career_os.harness.chat_attachments import (
    build_request_context_from_attachments,
    enrich_user_message_with_attachments,
)
from career_os.harness.orchestrator import ChatOrchestrator
from career_os.harness.session_activity import build_session_activity
from career_os.platform.store.session import SessionStore
from career_os.platform.store.profile import ProfileStore
from career_os.platform.market_research.models import ResearchStatus
from career_os.platform.market_research.service import get_market_research_service
from career_os.runtime.sse import format_sse, stream_tokens

router = APIRouter(prefix="/v1")
harness = Harness()
orchestrator = ChatOrchestrator()


class ChatRequest(BaseModel):
    """
    ChatRequest（聊天请求）承载前端发起一轮对话时提交的输入数据。
    """

    model_config = ConfigDict(extra="forbid")

    session_id: str | None = None  # 会话标识
    message: str  # 用户消息
    attachments: list[dict[str, Any]] | None = None  # 附件列表
    market_action: Literal["start_confirmed_plan"] | None = None  # 仅允许启动当前已确认市场方案


def _apply_pending_gate(message: str, session_state: dict[str, Any]) -> list[str] | None:
    """应用pending gate。"""
    # 每轮先清理上一轮未理解 gate 的澄清标记，避免影响本轮匹配。
    session_state.pop("gate_clarify_pending", None)
    gates = dict(session_state.get("gates") or {})
    pending = gates.get("pending")
    # 没有待确认 gate 时返回 None，让调用方继续走普通 Coordinator 路由。
    if not pending:
        return None

    # 用户明确只想聊天时，不消费 gate，只标记后续合成走纯聊天回复。
    if is_chat_only_intent(message):
        session_state["chat_only_requested"] = True
        session_state["gates"] = gates
        return []

    # 先用 gate 匹配器判断用户对 pending gate 是确认、拒绝还是不明确。
    match = match_gate_intent(
        message,
        pending,
        session_id=session_state.get("session_id"),
        session_state=session_state,
        trace_writer=harness.trace,
    )
    flags = dict(gates.get("flags") or {})
    gate_name = match.get("gate_name") or pending.get("name")

    if match.get("matched") and match.get("intent") == "confirm":
        # confirm 分支会按 gate 类型推进阶段、设置 flags 或返回需要立即派发的 Worker。
        if gate_name == "market_result_confirmation":
            session_id = session_state.get("session_id")
            if not isinstance(session_id, str):
                return []
            confirmed = confirm_market_result(session_id, session_state)
            if hasattr(confirmed, "code"):
                session_state["gate_clarify_pending"] = True
                return []
            return ["opportunity"]
        gates["pending"] = None
        if gate_name == "optimize_confirm":
            flags["optimize_confirmed"] = True
            gates["flags"] = flags
            session_state["gates"] = gates
            list_id = session_state.get("list_id")
            session_id = session_state.get("session_id")
            if list_id and session_id:
                adv = advance_current_phase(session_id, list_id, "resume_optimize", session_state)
                if isinstance(adv, PipelineGateError):
                    gates["pending"] = pending
                    return []
            return ["resume", "asset"]
        if gate_name == "strategy_complete":
            flags["strategy_complete"] = True
            gates["flags"] = flags
            session_state["gates"] = gates
            gates["pending"] = {
                "name": "optimize_confirm",
                "prompt": "是否确认开始按策略优化简历？",
            }
            session_state["gates"] = gates
            return []
        if gate_name == "jd_continue_despite_not_recommended":
            flags["jd_continue_despite_not_recommended"] = True
            gates["flags"] = flags
            session_state["gates"] = gates
            return ["opportunity"]
        if gate_name == "explore_complete":
            finalize_explore_path_exit(session_state, gates)
            list_id = session_state.get("list_id")
            if list_id:
                TaskStore().clear_works_for_phase(list_id, "explore")
                on_explore_complete_confirmed(list_id)
            return []
        if gate_name == "explore_repeat":
            flags["explore_repeat_accepted"] = True
            intake = resolve_explore_intake(session_state)
            flags["explore_repeat_baseline_at"] = intake.get("submitted_at")
            gates["pending"] = None
            gates["flags"] = flags
            session_state["gates"] = gates
            session_state["explore_intake_blocked"] = True
            return []
        gates["flags"] = flags
        session_state["gates"] = gates
        return []

    if match.get("matched") and match.get("intent") == "reject":
        # reject 分支会关闭当前 gate；探索类 gate 还需要回退或固化对应阶段状态。
        gates["pending"] = None
        if gate_name == "explore_complete":
            reopen_explore_after_gate_reject(session_state, gates)
            return []
        if gate_name == "explore_repeat":
            flags["explore_repeat_declined"] = True
            gates["flags"] = flags
            if explore_intake_submitted(session_state):
                finalize_explore_path_exit(session_state, gates)
                list_id = session_state.get("list_id")
                if list_id:
                    prior = session_state.get("prior_results") or {}
                    TaskStore().clear_works_for_phase(list_id, "explore")
                    on_explore_repeat_declined(list_id, prior)
            session_state["gates"] = gates
        return []

    if pending and not match.get("matched"):
        # gate 存在但用户意图不明确时，交给 synthesize 输出澄清问题。
        session_state["gate_clarify_pending"] = True
        session_state["gates"] = gates
    return []


async def _chat_stream(
    body: ChatRequest,
    session_id: str,
    begin: dict[str, Any],
    meta: dict[str, Any],
) -> AsyncIterator[str]:
    """流式处理一轮聊天。"""
    # 先加载会话状态，并把 profile 中已有的探索完成信息同步进当前 session。
    session_store = SessionStore()
    state = session_store.get_state(session_id)
    state["session_id"] = session_id
    profile = ProfileStore().get(["exploration", "intent"])
    seed_session_explore_completion_from_profile(state, profile)
    session_store.update_state(session_id, state)

    yield format_sse("session", {"session_id": session_id})

    # 如果上下文接近上限，先通过 SSE 提醒前端建议用户开新会话。
    if begin.get("recommend_new_session"):
        yield format_sse(
            "history_notice",
            orchestrator.context_usage_payload(meta),
        )

    # 附件会先转换成请求上下文和增强后的用户消息，再一起进入 Coordinator。
    user_message = enrich_user_message_with_attachments(body.message, body.attachments)
    session_store.append_message(session_id, "user", user_message)
    chat_history, meta = session_store.load_chat_history(session_id)
    # pending gate 优先消费；没有 gate 时 pending 为空队列，后续由 Coordinator 自行分析。
    pending = _apply_pending_gate(body.message, state)
    if pending is None:
        pending = []
    request_context = build_request_context_from_attachments(body.attachments)
    if body.market_action == "start_confirmed_plan":
        artifacts = session_store.get_artifacts(session_id)
        market = artifacts.get("market") if isinstance(artifacts, dict) else {}
        request_context = {
            **request_context,
            "market_action": body.market_action,
            "active_plan_id": market.get("active_plan_id"),
        }
        pending = ["market"]

    # Coordinator 负责本轮路由、Worker 委托和确定性合成草稿。
    result = run_coordinator_turn(
        harness,
        session_id=session_id,
        session_state=state,
        user_message=user_message,
        chat_history=chat_history,
        messages_meta=meta,
        pending_workers=pending,
        worker_runner=build_harness_worker_runner(harness),
        request_context=request_context,
    )
    session_store.update_state(session_id, result["session_state"])

    # 初探信息缺失时，通过专门事件告诉前端需要展示 intake 表单。
    if result["session_state"].get("explore_intake_blocked") and compute_needs_full_explore(
        profile, result["session_state"]
    ):
        yield format_sse("explore_intake", {"required": True})

    draft = result.get("synthesis_draft") or result.get("synthesis_text") or "已完成处理。"

    # LLM 可用时用 draft + 上下文润色最终回复；不可用时直接把 draft 分块流式返回。
    if llm_enabled():
        from career_os.platform.store.session import slice_synthesize_chat_history

        history_syn = slice_synthesize_chat_history(chat_history)
        system, user = build_synthesis_messages(
            user_message,
            draft,
            result["session_state"],
            result.get("last_worker_result"),
            chat_history=history_syn,
            messages_meta=meta,
        )
        parts: list[str] = []
        for token in stream_text(system, user, role=LLMRole.COORDINATOR):
            parts.append(token)
            yield format_sse("token", {"delta": token})
        text = "".join(parts) or draft
    else:
        text = draft
        async for chunk in stream_tokens(text):
            yield chunk

    # 回复完成后写入 assistant 消息，再输出 done 事件和上下文使用情况。
    session_store.append_message(session_id, "assistant", text)

    _, meta_after = session_store.load_chat_history(session_id)
    context_usage = orchestrator.context_usage_payload(meta_after)
    context_usage["session_activity"] = build_session_activity(result["session_state"])

    yield format_sse("done", {"finish_reason": "stop", "context_usage": context_usage})
    orchestrator.end_chat(session_id)


@router.post("/chat")
async def chat(body: ChatRequest):
    """处理聊天请求。"""
    # 先合并文本和附件内容；二者都为空时直接拒绝请求。
    user_message = enrich_user_message_with_attachments(body.message, body.attachments)
    if not user_message.strip():
        raise HTTPException(status_code=400, detail="message_or_attachment_required")

    # 没有传 session_id 时创建新会话；随后加载会话状态和历史元数据。
    session_store = SessionStore()
    if body.market_action is not None and body.session_id is None:
        raise HTTPException(status_code=409, detail={"code": "market_plan_session_required"})
    session_id = body.session_id or session_store.create_session()
    state = session_store.get_state(session_id)
    state["session_id"] = session_id
    artifacts = session_store.get_artifacts(session_id)
    market = artifacts.get("market") if isinstance(artifacts, dict) else {}
    active_research_id = market.get("active_research_id")
    if isinstance(active_research_id, str) and active_research_id:
        try:
            snapshot = get_market_research_service().get_status(active_research_id, session_id)
        except KeyError:
            snapshot = None
        if snapshot is not None and snapshot.status in {
            ResearchStatus.QUEUED,
            ResearchStatus.RUNNING,
            ResearchStatus.CANCELLING,
            ResearchStatus.WAITING_USER,
        }:
            code = (
                "market_research_waiting_user"
                if snapshot.status == ResearchStatus.WAITING_USER
                else "market_research_in_progress"
            )
            raise HTTPException(status_code=409, detail={"code": code})
    if body.market_action == "start_confirmed_plan":
        plan_id = market.get("active_plan_id")
        if not isinstance(plan_id, str) or not plan_id:
            raise HTTPException(status_code=409, detail={"code": "market_plan_missing"})
        try:
            plan = get_market_research_service().plan_store.get(plan_id, session_id)
        except Exception:
            raise HTTPException(status_code=409, detail={"code": "market_plan_invalid"}) from None
        if plan.status != "confirmed" or plan.confirmed_at is None:
            raise HTTPException(status_code=409, detail={"code": "market_plan_not_confirmed"})
    _, meta = session_store.load_chat_history(session_id)
    begin = orchestrator.begin_chat(session_id, state, meta)
    # 同一会话已有流式响应未结束时，返回 409，避免并发写状态。
    if hasattr(begin, "code"):
        if begin.code == "chat_in_progress":
            raise HTTPException(status_code=409, detail={"code": begin.code, "message": begin.message})

    return StreamingResponse(_chat_stream(body, session_id, begin, meta), media_type="text/event-stream")
