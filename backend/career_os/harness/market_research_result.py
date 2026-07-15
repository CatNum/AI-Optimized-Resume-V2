from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from career_os.harness.errors import HarnessError
from career_os.platform.market_research.models import (
    DirectionResult,
    ResearchStatus,
    ResultRef,
)
from career_os.platform.market_research.store import MarketResearchStore
from career_os.platform.store.session import SessionStore
from career_os.platform.store.task import TaskStore


_ACTIVE_RESEARCH_STATUSES = {
    ResearchStatus.QUEUED,
    ResearchStatus.RUNNING,
    ResearchStatus.WAITING_USER,
    ResearchStatus.CANCELLING,
}


@dataclass(frozen=True)
class ResolvedMarketResult:
    """ResolvedMarketResult（已解析市场结果）保存 Harness 校验后允许下游读取的精简数据。"""

    research_id: str  # 正式市场调研任务编号
    result_version: int  # 已确认且不可变的正式结果版本
    status: str  # 正式结果的 completed 或 partial_completed 状态
    researched_at: str  # 正式结果完成调研的 ISO 时间
    expires_at: str  # 当前选择方向中最早停止下游使用的 ISO 时间
    directions: tuple[dict[str, Any], ...]  # 去除岗位编号和审计引用后的方向市场摘要
    comparison: dict[str, Any] | None  # 多方向并列对照，不包含评分或推荐
    source_boundaries: tuple[str, ...]  # 数据来源、样本口径和禁止推断边界

    def to_context(self) -> dict[str, Any]:
        """转换为只包含白名单字段的 context.market_research_result（市场调研上下文）。"""
        return {
            "research_id": self.research_id,
            "result_version": self.result_version,
            "status": self.status,
            "researched_at": self.researched_at,
            "expires_at": self.expires_at,
            "directions": list(self.directions),
            "comparison": self.comparison,
            "source_boundaries": list(self.source_boundaries),
        }


def resolve_downstream_result(
    session_id: str,
    session_state: dict[str, Any],
) -> ResolvedMarketResult | HarnessError:
    """解析正式市场结果；校验确认、版本、有效期和删除状态后返回精简下游数据。"""
    return _resolve_result(session_id, session_state, require_confirmation=True)


def confirm_market_result(
    session_id: str,
    session_state: dict[str, Any],
) -> ResolvedMarketResult | HarnessError:
    """校验并确认当前正式市场结果，然后把 Pipeline 推进到 JD 分析阶段。"""
    resolved = _resolve_result(session_id, session_state, require_confirmation=False)
    if isinstance(resolved, HarnessError):
        return resolved
    session_store = SessionStore()
    artifacts = session_store.get_artifacts(session_id)
    market = artifacts.get("market") if isinstance(artifacts, dict) else None
    if not isinstance(market, dict):
        return HarnessError("market_result_reference_missing", "当前 Session 没有市场结果引用。")
    current_ref = market.get("result_ref") or market.get("reuse_ref")
    if not isinstance(current_ref, dict):
        return HarnessError("market_result_reference_missing", "当前 Session 没有市场结果引用。")
    try:
        confirmed_state = session_store.confirm_market_result_reference(
            session_id,
            current_ref,
        )
    except ValueError:
        return HarnessError(
            "market_result_version_mismatch",
            "确认期间市场结果引用发生变化，请刷新后重新确认。",
        )
    session_state.clear()
    session_state.update(confirmed_state)
    list_id = session_state.get("list_id")
    if isinstance(list_id, str) and list_id:
        phase_error = TaskStore().set_current_phase(list_id, "jd_analysis")
        if phase_error is not None:
            return HarnessError(phase_error.code, phase_error.message)
    return resolved


def _resolve_result(
    session_id: str,
    session_state: dict[str, Any],
    *,
    require_confirmation: bool,
) -> ResolvedMarketResult | HarnessError:
    """按确认要求解析当前不可变结果，供确认操作和下游读取共享同一套校验。"""
    if not session_id:
        return HarnessError(
            "market_result_reference_missing",
            "市场结果解析缺少 Session 标识。",
        )
    session_store = SessionStore()
    if not session_store.session_exists(session_id):
        return HarnessError(
            "market_result_reference_missing",
            "当前 Session 不存在，无法解析市场结果。",
        )
    artifacts = session_store.get_artifacts(session_id)
    market = artifacts.get("market") if isinstance(artifacts, dict) else None
    if not isinstance(market, dict) or market.get("schema_version") != 1:
        return HarnessError(
            "market_result_reference_missing",
            "当前 Session 没有可验证的市场结果引用。",
        )

    store = MarketResearchStore()
    active_research_id = market.get("active_research_id")
    if isinstance(active_research_id, str) and active_research_id:
        snapshot = store.read_status(active_research_id)
        if snapshot is not None and snapshot.status in _ACTIVE_RESEARCH_STATUSES:
            return HarnessError(
                "market_research_in_progress",
                f"市场调研仍在进行中，当前状态为 {snapshot.status.value}。",
            )

    result_ref = market.get("result_ref")
    reuse_ref = market.get("reuse_ref")
    if result_ref is not None and reuse_ref is not None:
        return HarnessError(
            "market_result_reference_conflict",
            "当前 Session 同时存在新结果和复用结果引用，已拒绝下游使用。",
        )
    current_ref = result_ref if result_ref is not None else reuse_ref
    if not isinstance(current_ref, dict):
        return HarnessError(
            "market_result_reference_missing",
            "当前 Session 尚无正式市场结果引用。",
        )
    if require_confirmation and not market.get("market_result_confirmed"):
        return HarnessError(
            "market_result_confirmation_required",
            "请先查看并明确确认当前正式市场结果。",
        )
    if require_confirmation and market.get("confirmed_result_ref") != current_ref:
        return HarnessError(
            "market_result_version_mismatch",
            "已确认引用与当前市场结果引用不一致，请重新确认。",
        )

    try:
        parsed_ref = ResultRef.model_validate(current_ref)
    except ValueError:
        research_id = current_ref.get("research_id")
        result_version = current_ref.get("result_version")
        try:
            parsed_ref = ResultRef(
                research_id=research_id,
                result_version=result_version,
            )
        except ValueError:
            return HarnessError(
                "market_result_reference_missing",
                "当前市场结果引用结构无效。",
            )

    try:
        result = store.read_result(parsed_ref.research_id, parsed_ref.result_version)
    except (FileNotFoundError, OSError, ValueError):
        return HarnessError(
            "market_result_deleted",
            "正式市场结果已删除或不可读取，请重新调研。",
        )
    if (
        result.research_id != parsed_ref.research_id
        or result.result_version != parsed_ref.result_version
    ):
        return HarnessError(
            "market_result_version_mismatch",
            "正式市场结果内容与引用版本不一致。",
        )

    selected_direction_key = reuse_ref.get("direction_key") if isinstance(reuse_ref, dict) else None
    reuse_direction_ref = (
        reuse_ref.get("direction_result_ref") if isinstance(reuse_ref, dict) else None
    )
    if reuse_ref is not None:
        if not isinstance(selected_direction_key, str) or not isinstance(
            reuse_direction_ref, dict
        ):
            return HarnessError(
                "market_result_version_mismatch",
                "复用引用缺少唯一职业方向的不可变引用。",
            )
        if (
            reuse_direction_ref.get("research_id") != parsed_ref.research_id
            or reuse_direction_ref.get("result_version") != parsed_ref.result_version
            or reuse_direction_ref.get("direction_key") != selected_direction_key
        ):
            return HarnessError(
                "market_result_version_mismatch",
                "复用方向引用与正式结果版本不一致。",
            )
    resolved_directions: list[DirectionResult] = []
    for entry in result.successful_directions:
        direction = store.resolve_direction_entry(entry)
        if selected_direction_key and direction.direction_key != selected_direction_key:
            continue
        if reuse_direction_ref is not None and (
            reuse_direction_ref.get("direction_run_id") != direction.direction_run_id
        ):
            return HarnessError(
                "market_result_version_mismatch",
                "复用方向运行编号与正式结果不一致。",
            )
        resolved_directions.append(direction)
    if selected_direction_key and not resolved_directions:
        return HarnessError(
            "market_result_version_mismatch",
            "复用引用中的职业方向不属于该正式结果版本。",
        )

    effective_expires_at = min(direction.expires_at for direction in resolved_directions)
    if datetime.now(UTC) >= effective_expires_at:
        session_store.clear_expired_market_reference(session_id, current_ref)
        session_state.clear()
        session_state.update(session_store.get_state(session_id))
        return HarnessError(
            "market_result_expired",
            "当前正式市场结果已经过期，请重新调研。",
        )
    comparison = (
        result.comparison.model_dump(mode="json")
        if result.comparison is not None and not selected_direction_key
        else None
    )
    return ResolvedMarketResult(
        research_id=result.research_id,
        result_version=result.result_version,
        status=result.status,
        researched_at=result.researched_at.isoformat(),
        expires_at=effective_expires_at.isoformat(),
        directions=tuple(_compact_direction(direction) for direction in resolved_directions),
        comparison=comparison,
        source_boundaries=result.source_boundaries,
    )


def market_result_is_confirmed(
    session_state: dict[str, Any],
) -> bool:
    """重新解析当前 Session 的正式引用，只有完整校验通过时才返回真。"""
    session_id = session_state.get("session_id")
    if not isinstance(session_id, str):
        return False
    return not isinstance(resolve_downstream_result(session_id, session_state), HarnessError)


def _compact_direction(direction: DirectionResult) -> dict[str, Any]:
    """移除岗位编号、支持集合和审计引用，只保留下游决策需要的冻结市场字段。"""
    def compact_theme(theme: Any) -> dict[str, Any]:
        """把主题转换为主题名、支持岗位数和最多三个公开代表岗位。"""
        return {
            "theme": theme.theme,
            "support_job_count": len(theme.support_job_ids),
            "representative_jobs": [
                {
                    "title": job.title,
                    "company_name": job.company_name,
                    "job_url": job.job_url,
                }
                for job in theme.representative_jobs
            ],
        }

    def compact_skill(skill: Any) -> dict[str, Any]:
        """把技能统计转换为规范名称、别名、计数和分母，不下发岗位编号集合。"""
        return {
            "canonical_name": skill.canonical_name,
            "aliases": list(skill.aliases),
            "mention_count": skill.mention_count,
            "required_count": skill.required_count,
            "preferred_count": skill.preferred_count,
            "mention_denominator": skill.mention_denominator,
            "semantic_denominator": skill.semantic_denominator,
        }

    return {
        "direction_name": direction.direction_name,
        "direction_key": direction.direction_key,
        "researched_at": direction.researched_at.isoformat(),
        "expires_at": direction.expires_at.isoformat(),
        "boss_keywords": list(direction.boss_keywords),
        "trends_keywords": list(direction.trends_keywords),
        "visited_cities": list(direction.visited_cities),
        "keyword_statuses": dict(direction.keyword_statuses),
        "budget_seconds": direction.budget_seconds,
        "elapsed_seconds": direction.elapsed_seconds,
        "candidate_count": direction.candidate_count,
        "valid_job_count": direction.valid_job_count,
        "deduplicated_job_count": direction.deduplicated_job_count,
        "semantic_analyzed_count": direction.semantic_analyzed_count,
        "company_count": direction.company_count,
        "sample_level": direction.sample_level,
        "career_definition": direction.career_definition,
        "responsibility_themes": [compact_theme(item) for item in direction.responsibility_themes],
        "requirement_themes": [compact_theme(item) for item in direction.requirement_themes],
        "preference_themes": [compact_theme(item) for item in direction.preference_themes],
        "evidence_themes": [compact_theme(item) for item in direction.evidence_themes],
        "skill_statistics": [compact_skill(item) for item in direction.skill_statistics],
        "emerging_or_isolated_skills": [
            compact_skill(item) for item in direction.emerging_or_isolated_skills
        ],
        "experience_analysis": direction.experience_analysis,
        "education_distribution": direction.education_distribution,
        "salary_analysis": direction.salary_analysis,
        "industry_distribution": direction.industry_distribution,
        "company_size_distribution": direction.company_size_distribution,
        "trend_observations": [
            observation.model_dump(mode="json") for observation in direction.trend_observations
        ],
        "sample_limitations": list(direction.sample_limitations),
        "representative_jobs": [
            {
                "title": job.title,
                "company_name": job.company_name,
                "job_url": job.job_url,
            }
            for job in direction.representative_jobs
        ],
    }
