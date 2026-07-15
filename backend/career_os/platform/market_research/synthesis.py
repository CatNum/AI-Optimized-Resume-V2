from __future__ import annotations

import calendar
import json
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Callable

from pydantic import BaseModel, ConfigDict, ValidationError

from career_os.agents.lc.client import invoke_json
from career_os.agents.lc.models import LLMRole
from career_os.config import settings
from career_os.platform.market_research.errors import (
    MarketResearchError,
    MarketResearchErrorCode,
)
from career_os.platform.market_research.models import (
    CollectedJob,
    DirectionResult,
    DirectionStatistics,
    FailedDirection,
    JobReference,
    MarketComparison,
    MarketResearchResult,
    MarketSynthesisOutput,
    ResearchPlan,
    ResearchStage,
    SynthesisThemeCandidate,
    ThemeSummary,
)
from career_os.platform.market_research.sampling import job_identity
from career_os.platform.market_research.renderer import PlainTextMarketReportRenderer
from career_os.platform.market_research.store import MarketResearchStore
from career_os.platform.prompt.loader import (
    load_market_research_comparison_prompt,
    load_market_research_direction_prompt,
)
from career_os.platform.store.session import SessionStore

if TYPE_CHECKING:
    from career_os.platform.market_research.runner import DirectionRunContext, StageHandler


SynthesisLLMCall = Callable[[str, str], dict[str, Any] | None]
"""SynthesisLLMCall（综合模型调用）只接收受限 System 和结构化 user JSON。"""

_ALLOWED_STATISTIC_REFS = frozenset(
    {
        "valid_job_count",
        "semantic_analyzed_count",
        "company_count",
        "sample_level",
        "experience_analysis",
        "education_distribution",
        "salary_analysis",
        "industry_distribution",
        "company_size_distribution",
        "skill_taxonomy",
        "trend_observations",
    }
)
_PROHIBITED_SYNTHESIS_PHRASES = (
    "排名",
    "评分",
    "推荐",
    "更适合",
    "匹配度",
    "需求强弱",
    "城市对比",
)
_PROHIBITED_COMPARISON_PHRASES = (
    *_PROHIBITED_SYNTHESIS_PHRASES,
    "招聘趋势",
    "需求更强",
)
_SOURCE_BOUNDARIES = (
    "BOSS 数据仅表示本轮仍可访问且满足固定准入规则的当前岗位样本。",
    "岗位数量只表示本次样本规模，不代表市场总量或方向优劣。",
    "Google 数据仅表示搜索关注度，不代表招聘趋势。",
)


class ComparisonSynthesisOutput(BaseModel):
    """ComparisonSynthesisOutput（方向对照输出）只保存并列说明和完整方向键集合。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    summary: str  # 无排名、评分、匹配或推荐的并列说明
    direction_keys: tuple[str, ...]  # 必须与输入成功方向顺序完全一致


class MarketSynthesisService:
    """MarketSynthesisService（市场综合服务）用无工具 Worker 提议语义，再由程序验证引用。"""

    def __init__(
        self,
        *,
        llm_call: SynthesisLLMCall | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        """注入无工具 JSON 调用和时钟；默认复用 WORKER_MODEL 且 temperature=0。"""
        self.llm_call = llm_call or _invoke_worker_json  # 不提供 tools 的 Worker 模型调用
        self.direction_prompt = load_market_research_direction_prompt()  # 单方向只读综合指令
        self.comparison_prompt = load_market_research_comparison_prompt()  # 多方向并列对照指令
        self._now = now or (lambda: datetime.now(UTC))  # 冻结调研完成与六个月有效期的时钟

    def synthesize_direction(self, context: DirectionRunContext) -> DirectionResult:
        """综合一个方向，验证全部岗位和统计引用后原样合并确定性数字。"""
        jobs = [CollectedJob.model_validate(job) for job in context.data.get("jobs") or []]
        semantic_jobs = [job for job in jobs if job.semantic_valid]
        statistics = DirectionStatistics.model_validate(context.data.get("statistics"))
        if len(semantic_jobs) < 3:
            raise MarketResearchError(
                MarketResearchErrorCode.EXECUTION_FAILED,
                stage=ResearchStage.SYNTHESIZING.value,
                message="direction synthesis requires at least three semantic jobs",
            )
        frozen_input = self._direction_input(context, semantic_jobs, statistics)
        validation_error: str | None = None
        for _attempt in range(2):
            user_payload = dict(frozen_input)
            if validation_error is not None:
                user_payload["validation_error"] = validation_error
            raw = self._call(self.direction_prompt, user_payload)
            try:
                output = MarketSynthesisOutput.model_validate(raw)
                direction_result = self._validate_and_merge(
                    context,
                    jobs,
                    statistics,
                    output,
                )
                context.record_direction_result(direction_result)
                return direction_result
            except (ValidationError, ValueError, TypeError) as error:
                validation_error = type(error).__name__
        raise MarketResearchError(
            MarketResearchErrorCode.EXECUTION_FAILED,
            stage=ResearchStage.SYNTHESIZING.value,
            message="direction synthesis failed Harness validation",
        )

    def synthesize_comparison(
        self,
        directions: tuple[DirectionResult, ...],
    ) -> MarketComparison | None:
        """至少两个成功方向时生成并列对照；两次失败后返回确定性程序说明。"""
        if len(directions) < 2:
            return None
        direction_keys = tuple(direction.direction_key for direction in directions)
        payload = {
            "directions": [
                {
                    "direction_name": direction.direction_name,
                    "direction_key": direction.direction_key,
                    "responsibility_themes": [
                        theme.theme for theme in direction.responsibility_themes
                    ],
                    "experience_focus_groups": direction.experience_analysis.get(
                        "focus_groups", ()
                    ),
                    "skills": [
                        skill.canonical_name for skill in direction.skill_statistics
                    ],
                    "salary_analysis": direction.salary_analysis,
                }
                for direction in directions
            ]
        }
        for _attempt in range(2):
            raw = self._call(self.comparison_prompt, payload)
            try:
                output = ComparisonSynthesisOutput.model_validate(raw)
                if output.direction_keys != direction_keys:
                    raise ValueError("comparison direction keys changed")
                _reject_phrases(output.summary, _PROHIBITED_COMPARISON_PHRASES)
                _reject_numeric_copies(output.summary)
                return MarketComparison(
                    summary=output.summary.strip(),
                    direction_keys=direction_keys,
                )
            except (ValidationError, ValueError, TypeError):
                continue
        return MarketComparison(
            summary=_programmatic_comparison(directions),
            direction_keys=direction_keys,
        )

    def _direction_input(
        self,
        context: DirectionRunContext,
        semantic_jobs: list[CollectedJob],
        statistics: DirectionStatistics,
    ) -> dict[str, Any]:
        """构造不含 JD、截图、Profile、聊天、Cookie 或路径的冻结综合输入。"""
        return {
            "direction": {
                "direction_name": context.direction.direction_name,
                "direction_key": context.direction.direction_key,
            },
            "semantic_jobs": [
                {
                    "job_id": job_identity(job),
                    "title": job.title,
                    "company_name": job.company_name,
                    "job_url": job.job_url,
                    "responsibilities": [item.model_dump() for item in job.responsibilities],
                    "requirements": [item.model_dump() for item in job.requirements],
                    "preferences": [item.model_dump() for item in job.preferences],
                    "evidence_items": [item.model_dump() for item in job.evidence_items],
                    "semantic_skills": list(job.semantic_skills),
                }
                for job in semantic_jobs
            ],
            "statistics": statistics.model_dump(mode="json"),
            "trend_observations": [
                observation.model_dump(mode="json")
                for observation in context.data.get("trend_observations") or ()
            ],
            "allowed_statistic_refs": sorted(_ALLOWED_STATISTIC_REFS),
        }

    def _validate_and_merge(
        self,
        context: DirectionRunContext,
        jobs: list[CollectedJob],
        statistics: DirectionStatistics,
        output: MarketSynthesisOutput,
    ) -> DirectionResult:
        """验证 Worker 的岗位/统计引用和文本边界，再合并程序冻结数字真值。"""
        semantic_map = {job_identity(job): job for job in jobs if job.semantic_valid}
        if not set(output.statistic_refs).issubset(_ALLOWED_STATISTIC_REFS):
            raise ValueError("synthesis references an unknown statistic")
        if len(output.statistic_refs) != len(set(output.statistic_refs)):
            raise ValueError("statistic_refs must be unique")
        career_ids = tuple(dict.fromkeys(output.career_definition_job_ids))
        if output.career_definition is None:
            if career_ids:
                raise ValueError("career definition ids require a definition")
        else:
            if len(career_ids) < 3 or not set(career_ids).issubset(semantic_map):
                raise ValueError("career definition requires three valid job references")
            _reject_phrases(output.career_definition, _PROHIBITED_SYNTHESIS_PHRASES)

        responsibility_themes = _validate_themes(
            output.responsibility_themes,
            semantic_map,
        )
        requirement_themes = _validate_themes(output.requirement_themes, semantic_map)
        preference_themes = _validate_themes(output.preference_themes, semantic_map)
        evidence_themes = _validate_themes(output.evidence_themes, semantic_map)
        skill_names = {
            skill.canonical_name
            for skill in (
                *statistics.skill_taxonomy.skills,
                *statistics.skill_taxonomy.emerging_or_isolated,
            )
        }
        if not set(output.skill_explanations).issubset(skill_names):
            raise ValueError("skill explanation references an unknown frozen skill")
        for text in (
            *output.skill_explanations.values(),
            output.salary_explanation or "",
        ):
            _reject_numeric_copies(text)
            _reject_phrases(text, _PROHIBITED_SYNTHESIS_PHRASES)
        trend_explanation = output.trend_explanation or ""
        if "搜索关注度" not in trend_explanation or "不代表招聘趋势" not in trend_explanation:
            raise ValueError("trend explanation must preserve the source boundary")

        representative_ids = list(career_ids[:3])
        if not representative_ids:
            for theme in (
                *responsibility_themes,
                *requirement_themes,
                *evidence_themes,
            ):
                for reference in theme.representative_jobs:
                    if reference.job_id not in representative_ids:
                        representative_ids.append(reference.job_id)
                    if len(representative_ids) == 3:
                        break
                if len(representative_ids) == 3:
                    break
        researched_at = self._now()
        return DirectionResult(
            direction_name=context.direction.direction_name,
            direction_key=context.direction.direction_key,
            direction_run_id=context.direction_run_id,
            researched_at=researched_at,
            expires_at=_add_calendar_months(
                researched_at,
                settings.market_research.validity_months,
            ),
            boss_keywords=context.direction.boss_keywords,
            trends_keywords=context.direction.trends_keywords,
            visited_cities=tuple(context.data.get("visited_cities") or ()),
            keyword_statuses=dict(context.data.get("keyword_statuses") or {}),
            budget_seconds=context.plan.budget_seconds,
            elapsed_seconds=context.budget.elapsed_seconds(),
            candidate_count=context.candidate_count,
            valid_job_count=statistics.valid_job_count,
            deduplicated_job_count=statistics.valid_job_count,
            semantic_analyzed_count=statistics.semantic_analyzed_count,
            company_count=statistics.company_count,
            sample_level=statistics.sample_level,
            career_definition=output.career_definition,
            responsibility_themes=responsibility_themes,
            requirement_themes=requirement_themes,
            preference_themes=preference_themes,
            evidence_themes=evidence_themes,
            skill_statistics=statistics.skill_taxonomy.skills,
            emerging_or_isolated_skills=statistics.skill_taxonomy.emerging_or_isolated,
            skill_explanations=dict(output.skill_explanations),
            experience_analysis=statistics.experience_analysis,
            education_distribution=statistics.education_distribution,
            salary_analysis=statistics.salary_analysis,
            salary_explanation=output.salary_explanation,
            industry_distribution=statistics.industry_distribution,
            company_size_distribution=statistics.company_size_distribution,
            trend_observations=tuple(context.data.get("trend_observations") or ()),
            trend_explanation=output.trend_explanation,
            sample_limitations=tuple(context.data.get("sample_limitations") or ()),
            representative_jobs=tuple(
                _job_reference(semantic_map[job_id])
                for job_id in representative_ids
                if job_id in semantic_map
            ),
            audit_refs=(),
        )

    def _call(self, system: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        """调用无工具 Worker；异常压缩为空输出并交给有限重试。"""
        try:
            return self.llm_call(system, json.dumps(payload, ensure_ascii=False))
        except Exception:
            return None


def build_synthesis_stage_handler(service: MarketSynthesisService) -> StageHandler:
    """创建 synthesizing（单方向综合）阶段处理器。"""

    def synthesize(context: DirectionRunContext) -> None:
        """只读取结构化语义与冻结统计，生成经引用校验的方向结果候选。"""
        service.synthesize_direction(context)

    return synthesize


def source_boundaries() -> tuple[str, ...]:
    """返回正式结果固定的数据来源和禁止推断边界。"""
    return _SOURCE_BOUNDARIES


class MarketCompletionPublisher:
    """MarketCompletionPublisher（市场完成发布器）原子发布结果并幂等写入普通 assistant 消息。"""

    def __init__(
        self,
        store: MarketResearchStore,
        session_store: SessionStore,
        synthesis_service: MarketSynthesisService,
        *,
        renderer: PlainTextMarketReportRenderer | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        """注入市场 Store、来源 Session Store、综合服务、纯文本渲染器和时钟。"""
        self.store = store  # 原子发布不可变结果版本的市场存储器
        self.session_store = session_store  # 写结果引用、确认闸门和普通消息的会话存储器
        self.synthesis_service = synthesis_service  # 多方向并列对照与程序兜底服务
        self.renderer = renderer or PlainTextMarketReportRenderer()  # 固定八章节纯文本渲染器
        self._now = now or (lambda: datetime.now(UTC))  # 顶层结果和完成消息时间戳时钟

    def publish(
        self,
        research_id: str,
        plan: ResearchPlan,
        successful: list[DirectionRunContext],
        failed: list[FailedDirection],
    ) -> None:
        """发布至少一个成功方向，绑定来源 Session，并用 completion_published_at 保证幂等。"""
        snapshot = self.store.read_status(research_id)
        if snapshot is None:
            raise RuntimeError("research snapshot does not exist before publication")
        latest_ref = self.store.read_latest_ref(research_id)
        if snapshot.completion_published_at is not None:
            if latest_ref is None:
                raise RuntimeError("completion marker exists without a formal result")
            self.session_store.bind_market_result_for_confirmation(
                snapshot.origin_session_id,
                latest_ref.model_dump(mode="json"),
            )
            return
        directions = tuple(
            DirectionResult.model_validate(context.data.get("direction_result"))
            for context in successful
        )
        if not directions:
            raise RuntimeError("completion publisher requires a successful direction")
        jobs_by_id: dict[str, CollectedJob] = {}
        for context in successful:
            for raw_job in context.data.get("jobs") or []:
                job = CollectedJob.model_validate(raw_job)
                jobs_by_id.setdefault(job_identity(job), job)
        existing_result: MarketResearchResult | None = None
        if latest_ref is not None:
            candidate = self.store.read_result(research_id, latest_ref.result_version)
            candidate_run_ids = {
                direction.direction_run_id
                for direction in candidate.successful_directions
                if isinstance(direction, DirectionResult)
            }
            current_run_ids = {direction.direction_run_id for direction in directions}
            if candidate.plan_id == plan.plan_id and candidate_run_ids == current_run_ids:
                existing_result = candidate
        result_version = (
            existing_result.result_version
            if existing_result is not None
            else self.store.next_result_version(research_id)
        )
        researched_at = self._now()
        result = existing_result or MarketResearchResult(
            research_id=research_id,
            plan_id=plan.plan_id,
            result_version=result_version,
            origin_session_id=snapshot.origin_session_id,
            status="partial_completed" if failed else "completed",
            researched_at=researched_at,
            expires_at=min(direction.expires_at for direction in directions),
            successful_directions=directions,
            failed_directions=tuple(failed),
            comparison=self.synthesis_service.synthesize_comparison(directions),
            source_boundaries=source_boundaries(),
            audit_refs=(
                "result.json",
                "jobs.json",
                "skills.json",
                "screenshots_manifest.json",
            ),
        )
        if existing_result is None:
            first_taxonomy = successful[0].data.get("skill_taxonomy")
            result_ref = self.store.publish_result(
                research_id,
                result,
                list(jobs_by_id.values()),
                first_taxonomy,
            )
        else:
            result_ref = latest_ref
            if result_ref is None:
                raise RuntimeError("existing result is missing latest reference")
        result_ref_payload = result_ref.model_dump(mode="json")
        self.store.append_event(
            research_id,
            {
                "event": "market.result.published",
                "result_version": result_ref.result_version,
                "published": True,
            },
        )
        self.session_store.bind_market_result_for_confirmation(
            snapshot.origin_session_id,
            result_ref_payload,
        )
        if snapshot.completion_published_at is None:
            report = self.renderer.render(result)
            self.session_store.append_message(
                snapshot.origin_session_id,
                "assistant",
                report,
                idempotency_key=(
                    f"market_result:{result_ref.research_id}:v{result_ref.result_version}"
                ),
            )
            latest_snapshot = self.store.read_status(research_id)
            if latest_snapshot is None:
                raise RuntimeError("research snapshot disappeared after publication")
            self.store.write_status(
                latest_snapshot.model_copy(
                    update={
                        "completion_published_at": self._now(),
                        "updated_at": self._now(),
                    }
                )
            )

    def publish_retry(
        self,
        parent_research_id: str,
        retry_id: str,
        origin_session_id: str,
        plan: ResearchPlan,
        successful: list[DirectionRunContext],
        prior_failed: tuple[FailedDirection, ...],
    ) -> None:
        """发布单方向重试的新版本；引用旧成功方向且不改变原主任务状态。"""
        if len(successful) != 1:
            raise RuntimeError("direction retry requires exactly one successful direction")
        context = successful[0]
        new_direction = DirectionResult.model_validate(context.data.get("direction_result"))
        self.store.adopt_retry_direction_temp(
            retry_id,
            parent_research_id,
            new_direction.direction_run_id,
        )
        latest_ref = self.store.read_latest_ref(parent_research_id)
        referenced = []
        resolved_directions: list[DirectionResult] = []
        if latest_ref is not None:
            previous = self.store.read_result(
                parent_research_id,
                latest_ref.result_version,
            )
            for entry in previous.successful_directions:
                resolved = self.store.resolve_direction_entry(entry)
                if resolved.direction_key == new_direction.direction_key:
                    continue
                referenced.append(
                    self.store.build_direction_reference(
                        parent_research_id,
                        latest_ref.result_version,
                        resolved.direction_key,
                    )
                )
                resolved_directions.append(resolved)
        resolved_directions.append(new_direction)
        remaining_failed = tuple(
            failure
            for failure in prior_failed
            if failure.direction_key != new_direction.direction_key
        )
        result_version = self.store.next_result_version(parent_research_id)
        researched_at = self._now()
        result = MarketResearchResult(
            research_id=parent_research_id,
            plan_id=plan.plan_id,
            result_version=result_version,
            origin_session_id=origin_session_id,
            status="partial_completed" if remaining_failed else "completed",
            researched_at=researched_at,
            expires_at=min(
                direction.expires_at
                for direction in (*referenced, new_direction)
            ),
            successful_directions=(*referenced, new_direction),
            failed_directions=remaining_failed,
            comparison=self.synthesis_service.synthesize_comparison(
                tuple(resolved_directions)
            ),
            source_boundaries=source_boundaries(),
            audit_refs=(
                "result.json",
                "jobs.json",
                "skills.json",
                "screenshots_manifest.json",
            ),
        )
        jobs = [
            CollectedJob.model_validate(job)
            for job in context.data.get("jobs") or []
        ]
        try:
            result_ref = self.store.publish_result(
                parent_research_id,
                result,
                jobs,
                context.data.get("skill_taxonomy"),
            )
        except Exception:
            self.store.cleanup_direction_temp(
                parent_research_id,
                new_direction.direction_run_id,
            )
            raise
        self.store.set_retry_published_result(retry_id, result_ref)
        self.store.append_event(
            retry_id,
            {
                "event": "market.result.published",
                "result_version": result_ref.result_version,
                "published": True,
            },
        )
        self.session_store.bind_market_result_for_confirmation(
            origin_session_id,
            result_ref.model_dump(mode="json"),
        )
        self.session_store.append_message(
            origin_session_id,
            "assistant",
            self.renderer.render(result),
            idempotency_key=(
                f"market_result:{result_ref.research_id}:v{result_ref.result_version}"
            ),
        )


def _validate_themes(
    candidates: tuple[SynthesisThemeCandidate, ...],
    job_map: dict[str, CollectedJob],
) -> tuple[ThemeSummary, ...]:
    """校验主题至少两个支持岗位、声明计数和最多三个代表岗位引用。"""
    themes: list[ThemeSummary] = []
    for candidate in candidates:
        support_ids = tuple(dict.fromkeys(candidate.support_job_ids))
        representative_ids = tuple(dict.fromkeys(candidate.representative_job_ids))
        if candidate.support_count != len(support_ids) or len(support_ids) < 2:
            raise ValueError("theme support_count does not match unique job ids")
        if not set(support_ids).issubset(job_map):
            raise ValueError("theme references an unknown semantic job")
        if not set(representative_ids).issubset(support_ids):
            raise ValueError("theme representative must belong to support ids")
        _reject_phrases(candidate.theme, _PROHIBITED_SYNTHESIS_PHRASES)
        themes.append(
            ThemeSummary(
                theme=candidate.theme.strip(),
                support_job_ids=support_ids,
                representative_jobs=tuple(
                    _job_reference(job_map[job_id]) for job_id in representative_ids
                ),
            )
        )
    return tuple(themes)


def _job_reference(job: CollectedJob) -> JobReference:
    """把清洗岗位压缩为报告可追溯的岗位身份、标题、公司和官方 URL。"""
    return JobReference(
        job_id=job_identity(job),
        title=job.title,
        company_name=job.company_name,
        job_url=job.job_url,
    )


def _reject_phrases(text: str, phrases: tuple[str, ...]) -> None:
    """拒绝排名、评分、推荐、匹配、需求强弱或城市对比等越界结论。"""
    if any(phrase in text for phrase in phrases):
        raise ValueError("synthesis contains a prohibited inference")


def _reject_numeric_copies(text: str) -> None:
    """拒绝 Worker 在解释中复制或创造数字，最终数字只由 renderer 合并冻结字段。"""
    if re.search(r"\d", text):
        raise ValueError("synthesis explanation cannot contain numeric copies")


def _programmatic_comparison(directions: tuple[DirectionResult, ...]) -> str:
    """当对照 Worker 两次失败时，用相同固定字段生成无排名的并列说明。"""
    segments: list[str] = []
    for direction in directions:
        themes = "、".join(theme.theme for theme in direction.responsibility_themes[:2])
        skills = "、".join(skill.canonical_name for skill in direction.skill_statistics[:3])
        detail = f"{direction.direction_name}：职责主题为{themes or '样本主题不足'}"
        if skills:
            detail += f"；技能主题为{skills}"
        segments.append(detail)
    return "；".join(segments) + "。以上仅为冻结样本字段的并列说明。"


def _add_calendar_months(value: datetime, months: int) -> datetime:
    """从调研时间增加自然月，并把月末日期收敛到目标月最后一天。"""
    absolute_month = value.year * 12 + value.month - 1 + months
    year, month_index = divmod(absolute_month, 12)
    month = month_index + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def _invoke_worker_json(system: str, user: str) -> dict[str, Any] | None:
    """固定使用现有 WORKER_MODEL、LLMRole.WORKER 和 temperature=0 的无工具综合调用。"""
    return invoke_json(
        system,
        user,
        role=LLMRole.WORKER,
        temperature=0,
    )
