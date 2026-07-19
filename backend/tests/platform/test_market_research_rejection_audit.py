from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from career_os.platform.market_research.models import JobRejectionAudit
from career_os.platform.market_research.runner import DirectionRunContext


def test_rejection_audit_keeps_reason_and_identity_without_raw_job_description() -> None:
    """无效岗位审计只保存定位与原因，禁止把完整 JD 写入状态文件。"""
    audit = JobRejectionAudit(
        job_url="https://www.zhipin.com/job_detail/example.html",
        keyword="LLM Agent 应用开发",
        city="北京",
        reason="salary_unparseable",
        title="LLM 应用开发工程师",
        occurred_at=datetime.now(UTC),
    )

    assert audit.reason == "salary_unparseable"
    assert "raw_job_description" not in audit.model_dump()
    with pytest.raises(ValidationError):
        JobRejectionAudit.model_validate(
            {**audit.model_dump(), "raw_job_description": "不得持久化"}
        )


def test_direction_context_counts_rejection_reasons_and_keeps_recent_records() -> None:
    """运行进度必须能展示过滤总数、按原因统计和最近审计记录。"""
    context = DirectionRunContext.__new__(DirectionRunContext)
    context.rejected_job_count = 0
    context.rejection_counts = {}
    context.recent_rejections = []
    audit = JobRejectionAudit(
        job_url="https://www.zhipin.com/job_detail/example.html",
        keyword="LLM Agent 应用开发",
        city="北京",
        reason="recruiter_inactive",
        occurred_at=datetime.now(UTC),
    )

    context.record_rejection(audit)

    assert context.rejected_job_count == 1
    assert context.rejection_counts == {"recruiter_inactive": 1}
    assert context.recent_rejections == [audit]
