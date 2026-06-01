from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from career_os.platform.pipeline_constants import PHASE_TO_MILESTONE_ID
from career_os.harness.explore_closure import init_explore_closure
from career_os.platform.store.session import SessionStore
from career_os.platform.store.task import TaskStore, TaskStoreError


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def load_pipeline_milestones() -> list[dict[str, Any]]:
    path = repo_root() / "config" / "pipeline_milestones.json"
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def instantiate_pipeline_for_session(session_id: str) -> str | TaskStoreError:
    store = TaskStore()
    existing = store.get_active_list_id_for_session(session_id)
    if existing:
        meta = store.get_list_meta(existing)
        if meta and meta.get("list_type") == "pipeline":
            return existing

    result = store.create_task_list(
        session_id,
        list_type="pipeline",
        status="active",
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
            "explore_gate_confirmed": False,
            "explore_closure": init_explore_closure(),
        }
    )
    session_store.update_state(session_id, state)
    return list_id
