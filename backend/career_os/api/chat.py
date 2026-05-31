import json
from typing import Any, AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from career_os.agents.graphs.coordinator import run_coordinator_turn
from career_os.agents.graphs.workers.registry import build_harness_worker_runner
from career_os.harness.executor import Harness
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


def _determine_workers(message: str, session_state: dict[str, Any]) -> list[str]:
    text = message.lower()
    if "jd" in text or "岗位" in message or "job" in text:
        return ["market", "opportunity"]
    if "初探" in message or "explore" in text:
        return ["identity", "capability"]
    if "优化" in message or "resume" in text:
        flags = (session_state.get("gates") or {}).get("flags") or {}
        if flags.get("optimize_confirmed"):
            return ["resume", "asset"]
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
    pending = _determine_workers(body.message, state)
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
