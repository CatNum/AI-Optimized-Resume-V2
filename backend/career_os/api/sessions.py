from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from career_os.harness.executor import Harness
from career_os.platform.tool.handlers.outputs import dedupe_outputs_index
from career_os.platform.store.profile import ProfileStore
from career_os.platform.store.session import SessionStore
from career_os.platform.store.task import TaskStore

router = APIRouter(prefix="/v1")
harness = Harness()


class NewSessionResponse(BaseModel):
    session_id: str


class PingResponse(BaseModel):
    session_id: str
    last_activity_at: str


class OnboardingRequest(BaseModel):
    basic: dict[str, Any] | None = None
    intent: dict[str, Any] | None = None
    preference_tags: dict[str, Any] | None = None


@router.post("/sessions/new", response_model=NewSessionResponse)
def new_session():
    store = SessionStore()
    session_id = store.create_session()
    return {"session_id": session_id}


@router.post("/sessions/{session_id}/ping", response_model=PingResponse)
def ping_session(session_id: str):
    from datetime import UTC, datetime

    store = SessionStore()
    state = store.get_state(session_id)
    if not state.get("last_activity_at"):
        raise HTTPException(status_code=404, detail="session_not_found")
    now = datetime.now(UTC).isoformat()
    store.update_state(session_id, {"last_activity_at": now})
    return {"session_id": session_id, "last_activity_at": now}


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
