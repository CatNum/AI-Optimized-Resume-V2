from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from career_os.harness.explore_intake_fields import INTAKE_FIELD_KEYS
from career_os.platform.pipeline_constants import (
    JUMP_TARGET_PHASES,
    PHASE_TO_MILESTONE_ID,
    PIPELINE_PHASES,
)
from career_os.platform.store.profile import ProfileStore
from career_os.platform.store.session import SessionStore
from career_os.platform.store.task import TaskStore, TaskStoreError


@dataclass
class PipelineGateError:
    code: str
    message: str


def is_explore_gate_confirmed(session_state: dict[str, Any]) -> bool:
    if session_state.get("explore_gate_confirmed"):
        return True
    flags = (session_state.get("gates") or {}).get("flags") or {}
    return bool(flags.get("explore_gate_confirmed"))


def set_explore_gate_confirmed(session_state: dict[str, Any], value: bool) -> None:
    session_state["explore_gate_confirmed"] = value
    gates = dict(session_state.get("gates") or {})
    flags = dict(gates.get("flags") or {})
    flags["explore_gate_confirmed"] = value
    gates["flags"] = flags
    session_state["gates"] = gates


def compute_hard_pass(profile: dict[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    exploration = profile.get("exploration") or {}
    intake = exploration.get("intake") or {}
    if not intake.get("submitted_at"):
        reasons.append("explore_intake_not_submitted")
    resume_text = (profile.get("resume") or {}).get("source_text") or ""
    if not str(resume_text).strip():
        reasons.append("resume_missing")
    basic = profile.get("basic") or {}
    intent = profile.get("intent") or {}
    for key in INTAKE_FIELD_KEYS:
        path = key
        if key == "years_of_experience":
            val = basic.get("years_of_experience")
        elif key in {"current_salary", "target_salary", "target_role"}:
            val = intent.get(key)
        else:
            val = None
        if val is None or str(val).strip() == "":
            reasons.append(f"missing_{key}")
    return (len(reasons) == 0, reasons)


def never_explored(profile: dict[str, Any]) -> bool:
    exploration = profile.get("exploration") or {}
    if exploration.get("completed_at"):
        return False
    if exploration.get("intake_baseline"):
        return False
    return True


def _parse_iso_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _add_natural_month(dt: datetime) -> datetime:
    month_index = dt.month
    year = dt.year + (month_index // 12)
    month = (month_index % 12) + 1
    last_day = calendar.monthrange(year, month)[1]
    day = min(dt.day, last_day)
    return dt.replace(year=year, month=month, day=day)


def _session_has_explore_completion(session_state: dict[str, Any]) -> bool:
    if session_state.get("explore_completed_at"):
        return True
    if session_state.get("explore_gate_confirmed"):
        return True
    flags = (session_state.get("gates") or {}).get("flags") or {}
    if flags.get("explore_gate_confirmed"):
        return True
    closure = session_state.get("explore_closure") or {}
    return bool(closure.get("completed"))


def compute_needs_full_explore(
    profile: dict[str, Any], session_state: dict[str, Any]
) -> bool:
    if _session_has_explore_completion(session_state):
        return False
    if never_explored(profile):
        return True
    exploration = profile.get("exploration") or {}
    flags = (session_state.get("gates") or {}).get("flags") or {}
    if flags.get("fresh_pass") is True:
        return False
    completed_at = _parse_iso_datetime(exploration.get("completed_at"))
    if not completed_at:
        return True
    if datetime.now(UTC) >= _add_natural_month(completed_at.astimezone(UTC)):
        return True
    baseline = exploration.get("intake_baseline")
    intake = exploration.get("intake") or {}
    if baseline and intake:
        if intake != baseline:
            return True
    intent = profile.get("intent") or {}
    if intent.get("requires_career_revisit"):
        return True
    return False


def clear_gate_flags_for_jump(target_phase: str, session_state: dict[str, Any]) -> None:
    gates = dict(session_state.get("gates") or {})
    flags = dict(gates.get("flags") or {})
    pending = gates.get("pending")

    if target_phase == "explore":
        flags.pop("strategy_complete", None)
        flags.pop("optimize_confirmed", None)
        flags["explore_return_requested"] = True
        set_explore_gate_confirmed(session_state, False)
        closure = dict(session_state.get("explore_closure") or {})
        closure.pop("gate_pending", None)
        closure.pop("completed", None)
        session_state["explore_closure"] = closure
    elif target_phase in {"market", "jd_analysis"}:
        flags.pop("strategy_complete", None)
        flags.pop("optimize_confirmed", None)
        flags.pop("explore_return_requested", None)
        flags.pop("explore_continue_requested", None)
    elif target_phase == "resume_strategy":
        flags.pop("optimize_confirmed", None)

    if pending and isinstance(pending, dict):
        pname = pending.get("name")
        if target_phase == "explore" and pname in {
            "strategy_complete",
            "optimize_confirm",
        }:
            gates["pending"] = None
        elif target_phase in {"market", "jd_analysis", "explore"} and pname in {
            "strategy_complete",
            "optimize_confirm",
        }:
            gates["pending"] = None
        elif target_phase == "resume_strategy" and pname == "optimize_confirm":
            gates["pending"] = None

    gates["flags"] = flags
    session_state["gates"] = gates


def validate_jump_target(
    target_phase: str, session_state: dict[str, Any]
) -> PipelineGateError | None:
    if target_phase == "resume_optimize":
        return PipelineGateError(
            "jump_target_forbidden",
            "resume_optimize is not a jump target; use advance after optimize_confirm",
        )
    if target_phase not in JUMP_TARGET_PHASES:
        return PipelineGateError("invalid_phase", f"Unknown jump target: {target_phase}")
    if target_phase != "explore" and not is_explore_gate_confirmed(session_state):
        return PipelineGateError(
            "explore_gate_required",
            "explore_complete must be confirmed before leaving explore",
        )
    return None


def jump_to_phase(
    session_id: str,
    list_id: str,
    target_phase: str,
    session_state: dict[str, Any],
) -> PipelineGateError | dict[str, Any]:
    err = validate_jump_target(target_phase, session_state)
    if err:
        return err

    store = TaskStore()
    meta = store.get_list_meta(list_id)
    if not meta or meta.get("list_type") != "pipeline":
        return PipelineGateError("not_pipeline", "Task list is not pipeline")

    from_phase = meta.get("current_phase") or "explore"
    if from_phase == target_phase:
        return {"list_id": list_id, "current_phase": target_phase, "unchanged": True}

    clear_err = store.clear_works_for_phase(list_id, from_phase)
    if clear_err:
        return PipelineGateError(clear_err.code, clear_err.message)

    clear_gate_flags_for_jump(target_phase, session_state)

    phase_err = store.set_current_phase(list_id, target_phase)
    if phase_err:
        return PipelineGateError(phase_err.code, phase_err.message)

    claimed = store.claim_first_work_for_phase(list_id, target_phase)
    SessionStore().update_state(session_id, session_state)
    return {
        "list_id": list_id,
        "current_phase": target_phase,
        "from_phase": from_phase,
        "claimed_work": claimed,
    }


def ensure_milestone_works(
    list_id: str, phase: str, *, session_state: dict[str, Any] | None = None
) -> dict[str, Any] | PipelineGateError:
    store = TaskStore()
    meta = store.get_list_meta(list_id)
    if not meta or meta.get("list_type") != "pipeline":
        return PipelineGateError("not_pipeline", "Task list is not pipeline")

    current = meta.get("current_phase") or "explore"
    if phase != current:
        return PipelineGateError(
            "phase_mismatch",
            f"Can only ensure works for current phase ({current})",
        )

    milestone_id = PHASE_TO_MILESTONE_ID.get(phase)
    if not milestone_id:
        return PipelineGateError("invalid_phase", f"Unknown phase: {phase}")

    existing = store.list_works_for_phase(list_id, phase)
    if existing:
        claimed = store.claim_first_work_for_phase(list_id, phase)
        return {"created": [], "claimed_work": claimed}

    if phase == "resume_optimize":
        if session_state:
            flags = (session_state.get("gates") or {}).get("flags") or {}
            if not flags.get("optimize_confirmed"):
                return PipelineGateError(
                    "optimize_required",
                    "optimize_confirm required before resume works",
                )
        return {"created": [], "claimed_work": None}

    templates: tuple[dict[str, Any], ...] = (
        {
            "task_id": f"work_{phase}_plan",
            "subject": f"{phase} 执行计划",
            "description": f"规划 {phase} 阶段子任务",
            "sort_order": 1,
        },
    )

    created: list[str] = []
    for row in templates:
        result = store.create_task(
            list_id,
            row["task_id"],
            row["subject"],
            kind="work",
            parent_milestone_id=milestone_id,
            pipeline_phase=phase,
            description=row.get("description"),
            sort_order=row.get("sort_order", 0),
        )
        if isinstance(result, TaskStoreError):
            return PipelineGateError(result.code, result.message)
        created.append(row["task_id"])

    claimed = store.claim_first_work_for_phase(list_id, phase)
    return {"created": created, "claimed_work": claimed}


def advance_current_phase(
    session_id: str,
    list_id: str,
    target_phase: str,
    session_state: dict[str, Any],
) -> PipelineGateError | dict[str, Any]:
    if target_phase != "resume_optimize":
        return PipelineGateError(
            "advance_forbidden",
            "advance_current_phase only supports resume_optimize",
        )

    store = TaskStore()
    meta = store.get_list_meta(list_id)
    if not meta or meta.get("list_type") != "pipeline":
        return PipelineGateError("not_pipeline", "Task list is not pipeline")

    if meta.get("current_phase") != "resume_strategy":
        return PipelineGateError(
            "wrong_phase",
            "Must be on resume_strategy before advancing to resume_optimize",
        )

    flags = (session_state.get("gates") or {}).get("flags") or {}
    if not flags.get("optimize_confirmed"):
        return PipelineGateError(
            "optimize_required",
            "optimize_confirm must be confirmed first",
        )

    clear_err = store.clear_works_for_phase(list_id, "resume_strategy")
    if clear_err:
        return PipelineGateError(clear_err.code, clear_err.message)

    phase_err = store.set_current_phase(list_id, "resume_optimize")
    if phase_err:
        return PipelineGateError(phase_err.code, phase_err.message)

    works_result = ensure_milestone_works(
        list_id, "resume_optimize", session_state=session_state
    )
    if isinstance(works_result, PipelineGateError):
        return works_result

    SessionStore().update_state(session_id, session_state)
    return {
        "list_id": list_id,
        "current_phase": "resume_optimize",
        "from_phase": "resume_strategy",
        **works_result,
    }


def apply_proposed_work_tasks(
    list_id: str,
    proposals: list[dict[str, Any]],
    session_state: dict[str, Any],
) -> PipelineGateError | dict[str, Any]:
    store = TaskStore()
    meta = store.get_list_meta(list_id)
    if not meta or meta.get("list_type") != "pipeline":
        return PipelineGateError("not_pipeline", "Task list is not pipeline")

    current = meta.get("current_phase") or "explore"
    allowed_parent = PHASE_TO_MILESTONE_ID.get(current)
    created: list[str] = []
    for prop in proposals:
        parent = prop.get("parent_milestone_id")
        if parent != allowed_parent:
            return PipelineGateError(
                "parent_phase_mismatch",
                f"Work parent must be {allowed_parent} for current phase",
            )
        task_id = prop.get("task_id") or prop.get("id")
        if not task_id:
            return PipelineGateError("invalid_proposal", "task_id required")
        title = prop.get("subject") or prop.get("title") or task_id
        result = store.create_task(
            list_id,
            task_id,
            title,
            kind="work",
            parent_milestone_id=parent,
            pipeline_phase=current,
            description=prop.get("description"),
            sort_order=prop.get("sort_order"),
            worker_id=prop.get("worker_id"),
        )
        if isinstance(result, TaskStoreError):
            return PipelineGateError(result.code, result.message)
        created.append(task_id)

    claimed = store.claim_first_work_for_phase(list_id, current)
    return {"created": created, "claimed_work": claimed}
