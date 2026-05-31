import re
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from career_os.api.explore_intake import (
    ExploreIntakeRequest,
    get_explore_intake_status,
    submit_explore_intake,
)
from career_os.harness.executor import Harness
from career_os.platform.tool.handlers.outputs import dedupe_outputs_index
from career_os.harness.orchestrator import ChatOrchestrator
from career_os.harness.session_activity import build_session_activity
from career_os.platform.store.profile import ProfileStore
from career_os.platform.store.session import SessionStore
from career_os.platform.store.task import TaskStore

router = APIRouter(prefix="/v1")
harness = Harness()
orchestrator = ChatOrchestrator()

_SESSION_ID_RE = re.compile(r"^sess_[0-9a-f]{32}$")


def _validate_session_id(session_id: str) -> None:
    if not session_id.startswith("sess_") or not _SESSION_ID_RE.match(session_id):
        raise HTTPException(status_code=400, detail="invalid_session_id")


def _session_not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="session_not_found")


def _enrich_row(store: SessionStore, row: dict[str, Any]) -> dict[str, Any]:
    state = store.get_state(row["session_id"])
    activity = build_session_activity(state)
    return {
        **row,
        "expired": SessionStore.is_expired(state),
        "activity_headline": activity.get("headline"),
    }


def _index_row(store: SessionStore, session_id: str) -> dict[str, Any] | None:
    if not store.session_exists(session_id):
        return None
    index = store.load_index()
    row = next(
        (r for r in index.get("sessions", []) if r.get("session_id") == session_id),
        None,
    )
    if row is None:
        store.touch_index(session_id)
        index = store.load_index()
        row = next(
            (r for r in index.get("sessions", []) if r.get("session_id") == session_id),
            None,
        )
    return row


def _sort_sessions(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def activity_key(row: dict[str, Any]) -> str:
        return row.get("last_activity_at") or ""

    non_archived = [r for r in rows if not r.get("archived")]
    archived = [r for r in rows if r.get("archived")]
    non_archived.sort(key=activity_key, reverse=True)
    archived.sort(key=activity_key, reverse=True)
    return non_archived + archived


class NewSessionResponse(BaseModel):
    session_id: str


class PingResponse(BaseModel):
    session_id: str
    last_activity_at: str


class OnboardingRequest(BaseModel):
    basic: dict[str, Any] | None = None
    intent: dict[str, Any] | None = None
    preference_tags: dict[str, Any] | None = None


class PatchSessionRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=32)
    archived: bool | None = None


@router.get("/sessions")
def list_sessions(
    q: str | None = None,
    archived: str | None = Query(default="false"),
):
    store = SessionStore()
    index = store.load_index()
    if not index.get("sessions"):
        store.rebuild_index()
        index = store.load_index()

    rows = list(index.get("sessions", []))
    archived_filter = (archived or "false").lower()
    if archived_filter == "true":
        rows = [r for r in rows if r.get("archived")]
    elif archived_filter != "all":
        rows = [r for r in rows if not r.get("archived")]

    if q:
        needle = q.casefold()
        rows = [
            r
            for r in rows
            if needle in (r.get("title") or "").casefold()
            or needle in (r.get("preview") or "").casefold()
        ]

    enriched = [_enrich_row(store, row) for row in rows]
    return {"sessions": _sort_sessions(enriched)}


@router.get("/sessions/{session_id}")
def get_session(session_id: str):
    _validate_session_id(session_id)
    store = SessionStore()
    row = _index_row(store, session_id)
    if row is None:
        raise _session_not_found()
    payload = _enrich_row(store, row)
    return payload


@router.get("/sessions/{session_id}/messages")
def get_session_messages(session_id: str):
    _validate_session_id(session_id)
    store = SessionStore()
    if not store.session_exists(session_id):
        raise _session_not_found()
    return {"messages": store.load_messages_full(session_id)}


@router.post("/sessions/{session_id}/generate-title")
def generate_session_title(
    session_id: str,
    force: bool = Query(default=False),
):
    from career_os.agents.lc.client import llm_enabled
    from career_os.platform.store.session_title import maybe_generate_title

    _validate_session_id(session_id)
    if not llm_enabled():
        raise HTTPException(status_code=503, detail="llm_unavailable")
    store = SessionStore()
    if not store.session_exists(session_id):
        raise _session_not_found()
    row = _index_row(store, session_id)
    if row is None:
        raise _session_not_found()
    if not force and row.get("title_source") == "user":
        raise HTTPException(status_code=409, detail="title_locked")
    maybe_generate_title(session_id, store, force=force)
    row = _index_row(store, session_id)
    assert row is not None
    return _enrich_row(store, row)


@router.patch("/sessions/{session_id}")
def patch_session(session_id: str, body: PatchSessionRequest):
    _validate_session_id(session_id)
    if body.title is None and body.archived is None:
        raise HTTPException(status_code=400, detail="empty_patch_body")
    store = SessionStore()
    if not store.session_exists(session_id):
        raise _session_not_found()
    _index_row(store, session_id)
    try:
        store.patch_index(
            session_id,
            title=body.title,
            archived=body.archived,
        )
    except KeyError:
        raise _session_not_found() from None
    row = _index_row(store, session_id)
    assert row is not None
    return _enrich_row(store, row)


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str):
    _validate_session_id(session_id)
    store = SessionStore()
    if not store.session_exists(session_id):
        raise _session_not_found()
    store.delete_session(session_id)
    return {"ok": True}


@router.post("/sessions/new", response_model=NewSessionResponse)
def new_session():
    store = SessionStore()
    session_id = store.create_session()
    return {"session_id": session_id}


@router.post("/sessions/{session_id}/ping", response_model=PingResponse)
def ping_session(session_id: str):
    from datetime import UTC, datetime

    _validate_session_id(session_id)
    store = SessionStore()
    state = store.get_state(session_id)
    if not state.get("last_activity_at"):
        raise HTTPException(status_code=404, detail="session_not_found")
    if SessionStore.is_expired(state):
        raise HTTPException(status_code=410, detail="session_expired")
    now = datetime.now(UTC).isoformat()
    store.update_state(session_id, {"last_activity_at": now})
    return {"session_id": session_id, "last_activity_at": now}


@router.get("/sessions/{session_id}/context")
def session_context(session_id: str):
    _validate_session_id(session_id)
    store = SessionStore()
    state = store.get_state(session_id)
    if not state.get("last_activity_at"):
        raise HTTPException(status_code=404, detail="session_not_found")
    _, meta = store.load_messages_for_coordinator(session_id)
    return {
        **orchestrator.context_usage_payload(meta),
        "session_activity": build_session_activity(state),
    }


@router.get("/profile/explore-intake/status")
def explore_intake_status():
    return get_explore_intake_status()


@router.post("/profile/explore-intake")
def explore_intake(body: ExploreIntakeRequest):
    return submit_explore_intake(body)


@router.post("/profile/onboarding")
def profile_onboarding(body: OnboardingRequest):
    store = ProfileStore()
    patches: list[dict[str, Any]] = []
    if body.basic:
        for key, value in body.basic.items():
            patches.append({"path": f"basic.{key}", "value": value, "op": "set"})
    if body.intent:
        for key, value in body.intent.items():
            patches.append({"path": f"intent.{key}", "value": value, "op": "set"})
    if body.preference_tags:
        patches.append(
            {"path": "preference_tags", "value": body.preference_tags, "op": "set"}
        )
    if patches:
        store.patch(patches)
    return {"ok": True}


@router.get("/profile")
def get_profile():
    store = ProfileStore()
    return store.get(
        ["basic", "intent", "exploration", "career", "strategy", "preference_tags"]
    )


@router.get("/tasks")
def get_tasks():
    tasks_dir = TaskStore()._tasks_dir  # noqa: SLF001
    active_path = tasks_dir / "_active.json"
    if not active_path.exists():
        return {"tasks": []}
    import json

    active = json.loads(active_path.read_text(encoding="utf-8"))
    list_id = active.get("list_id")
    if not list_id:
        return {"tasks": []}
    return {"list_id": list_id, "tasks": TaskStore().list_tasks(list_id)}


@router.get("/outputs")
def list_outputs():
    profile = ProfileStore()
    raw = profile.get(["outputs_index"]).get("outputs_index", [])
    deduped = dedupe_outputs_index(raw)
    if len(deduped) != len(raw):
        profile.patch([{"path": "outputs_index", "value": deduped, "op": "set"}])
    return {"outputs_index": deduped}


@router.delete("/outputs/{encoded_path:path}")
def delete_output(encoded_path: str):
    from pathlib import Path

    path = Path(encoded_path)
    result = harness.execute_tool("asset", "delete_output", {"path": str(path)})
    if hasattr(result, "code"):
        raise HTTPException(status_code=400, detail=result.message)
    return result
