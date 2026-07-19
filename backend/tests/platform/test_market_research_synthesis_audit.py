from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ValidationError

from career_os.platform.market_research.models import SynthesisValidationAudit
from career_os.platform.market_research.synthesis import (
    build_synthesis_retry_context,
    build_synthesis_retry_feedback,
    build_synthesis_validation_audit,
)
from career_os.platform.prompt.loader import load_market_research_direction_prompt


class _OutputShape(BaseModel):
    """测试用综合输出结构，用于构造稳定的 Pydantic 字段路径。"""

    salary_summary: dict[str, int]


def test_synthesis_audit_extracts_validation_type_and_field_path() -> None:
    """综合输出结构错误必须保存失败类型与 loc 路径，不能保存原始输出。"""
    try:
        _OutputShape.model_validate({"salary_summary": {"median": "not-an-integer"}})
    except ValidationError as error:
        audit = build_synthesis_validation_audit(error, attempt=1, now=lambda: datetime.now(UTC))
    else:  # pragma: no cover - fixture 必须产生校验错误
        raise AssertionError("fixture must fail validation")

    assert audit.failure_type == "ValidationError"
    assert audit.field_paths == ("salary_summary.median",)
    assert "raw_output" not in audit.model_dump()


def test_synthesis_audit_uses_root_path_for_non_structured_harness_errors() -> None:
    """引用约束等 ValueError 没有 Pydantic loc 时使用根路径，不泄露异常消息。"""
    audit = build_synthesis_validation_audit(
        ValueError("synthesis references an unknown statistic"),
        attempt=2,
        now=lambda: datetime.now(UTC),
    )

    assert audit.failure_type == "ValueError"
    assert audit.field_paths == ("__root__",)
    assert audit.rule_code == "unknown_statistic_ref"


def test_direction_synthesis_prompt_forbids_worker_numeric_copies() -> None:
    """综合 Worker 的说明契约必须明确禁止数字，避免与程序冻结数字重复冲突。"""
    prompt = load_market_research_direction_prompt()

    assert "不得输出任何阿拉伯数字" in prompt
    assert "具体数字由程序渲染" in prompt
    assert "validation_feedback" in prompt
    assert "不代表招聘趋势" in prompt
    assert "support_count" in prompt


def test_synthesis_retry_feedback_keeps_only_rule_code_and_field_paths() -> None:
    """第二次综合调用必须收到可行动的脱敏规则码和字段路径，不接收异常原文。"""
    audit = SynthesisValidationAudit(
        failure_type="ValidationError",
        rule_code="schema_validation",
        field_paths=("evidence_themes.1.support_count",),
        attempt=1,
        occurred_at=datetime.now(UTC),
    )

    assert build_synthesis_retry_feedback(audit) == {
        "rule_code": "schema_validation",
        "field_paths": ["evidence_themes.1.support_count"],
    }


def test_synthesis_retry_context_includes_previous_model_output_only_for_retry() -> None:
    """第二次调用要收到首次 JSON 输出，以便按反馈原样修复完整对象。"""
    audit = SynthesisValidationAudit(
        failure_type="ValueError",
        rule_code="trend_boundary_missing",
        field_paths=("__root__",),
        attempt=1,
        occurred_at=datetime.now(UTC),
    )
    previous_output = {"trend_explanation": "这是搜索热度"}

    assert build_synthesis_retry_context(audit, previous_output) == {
        "validation_feedback": {
            "rule_code": "trend_boundary_missing",
            "field_paths": ["__root__"],
        },
        "previous_output": previous_output,
    }
