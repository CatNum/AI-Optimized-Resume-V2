from __future__ import annotations

from datetime import UTC, datetime

from career_os.platform.market_research.extraction import _validate_job_outputs
from career_os.platform.market_research.models import (
    CollectedJob,
    RecruiterActivity,
    SemanticValidationAudit,
)
from career_os.platform.market_research.runner import DirectionRunContext


def test_semantic_audit_keeps_failure_type_and_field_path_without_jd() -> None:
    """语义失败审计必须保存脱敏原因与路径，且绝不保存 JD 或 evidence 原文。"""
    audit = SemanticValidationAudit(
        job_id="job_123",
        job_url="https://www.zhipin.com/job_detail/example.html",
        failure_type="schema_validation",
        field_paths=("responsibilities.0.evidence",),
        attempt=2,
        occurred_at=datetime.now(UTC),
    )

    assert audit.failure_type == "schema_validation"
    assert audit.field_paths == ("responsibilities.0.evidence",)
    assert "raw_job_description" not in audit.model_dump()
    assert "evidence" not in audit.model_dump()


def test_direction_context_aggregates_semantic_failure_audits() -> None:
    """方向状态必须统计语义失败并保存最近审计记录。"""
    context = DirectionRunContext.__new__(DirectionRunContext)
    context.semantic_rejected_job_count = 0
    context.semantic_failure_counts = {}
    context.recent_semantic_failures = []
    audit = SemanticValidationAudit(
        job_id="job_123",
        job_url="https://www.zhipin.com/job_detail/example.html",
        failure_type="evidence_not_found",
        field_paths=("evidence",),
        attempt=2,
        occurred_at=datetime.now(UTC),
    )

    context.record_semantic_validation_failure(audit)

    assert context.semantic_rejected_job_count == 1
    assert context.semantic_failure_counts == {"evidence_not_found": 1}
    assert context.recent_semantic_failures == [audit]


def test_invalid_semantic_output_returns_schema_failure_and_field_path() -> None:
    """岗位输出缺少职责/要求时，最终失败类型必须可用于生成脱敏审计。"""
    job = CollectedJob(
        job_id="job_123",
        job_url="https://www.zhipin.com/job_detail/example.html",
        title="LLM 应用开发工程师",
        matched_keywords=("LLM Agent 应用开发",),
        city="北京",
        experience_group="经验不限",
        education_group="本科",
        salary_min=20_000,
        salary_max=30_000,
        recruiter_activity=RecruiterActivity.JUST_ACTIVE,
        company_name="示例公司",
        collected_at=datetime.now(UTC),
    )

    valid, failures = _validate_job_outputs(
        {"jobs": [{"job_id": "job_123"}]},
        {"job_123": job},
        {"job_123": "负责 LLM 应用开发。"},
    )

    assert valid == {}
    assert failures == {"job_123": ("schema_validation", ("__root__",))}
