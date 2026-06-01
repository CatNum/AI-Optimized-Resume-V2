from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, field_validator

from career_os.harness.explore_intake import explore_intake_submitted
from career_os.harness.explore_intake_fields import (
    merge_intake_field_values,
    profile_patches_from_resolved,
)
from career_os.platform.store.profile import ProfileStore
from career_os.platform.store.session import SessionStore
from career_os.platform.pipeline_template import instantiate_pipeline_for_session
from career_os.platform.store.task import TaskStoreError

_SESSION_ID_RE = re.compile(r"^sess_[0-9a-f]{32}$")

class ExploreIntakeRequest(BaseModel):
    session_id: str
    resume_text: str
    years_of_experience: str = ""
    current_salary: str = ""
    target_salary: str = ""
    target_role: str = ""

    @field_validator("resume_text")
    @classmethod
    def resume_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("resume_text is required")
        return value

    @field_validator("session_id")
    @classmethod
    def session_id_format(cls, value: str) -> str:
        if not value.startswith("sess_") or not _SESSION_ID_RE.match(value):
            raise ValueError("invalid_session_id")
        return value


def build_explore_intake_patches(body: ExploreIntakeRequest) -> list[dict[str, Any]]:
    submitted_at = datetime.now(UTC).isoformat()
    user_values = {
        "years_of_experience": body.years_of_experience,
        "current_salary": body.current_salary,
        "target_salary": body.target_salary,
        "target_role": body.target_role,
    }
    resolved, extracted, pending = merge_intake_field_values(
        resume_text=body.resume_text,
        user_values=user_values,
    )
    intake: dict[str, Any] = {
        "submitted_at": submitted_at,
        "resume_text": body.resume_text.strip(),
        "user_supplements": user_values,
        "resolved_fields": resolved,
        "extracted_from_resume": extracted,
        "pending_fields": pending,
    }
    patches: list[dict[str, Any]] = [
        {"path": "exploration.intake", "value": intake, "op": "set"},
        {"path": "resume.source_text", "value": body.resume_text.strip(), "op": "set"},
        *profile_patches_from_resolved(resolved),
    ]
    return patches


def submit_explore_intake(body: ExploreIntakeRequest) -> dict[str, Any]:
    session_store = SessionStore()
    if not session_store.session_exists(body.session_id):
        raise ValueError("session_not_found")
    profile_store = ProfileStore()
    profile_store.patch(build_explore_intake_patches(body))
    state = session_store.get_state(body.session_id)
    list_id = state.get("list_id")
    if not list_id:
        created = instantiate_pipeline_for_session(body.session_id)
        if isinstance(created, TaskStoreError):
            raise RuntimeError(created.message)
        list_id = created
    intake = profile_store.get(["exploration"]).get("exploration", {}).get("intake", {})
    return {
        "ok": True,
        "submitted": True,
        "pending_fields": intake.get("pending_fields") or [],
        "pipeline_list_id": list_id,
    }


def get_explore_intake_status() -> dict[str, Any]:
    profile = ProfileStore().get(["exploration"])
    intake = (profile.get("exploration") or {}).get("intake") or {}
    return {
        "submitted": explore_intake_submitted(profile),
        "intake": intake,
        "pending_fields": intake.get("pending_fields") or [],
    }
