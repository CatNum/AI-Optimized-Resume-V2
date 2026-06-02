import json
from datetime import UTC, datetime
from typing import Any, AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from career_os.agents.graphs.coordinator import run_coordinator_turn
from career_os.agents.graphs.workers.registry import build_harness_worker_runner
from career_os.agents.lc.client import llm_enabled, stream_text
from career_os.agents.lc.models import LLMRole
from career_os.agents.lc.coordinator_llm import build_synthesis_messages
from career_os.harness.executor import Harness
from career_os.harness.explore_intake import explore_intake_submitted
from career_os.harness.gate import match_gate_intent
from career_os.harness.pipeline_gates import (
    PipelineGateError,
    advance_current_phase,
    set_explore_gate_confirmed,
)
from career_os.platform.store.task import TaskStore
from career_os.harness.orchestrator import ChatOrchestrator
from career_os.harness.session_activity import build_session_activity
from career_os.platform.store.profile import ProfileStore
from career_os.platform.store.session import SessionStore
from career_os.runtime.sse import format_sse, stream_tokens

router = APIRouter(prefix="/v1")
harness = Harness()
orchestrator = ChatOrchestrator()


class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str
    attachments: list[dict[str, Any]] | None = None


def _apply_pending_gate(message: str, session_state: dict[str, Any]) -> list[str] | None:
    session_state.pop("gate_clarify_pending", None)
    gates = dict(session_state.get("gates") or {})
    pending = gates.get("pending")
    if not pending:
        return None

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
        if gate_name == "explore_complete":
            explore = dict(session_state.get("explore_closure") or {})
            explore["gate_pending"] = False
            explore["completed"] = True
            session_state["explore_closure"] = explore
            set_explore_gate_confirmed(session_state, True)
            flags["fresh_pass"] = True
            gates["flags"] = flags
            session_state["gates"] = gates
            profile = ProfileStore().get(["exploration", "basic", "intent", "resume"])
            exploration = dict(profile.get("exploration") or {})
            intake = exploration.get("intake") or {}
            exploration["intake_baseline"] = dict(intake)
            exploration["completed_at"] = exploration.get("completed_at") or datetime.now(
                UTC
            ).isoformat()
            ProfileStore().patch(
                [
                    {"path": "exploration.intake_baseline", "value": dict(intake), "op": "set"},
                    {"path": "exploration.completed_at", "value": exploration["completed_at"], "op": "set"},
                ]
            )
            list_id = session_state.get("list_id")
            if list_id:
                TaskStore().clear_works_for_phase(list_id, "explore")
            return []
        if gate_name == "explore_repeat":
            flags["explore_repeat_accepted"] = True
            profile = ProfileStore().get(["exploration"])
            intake = (profile.get("exploration") or {}).get("intake") or {}
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
        gates["pending"] = None
        if gate_name == "explore_repeat":
            flags["explore_repeat_declined"] = True
            if explore_intake_submitted():
                set_explore_gate_confirmed(session_state, True)
            gates["flags"] = flags
        session_state["gates"] = gates
        return []

    if pending and not match.get("matched"):
        session_state["gate_clarify_pending"] = True
        session_state["gates"] = gates
    return []


async def _chat_stream(
    body: ChatRequest,
    session_id: str,
    begin: dict[str, Any],
    meta: dict[str, Any],
) -> AsyncIterator[str]:
    session_store = SessionStore()
    state = session_store.get_state(session_id)
    state["session_id"] = session_id

    yield format_sse("session", {"session_id": session_id})

    if begin.get("recommend_new_session"):
        yield format_sse(
            "history_notice",
            orchestrator.context_usage_payload(meta),
        )

    session_store.append_message(session_id, "user", body.message)
    chat_history, meta = session_store.load_chat_history(session_id)
    pending = _apply_pending_gate(body.message, state)
    if pending is None:
        pending = []
    context: dict[str, Any] = {}
    if "resume" in pending:
        context["selected_optimization_levels"] = ["标准", "进取"]
        context["html_deliveries"] = []
    if "asset" in pending and state.get("prior_results", {}).get("resume"):
        context["run_kind"] = "register"
        context["html_deliveries"] = state["prior_results"]["resume"].get(
            "html_deliveries", []
        )

    result = run_coordinator_turn(
        harness,
        session_id=session_id,
        session_state=state,
        user_message=body.message,
        chat_history=chat_history,
        messages_meta=meta,
        pending_workers=pending,
        worker_runner=build_harness_worker_runner(harness),
    )
    session_store.update_state(session_id, result["session_state"])

    if result["session_state"].get("explore_intake_blocked"):
        yield format_sse("explore_intake", {"required": True})

    draft = result.get("synthesis_draft") or result.get("synthesis_text") or "已完成处理。"

    if llm_enabled():
        from career_os.platform.store.session import slice_synthesize_chat_history

        history_syn = slice_synthesize_chat_history(chat_history)
        system, user = build_synthesis_messages(
            body.message,
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

    session_store.append_message(session_id, "assistant", text)

    _, meta_after = session_store.load_chat_history(session_id)
    context_usage = orchestrator.context_usage_payload(meta_after)
    context_usage["session_activity"] = build_session_activity(result["session_state"])

    yield format_sse("done", {"finish_reason": "stop", "context_usage": context_usage})
    orchestrator.end_chat(session_id)


@router.post("/chat")
async def chat(body: ChatRequest):
    session_store = SessionStore()
    session_id = body.session_id or session_store.create_session()
    state = session_store.get_state(session_id)
    state["session_id"] = session_id
    _, meta = session_store.load_chat_history(session_id)
    begin = orchestrator.begin_chat(session_id, state, meta)
    if hasattr(begin, "code"):
        if begin.code == "session_expired":
            raise HTTPException(status_code=410, detail={"code": begin.code, "message": begin.message})
        if begin.code == "chat_in_progress":
            raise HTTPException(status_code=409, detail={"code": begin.code, "message": begin.message})

    return StreamingResponse(_chat_stream(body, session_id, begin, meta), media_type="text/event-stream")
