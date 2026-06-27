from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, field_validator

from career_os.harness.explore_intake import explore_intake_submitted
from career_os.harness.explore_intake import resolve_explore_intake
from career_os.harness.explore_intake_fields import (
    merge_intake_field_values,
    profile_patches_from_resolved,
)
from career_os.platform.store.profile import ProfileStore
from career_os.platform.store.session import SessionStore
from career_os.platform.pipeline_template import instantiate_pipeline_for_session
from career_os.platform.store.task import TaskStoreError
from career_os.platform.store.task import TaskStore

_SESSION_ID_RE = re.compile(r"^sess_[0-9a-f]{32}$")


class ExploreIntakeRequest(BaseModel):
    """
    ExploreIntakeRequest（初探信息请求）承载用户提交职业初探表单时的输入数据。
    """

    session_id: str  # 会话标识
    resume_text: str  # 简历文本
    years_of_experience: str = ""  # 工作年限
    current_salary: str = ""  # 当前薪资
    target_salary: str = ""  # 目标薪资
    target_role: str = ""  # 目标岗位

    @field_validator("resume_text")
    @classmethod
    def resume_not_blank(cls, value: str) -> str:
        """校验简历文本不能为空。"""
        if not value.strip():
            raise ValueError("resume_text is required")
        return value

    @field_validator("session_id")
    @classmethod
    def session_id_format(cls, value: str) -> str:
        """校验会话标识格式。"""
        if not value.startswith("sess_") or not _SESSION_ID_RE.match(value):
            raise ValueError("invalid_session_id")
        return value


def build_explore_intake_patches(body: ExploreIntakeRequest) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """构造初探信息表和 profile 补丁。"""
    # 先记录提交时间，并收集用户在表单中显式补充的字段。
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
    # intake 保存原始简历、用户补充、已解析字段和仍待补字段。
    intake: dict[str, Any] = {
        "submitted_at": submitted_at,
        "resume_text": body.resume_text.strip(),
        "user_supplements": user_values,
        "resolved_fields": resolved,
        "extracted_from_resume": extracted,
        "pending_fields": pending,
    }
    # profile patches 把简历正文和已解析字段同步到长期画像。
    patches: list[dict[str, Any]] = [
        {"path": "resume.source_text", "value": body.resume_text.strip(), "op": "set"},
        *profile_patches_from_resolved(resolved),
    ]
    return intake, patches


def submit_explore_intake(body: ExploreIntakeRequest) -> dict[str, Any]:
    """提交初探信息表。"""
    # 先确认会话存在，避免把 intake 写到孤立 session。
    session_store = SessionStore()
    if not session_store.session_exists(body.session_id):
        raise ValueError("session_not_found")
    profile_store = ProfileStore()
    intake, profile_patches = build_explore_intake_patches(body)
    # profile 持久化保存简历、解析字段和 exploration.intake。
    profile_store.patch(
        [
            *profile_patches,
            {"path": "exploration.intake", "value": intake, "op": "set"},
        ]
    )
    # session_state 保存当前会话最新 intake_status，供本轮 Coordinator 立即读取。
    state = session_store.get_state(body.session_id)
    state["intake_status"] = intake
    session_store.update_state(body.session_id, state)
    session_store.patch_artifacts(
        body.session_id,
        [{"path": "exploration.intake", "value": intake, "op": "set"}],
    )
    # 没有 pipeline 任务列表时创建一个；已有时直接启动列表进入后续流程。
    list_id = state.get("list_id")
    if not list_id:
        created = instantiate_pipeline_for_session(body.session_id)
        if isinstance(created, TaskStoreError):
            raise RuntimeError(created.message)
        list_id = created
    start_err = TaskStore().start_task_list(list_id)
    if start_err and start_err.code != "list_not_ready":
        raise RuntimeError(start_err.message)
    return {
        "ok": True,
        "submitted": True,
        "pending_fields": intake.get("pending_fields") or [],
        "pipeline_list_id": list_id,
    }


def get_explore_intake_status(session_id: str | None = None) -> dict[str, Any]:
    """读取初探信息表状态。"""
    # 有 session_id 时优先读取会话态；没有时退回 profile/默认状态。
    intake: dict[str, Any] = {}
    if session_id:
        session = SessionStore().get_state(session_id)
        intake = resolve_explore_intake(session)
    else:
        intake = resolve_explore_intake({})
    return {
        "submitted": explore_intake_submitted({"intake_status": intake}),
        "intake": intake,
        "pending_fields": intake.get("pending_fields") or [],
    }
