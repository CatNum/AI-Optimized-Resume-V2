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
from career_os.platform.tool.handlers.outputs import dedupe_outputs_index, merge_outputs_index
from career_os.harness.orchestrator import ChatOrchestrator
from career_os.harness.session_activity import build_session_activity
from career_os.platform.store.profile import ProfileStore
from career_os.platform.store.session import SessionStore
from career_os.harness.pipeline_gates import (
    compute_hard_pass,
    jump_to_phase,
)
from career_os.platform.pipeline_template import (
    hydrate_explore_completion_from_sessions,
    seed_session_explore_completion_from_profile,
    instantiate_pipeline_for_session,
)
from career_os.platform.store.task import TaskStore, TaskStoreError

router = APIRouter(prefix="/v1")
harness = Harness()
orchestrator = ChatOrchestrator()

_SESSION_ID_RE = re.compile(r"^sess_[0-9a-f]{32}$")


def _validate_session_id(session_id: str) -> None:
    """校验session id。"""
    if not session_id.startswith("sess_") or not _SESSION_ID_RE.match(session_id):
        raise HTTPException(status_code=400, detail="invalid_session_id")


def _task_error(status: int, code: str, message: str) -> HTTPException:
    """处理task error。"""
    return HTTPException(status_code=status, detail={"code": code, "message": message})


def _validate_session_id_for_tasks(session_id: str) -> None:
    """校验session id for tasks。"""
    if not session_id.startswith("sess_") or not _SESSION_ID_RE.match(session_id):
        raise _task_error(400, "invalid_session_id", "Invalid session_id")


def _session_not_found() -> HTTPException:
    """处理session not found。"""
    return HTTPException(status_code=404, detail="session_not_found")


def _enrich_row(store: SessionStore, row: dict[str, Any]) -> dict[str, Any]:
    """处理enrich row。"""
    state = store.get_state(row["session_id"])
    activity = build_session_activity(state)
    return {
        **row,
        "expired": SessionStore.is_expired(state),
        "activity_headline": activity.get("headline"),
    }


def _index_row(store: SessionStore, session_id: str) -> dict[str, Any] | None:
    """处理index row。"""
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
    """排序sessions。"""
    def activity_key(row: dict[str, Any]) -> str:
        """生成活跃时间排序键。"""
        return row.get("last_activity_at") or ""

    non_archived = [r for r in rows if not r.get("archived")]
    archived = [r for r in rows if r.get("archived")]
    non_archived.sort(key=activity_key, reverse=True)
    archived.sort(key=activity_key, reverse=True)
    return non_archived + archived


class NewSessionResponse(BaseModel):
    """
    NewSessionResponse（新会话响应）承载创建会话接口返回的会话标识。
    """

    session_id: str  # 会话标识


class PingResponse(BaseModel):
    """
    PingResponse（心跳响应）承载会话心跳接口返回的活跃状态。
    """

    session_id: str  # 会话标识
    last_activity_at: str  # 最后活跃时间


class OnboardingRequest(BaseModel):
    """
    OnboardingRequest（引导请求）承载用户首次补充画像和求职意图的数据。
    """

    basic: dict[str, Any] | None = None  # 基础画像
    intent: dict[str, Any] | None = None  # 求职意图
    preference_tags: dict[str, Any] | None = None  # 偏好标签


class PatchSessionRequest(BaseModel):
    """
    PatchSessionRequest（会话更新请求）承载修改会话标题或归档状态的数据。
    """

    title: str | None = Field(default=None, min_length=1, max_length=32)  # 标题
    archived: bool | None = None  # 是否归档


@router.get("/sessions")
def list_sessions(
    q: str | None = None,
    archived: str | None = Query(default="false"),
):
    """列出sessions。"""
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
    """读取session。"""
    _validate_session_id(session_id)
    store = SessionStore()
    row = _index_row(store, session_id)
    if row is None:
        raise _session_not_found()
    payload = _enrich_row(store, row)
    return payload


@router.get("/sessions/{session_id}/messages")
def get_session_messages(session_id: str):
    """读取session messages。"""
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
    """处理generate session title。"""
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
    """补丁更新session。"""
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
    """删除session。"""
    _validate_session_id(session_id)
    store = SessionStore()
    if not store.session_exists(session_id):
        raise _session_not_found()
    if orchestrator.is_chat_in_progress(session_id):
        raise HTTPException(status_code=409, detail="chat_in_progress")
    store.delete_session(session_id)
    return {"ok": True}


@router.post("/sessions/new", response_model=NewSessionResponse)
def new_session():
    """创建session。"""
    store = SessionStore()
    session_id = store.create_session()
    result = instantiate_pipeline_for_session(session_id)
    if isinstance(result, TaskStoreError):
        raise HTTPException(
            status_code=500,
            detail={"code": result.code, "message": result.message},
        )
    return {"session_id": session_id}


@router.post("/sessions/{session_id}/ping", response_model=PingResponse)
def ping_session(session_id: str):
    """处理ping session。"""
    from datetime import UTC, datetime

    _validate_session_id(session_id)
    store = SessionStore()
    state = store.get_state(session_id)
    if not state.get("last_activity_at"):
        raise HTTPException(status_code=404, detail="session_not_found")
    now = datetime.now(UTC).isoformat()
    store.update_state(session_id, {"last_activity_at": now})
    return {"session_id": session_id, "last_activity_at": now}


@router.get("/sessions/{session_id}/context")
def session_context(session_id: str):
    """处理session context。"""
    _validate_session_id(session_id)
    store = SessionStore()
    state = store.get_state(session_id)
    if not state.get("last_activity_at"):
        raise HTTPException(status_code=404, detail="session_not_found")
    _, meta = store.load_chat_history(session_id)
    return {
        **orchestrator.context_usage_payload(meta),
        "session_activity": build_session_activity(state),
    }


@router.get("/profile/explore-intake/status")
def explore_intake_status(session_id: str | None = Query(default=None)):
    """处理explore intake status。"""
    return get_explore_intake_status(session_id)


@router.post("/profile/explore-intake")
def explore_intake(body: ExploreIntakeRequest):
    """处理explore intake。"""
    try:
        return submit_explore_intake(body)
    except ValueError as exc:
        code = str(exc)
        if code == "session_not_found":
            raise HTTPException(status_code=404, detail="session_not_found") from exc
        if code == "invalid_session_id":
            raise HTTPException(
                status_code=400,
                detail={"code": "invalid_session_id", "message": "Invalid session_id"},
            ) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/profile/onboarding")
def profile_onboarding(body: OnboardingRequest):
    """处理profile onboarding。"""
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
    """读取profile。"""
    store = ProfileStore()
    return store.get(
        ["basic", "intent", "exploration", "career", "strategy", "preference_tags"]
    )


def _format_task_list_row(store: TaskStore, row: dict[str, Any]) -> dict[str, Any]:
    """格式化task list row。"""
    list_id = row["list_id"]
    if row.get("list_type") == "pipeline":
        tree = store.list_tasks_tree(list_id)
        if tree:
            return {
                "list_id": list_id,
                "list_type": "pipeline",
                "status": row.get("status"),
                "current_phase": tree.get("current_phase"),
                "milestones": tree.get("milestones", []),
                "tasks": [],
            }
    return row


@router.get("/tasks")
def get_tasks(session_id: str | None = Query(default=None)):
    """读取tasks。"""
    if session_id is None:
        raise _task_error(
            400,
            "session_id_required",
            "session_id query parameter is required",
        )
    _validate_session_id_for_tasks(session_id)
    store = TaskStore()
    session_store = SessionStore()
    hydrate_explore_completion_from_sessions()
    if not session_store.session_exists(session_id):
        raise _task_error(404, "session_not_found", "Session not found")
    state = session_store.get_state(session_id)
    state["session_id"] = session_id
    profile = ProfileStore().get(["exploration", "intent"])
    if seed_session_explore_completion_from_profile(state, profile):
        session_store.update_state(session_id, state)
    closure = state.get("explore_closure") or {}
    flags = (state.get("gates") or {}).get("flags") or {}
    current_list_meta = store.get_list_meta(state.get("list_id") or "")
    if (
        state.get("list_type") == "pipeline"
        and current_list_meta
        and current_list_meta.get("status") == "active"
        and current_list_meta.get("current_phase") == "explore"
        and not flags.get("explore_return_requested")
        and not flags.get("explore_continue_requested")
        and (profile.get("exploration") or {}).get("completed_at")
    ):
        list_id = state.get("list_id")
        if list_id:
            promoted = jump_to_phase(session_id, list_id, "market", state)
            if not hasattr(promoted, "code"):
                state = session_store.get_state(session_id)
                session_store.update_state(session_id, state)
    raw_lists = store.list_lists_for_session(session_id)
    lists = [_format_task_list_row(store, row) for row in raw_lists]
    active_list_id = next(
        (row["list_id"] for row in raw_lists if row.get("status") == "active"),
        None,
    )
    has_pipeline = any(item.get("list_type") == "pipeline" for item in lists)
    if has_pipeline:
        all_tasks_completed = False
    else:
        all_tasks_completed = all(not item.get("tasks") for item in lists)
    state = session_store.get_state(session_id)
    hard_pass, _ = compute_hard_pass(ProfileStore().get(["basic", "intent", "exploration", "resume"]))
    return {
        "session_id": session_id,
        "active_list_id": active_list_id,
        "lists": lists,
        "all_tasks_completed": all_tasks_completed,
        "explore_gate_confirmed": bool(state.get("explore_gate_confirmed")),
        "hard_pass": hard_pass,
        "ui_mode": "normal" if hard_pass else "weak",
    }


@router.get("/outputs")
def list_outputs(
    session_id: str | None = Query(default=None),
    kind: str | None = Query(default=None),
):
    """列出outputs。"""
    profile = ProfileStore()
    raw = profile.get(["outputs_index"]).get("outputs_index", [])
    deduped = dedupe_outputs_index(raw)
    merged = merge_outputs_index(deduped)
    if merged != deduped:
        profile.patch([{"path": "outputs_index", "value": merged, "op": "set"}])
    elif len(deduped) != len(raw):
        profile.patch([{"path": "outputs_index", "value": deduped, "op": "set"}])
    active = [entry for entry in merged if entry.get("status", "active") != "deleted"]
    if session_id:
        active = [entry for entry in active if entry.get("session_id") == session_id]
    if kind:
        active = [entry for entry in active if entry.get("kind") == kind]
    return {"outputs_index": active}


@router.delete("/outputs/{encoded_path:path}")
def delete_output(encoded_path: str):
    """删除output。"""
    from pathlib import Path

    path = Path(encoded_path)
    result = harness.execute_tool("asset", "delete_output", {"path": str(path)})
    if hasattr(result, "code"):
        raise HTTPException(status_code=400, detail=result.message)
    return result
