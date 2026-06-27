from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from career_os.platform.pipeline_constants import PHASE_TO_MILESTONE_ID
from career_os.harness.explore_closure import init_explore_closure
from career_os.platform.store.profile import ProfileStore
from career_os.platform.store.session import SessionStore
from career_os.platform.store.task import TaskStore, TaskStoreError


def repo_root() -> Path:
    """定位仓库根目录。"""
    return Path(__file__).resolve().parents[3]


def load_pipeline_milestones() -> list[dict[str, Any]]:
    """加载pipeline milestones。"""
    path = repo_root() / "config" / "pipeline_milestones.json"
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def hydrate_explore_completion_from_sessions(
    profile_store: ProfileStore | None = None,
    session_store: SessionStore | None = None,
) -> bool:
    """处理hydrate explore completion from sessions。"""
    profile_store = profile_store or ProfileStore()
    session_store = session_store or SessionStore()
    profile = profile_store.get(["exploration"])
    exploration = profile.get("exploration") or {}
    if exploration.get("completed_at"):
        return False

    index = session_store.load_index()
    rows = sorted(
        index.get("sessions", []),
        key=lambda row: row.get("last_activity_at") or "",
        reverse=True,
    )
    for row in rows:
        session_id = row.get("session_id")
        if not session_id or not session_store.session_exists(session_id):
            continue
        state = session_store.get_state(session_id)
        completed_at = state.get("explore_completed_at")
        if not completed_at:
            closure = state.get("explore_closure") or {}
            flags = (state.get("gates") or {}).get("flags") or {}
            if closure.get("completed") and (
                state.get("explore_gate_confirmed") or flags.get("explore_gate_confirmed")
            ):
                completed_at = state.get("last_activity_at") or datetime.now(UTC).isoformat()
        if not completed_at:
            continue

        patches: list[dict[str, Any]] = [
            {"path": "exploration.completed_at", "value": completed_at, "op": "set"},
        ]
        intake = exploration.get("intake") or {}
        if intake:
            patches.append(
                {"path": "exploration.intake_baseline", "value": intake, "op": "set"}
            )
        profile_store.patch(patches)
        return True

    return False


def seed_session_explore_completion_from_profile(
    session_state: dict[str, Any],
    profile: dict[str, Any],
) -> bool:
    """写入初始session explore completion from profile。"""
    exploration = profile.get("exploration") or {}
    completed_at = exploration.get("completed_at")
    if not completed_at:
        return False

    flags = (session_state.get("gates") or {}).get("flags") or {}
    if flags.get("explore_return_requested") or flags.get("explore_continue_requested"):
        return False

    if session_state.get("explore_completed_at") == completed_at and (
        session_state.get("explore_gate_confirmed")
        and (session_state.get("explore_closure") or {}).get("completed")
    ):
        return False

    closure = dict(session_state.get("explore_closure") or init_explore_closure())
    required = closure.get("required_workers") or ["identity", "capability"]
    worker_done = dict(closure.get("worker_done") or {})
    for worker_id in required:
        worker_done[worker_id] = True
    closure["worker_done"] = worker_done
    closure["gate_pending"] = False
    closure["completed"] = True
    session_state["explore_closure"] = closure
    session_state["explore_completed_at"] = completed_at

    from career_os.harness.pipeline_gates import set_explore_gate_confirmed

    set_explore_gate_confirmed(session_state, True)
    gates = dict(session_state.get("gates") or {})
    flags = dict(gates.get("flags") or {})
    flags["explore_gate_confirmed"] = True
    flags["fresh_pass"] = True
    gates["flags"] = flags
    session_state["gates"] = gates
    return True


def instantiate_pipeline_for_session(session_id: str) -> str | TaskStoreError:
    """实例化pipeline for session。"""
    store = TaskStore()
    existing = store.get_active_list_id_for_session(session_id)
    if existing:
        meta = store.get_list_meta(existing)
        if meta and meta.get("list_type") == "pipeline":
            return existing

    hydrate_explore_completion_from_sessions()
    profile = ProfileStore().get(["exploration", "intent"])

    result = store.create_task_list(
        session_id,
        list_type="pipeline",
        status="ready",
        current_phase="explore",
    )
    if isinstance(result, TaskStoreError):
        return result
    list_id = result

    blocked_by: str | None = None
    for row in load_pipeline_milestones():
        task_id = row["task_id"]
        created = store.create_task(
            list_id,
            task_id,
            row["subject"],
            kind="milestone",
            pipeline_phase=row["pipeline_phase"],
            parent_milestone_id=None,
            blocked_by=blocked_by,
            requires_user_confirm=True,
        )
        if isinstance(created, TaskStoreError):
            return created
        blocked_by = task_id

    session_store = SessionStore()
    state = session_store.get_state(session_id)
    state.update(
        {
            "list_id": list_id,
            "list_type": "pipeline",
            "explore_closure": init_explore_closure(),
        }
    )
    seed_session_explore_completion_from_profile(state, profile)
    session_store.update_state(session_id, state)
    return list_id
