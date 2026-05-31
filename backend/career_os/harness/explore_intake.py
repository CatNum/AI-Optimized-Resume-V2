from __future__ import annotations

from typing import Any

from career_os.harness.explore_intake_fields import pending_field_labels
from career_os.platform.store.profile import ProfileStore


def explore_intake_submitted(profile: dict[str, Any] | None = None) -> bool:
    if profile is None:
        profile = ProfileStore().get(["exploration"])
    intake = (profile.get("exploration") or {}).get("intake") or {}
    return bool(intake.get("submitted_at"))


def explore_intake_payload() -> dict[str, Any]:
    profile = ProfileStore().get(["exploration"])
    intake = (profile.get("exploration") or {}).get("intake") or {}
    pending = list(intake.get("pending_fields") or [])
    return {
        "explore_intake_submitted": explore_intake_submitted(profile),
        "explore_intake_pending_fields": pending,
        "explore_intake_pending_labels": pending_field_labels(pending),
        "explore_intake": intake,
    }


def worker_context_from_intake() -> dict[str, Any]:
    profile = ProfileStore().get(["exploration"])
    intake = (profile.get("exploration") or {}).get("intake") or {}
    pending = list(intake.get("pending_fields") or [])
    return {
        "explore_intake_pending_fields": pending,
        "explore_intake_pending_labels": pending_field_labels(pending),
        "explore_intake_resolved_fields": intake.get("resolved_fields") or {},
    }


def is_explore_route(result: dict[str, Any]) -> bool:
    if result.get("list_type") == "explore":
        return True
    workers = result.get("workers") or []
    return any(worker_id in {"identity", "capability"} for worker_id in workers)


def enforce_explore_intake(
    result: dict[str, Any],
    session_state: dict[str, Any],
) -> dict[str, Any]:
    if not is_explore_route(result):
        return result
    if explore_intake_submitted():
        return result
    blocked: dict[str, Any] = {
        "workers": [],
        "list_type": "explore",
        "explore_intake_blocked": True,
    }
    return blocked
