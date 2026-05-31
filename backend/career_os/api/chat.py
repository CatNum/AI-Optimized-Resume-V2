import json
from typing import Any, AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from career_os.agents.graphs.coordinator import run_coordinator_turn
from career_os.agents.graphs.workers.registry import build_harness_worker_runner
from career_os.harness.executor import Harness
from career_os.harness.gate import match_gate_intent
from career_os.harness.orchestrator import ChatOrchestrator
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
    gates = dict(session_state.get("gates") or {})
    pending = gates.get("pending")
    if not pending:
        return None

    match = match_gate_intent(message, pending)
    flags = dict(gates.get("flags") or {})
    gate_name = match.get("gate_name") or pending.get("name")

    if match.get("matched") and match.get("intent") == "confirm":
        gates["pending"] = None
        if gate_name == "optimize_confirm":
            flags["optimize_confirmed"] = True
            gates["flags"] = flags
            session_state["gates"] = gates
            return ["resume", "asset"]
        if gate_name == "explore_complete":
            explore = dict(session_state.get("explore_closure") or {})
            explore["gate_pending"] = False
            explore["completed"] = True
            session_state["explore_closure"] = explore
            gates["flags"] = flags
            session_state["gates"] = gates
            return []
        gates["flags"] = flags
        session_state["gates"] = gates
        return []

    if match.get("matched") and match.get("intent") == "reject":
        gates["pending"] = None
        session_state["gates"] = gates
        return []

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
            {
                "trimmed": meta.get("trimmed", False),
                "usage_ratio": meta.get("usage_ratio", 0),
                "recommend_new_session": True,
            },
        )

    session_store.append_message(session_id, "user", body.message)
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
        pending_workers=pending,
        worker_runner=build_harness_worker_runner(harness),
    )
    session_store.update_state(session_id, result["session_state"])
    text = result.get("synthesis_text") or "已完成处理。"
    session_store.append_message(session_id, "assistant", text)

    async for chunk in stream_tokens(text):
        yield chunk

    gates = result["session_state"].get("gates", {})
    if gates.get("pending"):
        yield format_sse("gate", gates["pending"])

    yield format_sse("done", {"finish_reason": "stop"})
    orchestrator.end_chat(session_id)


@router.post("/chat")
async def chat(body: ChatRequest):
    session_store = SessionStore()
    session_id = body.session_id or session_store.create_session()
    state = session_store.get_state(session_id)
    state["session_id"] = session_id
    _, meta = session_store.load_messages_for_coordinator(session_id)
    begin = orchestrator.begin_chat(session_id, state, meta)
    if hasattr(begin, "code"):
        if begin.code == "session_expired":
            raise HTTPException(status_code=410, detail={"code": begin.code, "message": begin.message})
        if begin.code == "chat_in_progress":
            raise HTTPException(status_code=409, detail={"code": begin.code, "message": begin.message})

    return StreamingResponse(_chat_stream(body, session_id, begin, meta), media_type="text/event-stream")
