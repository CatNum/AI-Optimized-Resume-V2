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
    """表示 pipeline gate 或阶段操作失败。

    code（错误码）用于程序判断失败类型；message（错误消息）用于 trace 或上层提示。
    """
    code: str
    message: str


def is_explore_gate_confirmed(session_state: dict[str, Any]) -> bool:
    """判断探索完成 gate 是否已经确认。

    session_state（会话状态）可能在顶层或 gates.flags 中保存确认标记。
    返回值为 True 表示可以离开 explore 阶段。
    """
    if session_state.get("explore_gate_confirmed"):
        return True
    flags = (session_state.get("gates") or {}).get("flags") or {}
    return bool(flags.get("explore_gate_confirmed"))


def set_explore_gate_confirmed(session_state: dict[str, Any], value: bool) -> None:
    """同步设置探索完成 gate 确认标记。

    session_state（会话状态）会被原地更新；value（确认值）同时写入顶层
    explore_gate_confirmed 和 gates.flags.explore_gate_confirmed。
    """
    session_state["explore_gate_confirmed"] = value
    gates = dict(session_state.get("gates") or {})
    flags = dict(gates.get("flags") or {})
    flags["explore_gate_confirmed"] = value
    gates["flags"] = flags
    session_state["gates"] = gates


def compute_hard_pass(profile: dict[str, Any]) -> tuple[bool, list[str]]:
    """计算用户画像是否满足硬性通过条件。

    profile（用户画像）提供 intake、简历、基础信息和求职意向。返回值是
    (是否通过, 未通过原因列表)。
    """
    reasons: list[str] = []
    exploration = profile.get("exploration") or {}
    intake = exploration.get("intake") or {}
    # intake、简历正文和关键求职字段都齐全，才算硬性通过。
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
    """判断用户是否从未完成过职业初探。

    profile（用户画像）提供 exploration.completed_at 和 intake_baseline。
    返回值为 True 表示没有完成时间，也没有历史初探基线。
    """
    exploration = profile.get("exploration") or {}
    if exploration.get("completed_at"):
        return False
    if exploration.get("intake_baseline"):
        return False
    return True


def _parse_iso_datetime(value: Any) -> datetime | None:
    """解析 ISO 时间字符串。"""
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
    """给时间增加一个自然月。"""
    month_index = dt.month
    year = dt.year + (month_index // 12)
    month = (month_index % 12) + 1
    last_day = calendar.monthrange(year, month)[1]
    day = min(dt.day, last_day)
    return dt.replace(year=year, month=month, day=day)


def _session_has_explore_completion(session_state: dict[str, Any]) -> bool:
    """判断当前会话态是否已经记录探索完成。"""
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
    """判断是否需要重新走完整职业初探。

    profile（用户画像）提供 exploration、resume、intent 等持久化信息；
    session_state（会话状态）提供本会话的探索完成标记和 gates.flags。
    返回值为 True 表示画像过旧、信息变化或从未完成初探，需要先回到 explore。
    """
    # 当前会话已经确认完成探索时，不需要再看 profile 是否过期。
    if _session_has_explore_completion(session_state):
        return False
    # 从未探索过时，必须完整走 explore。
    if never_explored(profile):
        return True
    exploration = profile.get("exploration") or {}
    flags = (session_state.get("gates") or {}).get("flags") or {}
    # fresh_pass 表示本轮刚确认过探索完成，跳过过期/差异检查。
    if flags.get("fresh_pass") is True:
        return False
    completed_at = _parse_iso_datetime(exploration.get("completed_at"))
    if not completed_at:
        return True
    # 完成时间超过一个自然月，要求重新完整初探。
    if datetime.now(UTC) >= _add_natural_month(completed_at.astimezone(UTC)):
        return True
    baseline = exploration.get("intake_baseline")
    intake = exploration.get("intake") or {}
    if baseline and intake:
        # 当前 intake 与完成时基线不一致，说明画像发生变化，需要重新探索。
        if intake != baseline:
            return True
    intent = profile.get("intent") or {}
    if intent.get("requires_career_revisit"):
        return True
    return False


def clear_gate_flags_for_jump(target_phase: str, session_state: dict[str, Any]) -> None:
    """阶段跳转前清理不再适用的 gate flags。

    target_phase（目标阶段）决定要清理哪些确认标记；
    session_state（会话状态）会被原地更新，避免旧 gate 影响新阶段。
    """
    gates = dict(session_state.get("gates") or {})
    flags = dict(gates.get("flags") or {})
    pending = gates.get("pending")

    # 回到 explore 时，清理后续阶段确认，并重置探索完成标记。
    if target_phase == "explore":
        flags.pop("strategy_complete", None)
        flags.pop("optimize_confirmed", None)
        flags["explore_return_requested"] = True
        set_explore_gate_confirmed(session_state, False)
        closure = dict(session_state.get("explore_closure") or {})
        closure.pop("gate_pending", None)
        closure.pop("completed", None)
        session_state["explore_closure"] = closure
    # 回到 market/jd_analysis 时，清理策略和优化确认，避免越级进入后续阶段。
    elif target_phase in {"market", "jd_analysis"}:
        flags.pop("strategy_complete", None)
        flags.pop("optimize_confirmed", None)
        flags.pop("explore_return_requested", None)
        flags.pop("explore_continue_requested", None)
    # 回到策略阶段时，优化确认需要重新走。
    elif target_phase == "resume_strategy":
        flags.pop("optimize_confirmed", None)

    # 如果当前 pending gate 属于被跳过的后续阶段，同时清空 pending。
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
    """校验目标阶段是否允许被显式跳转。

    target_phase（目标阶段）必须在允许跳转集合中；session_state（会话状态）用于检查
    explore gate 是否确认。返回 None 表示允许跳转，否则返回 PipelineGateError。
    """
    # resume_optimize 只能通过 optimize_confirm 后的 advance_current_phase 进入，不能直接跳转。
    if target_phase == "resume_optimize":
        return PipelineGateError(
            "jump_target_forbidden",
            "resume_optimize is not a jump target; use advance after optimize_confirm",
        )
    if target_phase not in JUMP_TARGET_PHASES:
        return PipelineGateError("invalid_phase", f"Unknown jump target: {target_phase}")
    # 离开 explore 前必须先确认探索完成 gate。
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
    """执行 pipeline 显式阶段跳转。

    session_id（会话标识）用于回写会话状态；list_id（列表标识）定位任务列表；
    target_phase（目标阶段）是要跳到的阶段；session_state（会话状态）会同步清理 gate。
    返回值是跳转结果，或 PipelineGateError。
    """
    # 先校验目标阶段是否合法，以及是否满足离开 explore 的 gate 约束。
    err = validate_jump_target(target_phase, session_state)
    if err:
        return err

    # 读取任务列表，确保 list_id 指向 pipeline 类型列表。
    store = TaskStore()
    meta = store.get_list_meta(list_id)
    if not meta or meta.get("list_type") != "pipeline":
        return PipelineGateError("not_pipeline", "Task list is not pipeline")

    from_phase = meta.get("current_phase") or "explore"
    # 已经在目标阶段时直接返回 unchanged，不重复清理任务。
    if from_phase == target_phase:
        return {"list_id": list_id, "current_phase": target_phase, "unchanged": True}

    # 跳转前清理原阶段 work，避免旧阶段任务残留到新阶段。
    clear_err = store.clear_works_for_phase(list_id, from_phase)
    if clear_err:
        return PipelineGateError(clear_err.code, clear_err.message)

    # 清理与新阶段冲突的 gate flags，然后启动列表并写入 current_phase。
    clear_gate_flags_for_jump(target_phase, session_state)

    start_err = store.start_task_list(list_id)
    if start_err and start_err.code != "list_not_ready":
        return PipelineGateError(start_err.code, start_err.message)

    phase_err = store.set_current_phase(list_id, target_phase)
    if phase_err:
        return PipelineGateError(phase_err.code, phase_err.message)

    # 尝试领取目标阶段第一个 work，最后把清理后的 session_state 持久化。
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
    """确保当前阶段存在可领取的 work 任务。

    list_id（列表标识）定位 pipeline 任务列表；phase（阶段）必须等于列表当前阶段；
    session_state（会话状态）用于检查优化确认。返回值包含 created 和 claimed_work。
    """
    store = TaskStore()
    meta = store.get_list_meta(list_id)
    if not meta or meta.get("list_type") != "pipeline":
        return PipelineGateError("not_pipeline", "Task list is not pipeline")

    current = meta.get("current_phase") or "explore"
    # 只能为当前阶段补 work，避免跨阶段创建任务。
    if phase != current:
        return PipelineGateError(
            "phase_mismatch",
            f"Can only ensure works for current phase ({current})",
        )

    start_err = store.start_task_list(list_id)
    if start_err and start_err.code != "list_not_ready":
        return PipelineGateError(start_err.code, start_err.message)

    milestone_id = PHASE_TO_MILESTONE_ID.get(phase)
    if not milestone_id:
        return PipelineGateError("invalid_phase", f"Unknown phase: {phase}")

    existing = store.list_works_for_phase(list_id, phase)
    # 已有 work 时只领取第一个，不重复创建模板任务。
    if existing:
        claimed = store.claim_first_work_for_phase(list_id, phase)
        return {"created": [], "claimed_work": claimed}

    # 简历优化阶段必须先有 optimize_confirmed；未确认时不创建优化 work。
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
    """从当前阶段向 resume_optimize 做受控推进。

    session_id（会话标识）用于持久化会话状态；list_id（列表标识）定位任务列表；
    target_phase（目标阶段）当前只允许 resume_optimize；session_state（会话状态）
    必须包含 optimize_confirmed。返回值是推进结果或 PipelineGateError。
    """
    # 该函数只服务“策略确认后进入简历优化”，其他阶段推进走普通阶段切换。
    if target_phase != "resume_optimize":
        return PipelineGateError(
            "advance_forbidden",
            "advance_current_phase only supports resume_optimize",
        )

    store = TaskStore()
    meta = store.get_list_meta(list_id)
    if not meta or meta.get("list_type") != "pipeline":
        return PipelineGateError("not_pipeline", "Task list is not pipeline")

    # 必须先在 resume_strategy 阶段，才能推进到 resume_optimize。
    if meta.get("current_phase") != "resume_strategy":
        return PipelineGateError(
            "wrong_phase",
            "Must be on resume_strategy before advancing to resume_optimize",
        )

    flags = (session_state.get("gates") or {}).get("flags") or {}
    # 没有用户确认优化时，禁止进入 resume_optimize。
    if not flags.get("optimize_confirmed"):
        return PipelineGateError(
            "optimize_required",
            "optimize_confirm must be confirmed first",
        )

    clear_err = store.clear_works_for_phase(list_id, "resume_strategy")
    if clear_err:
        return PipelineGateError(clear_err.code, clear_err.message)

    start_err = store.start_task_list(list_id)
    if start_err and start_err.code != "list_not_ready":
        return PipelineGateError(start_err.code, start_err.message)

    phase_err = store.set_current_phase(list_id, "resume_optimize")
    if phase_err:
        return PipelineGateError(phase_err.code, phase_err.message)

    # 阶段写入后再确保优化阶段 work 存在或可领取。
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
    """把 Worker 提议的 work 任务写入当前 pipeline 阶段。

    list_id（列表标识）定位任务列表；proposals（任务提议列表）提供待创建 work；
    session_state（会话状态）用于读取当前阶段。返回值包含 created 和 claimed_work，
    或返回 PipelineGateError。
    """
    store = TaskStore()
    meta = store.get_list_meta(list_id)
    if not meta or meta.get("list_type") != "pipeline":
        return PipelineGateError("not_pipeline", "Task list is not pipeline")

    current = meta.get("current_phase") or "explore"
    allowed_parent = PHASE_TO_MILESTONE_ID.get(current)
    # 写入前启动任务列表；list_not_ready 表示已是可接受状态，不视为错误。
    start_err = store.start_task_list(list_id)
    if start_err and start_err.code != "list_not_ready":
        return PipelineGateError(start_err.code, start_err.message)
    created: list[str] = []
    for prop in proposals:
        parent = prop.get("parent_milestone_id")
        # 只能向当前阶段对应的 milestone 下创建 work，防止跨阶段污染任务列表。
        if parent != allowed_parent:
            return PipelineGateError(
                "parent_phase_mismatch",
                f"Work parent must be {allowed_parent} for current phase",
            )
        task_id = prop.get("task_id") or prop.get("id")
        # 每个提议必须有稳定 task_id，供重复写入和后续领取定位。
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

    # 创建后领取当前阶段第一个 work，供执行层继续处理。
    claimed = store.claim_first_work_for_phase(list_id, current)
    return {"created": created, "claimed_work": claimed}
