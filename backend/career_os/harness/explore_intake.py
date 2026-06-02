from __future__ import annotations

from typing import Any

from career_os.harness.explore_intake_fields import pending_field_labels
from career_os.platform.store.profile import ProfileStore
from career_os.platform.store.session import SessionStore


def _intake_from_state(session_state: dict[str, Any] | None) -> dict[str, Any]:
    state = session_state or {}
    if isinstance(state.get("intake_status"), dict):
        return state.get("intake_status") or {}
    session_id = state.get("session_id")
    if session_id:
        persisted = SessionStore().get_state(session_id)
        if isinstance(persisted.get("intake_status"), dict):
            return persisted.get("intake_status") or {}
        artifacts = SessionStore().get_artifacts(session_id)
        intake = (artifacts.get("exploration") or {}).get("intake")
        if isinstance(intake, dict):
            return intake
    profile = ProfileStore().get(["exploration"])
    legacy = (profile.get("exploration") or {}).get("intake")
    if isinstance(legacy, dict):
        return legacy
    return {}


def explore_intake_submitted(session_state: dict[str, Any] | None = None) -> bool:
    intake = _intake_from_state(session_state)
    return bool(intake.get("submitted_at"))


def explore_intake_payload(session_state: dict[str, Any] | None = None) -> dict[str, Any]:
    intake = _intake_from_state(session_state)
    pending = list(intake.get("pending_fields") or [])
    return {
        "explore_intake_submitted": explore_intake_submitted(session_state),
        "explore_intake_pending_fields": pending,
        "explore_intake_pending_labels": pending_field_labels(pending),
        "explore_intake": intake,
    }


def worker_context_from_intake(
    session_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    intake = _intake_from_state(session_state)
    pending = list(intake.get("pending_fields") or [])
    return {
        "explore_intake_pending_fields": pending,
        "explore_intake_pending_labels": pending_field_labels(pending),
        "explore_intake_resolved_fields": intake.get("resolved_fields") or {},
    }


def is_explore_route(result: dict[str, Any]) -> bool:
    if result.get("list_type") != "pipeline":
        return False
    if result.get("pipeline_phase") not in (None, "explore"):
        return False
    workers = result.get("workers") or []
    return not workers or any(
        worker_id in {"identity", "capability"} for worker_id in workers
    )


def _gate_flags(session_state: dict[str, Any]) -> dict[str, Any]:
    return (session_state.get("gates") or {}).get("flags") or {}


def needs_repeat_intake(session_state: dict[str, Any]) -> bool:
    flags = _gate_flags(session_state)
    if not flags.get("explore_repeat_accepted"):
        return False
    baseline = flags.get("explore_repeat_baseline_at")
    if not baseline:
        return True
    intake = _intake_from_state(session_state)
    return intake.get("submitted_at") == baseline


def enforce_explore_intake(
    result: dict[str, Any],
    session_state: dict[str, Any],
) -> dict[str, Any]:
    if not is_explore_route(result):
        return result

    flags = _gate_flags(session_state)
    pipeline_result = {
        **result,
        "list_type": "pipeline",
        "pipeline_phase": result.get("pipeline_phase") or "explore",
    }

    if flags.get("explore_repeat_declined"):
        return {**pipeline_result, "workers": []}

    if not explore_intake_submitted(session_state):
        return {
            **pipeline_result,
            "workers": [],
            "explore_intake_blocked": True,
        }

    if flags.get("explore_repeat_accepted"):
        if needs_repeat_intake(session_state):
            return {
                **pipeline_result,
                "workers": [],
                "explore_intake_blocked": True,
            }
        return pipeline_result

    return {
        **pipeline_result,
        "workers": [],
        "explore_repeat_blocked": True,
    }
