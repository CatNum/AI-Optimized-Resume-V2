from __future__ import annotations

import json
import unicodedata
from collections import Counter
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from career_os.agents.lc.client import invoke_json
from career_os.agents.lc.models import LLMRole
from career_os.platform.market_research.errors import (
    MarketResearchError,
    MarketResearchErrorCode,
)
from career_os.platform.market_research.models import (
    CollectedJob,
    JobSemanticItem,
    ResearchStage,
    SemanticValidationAudit,
)
from career_os.platform.market_research.sampling import job_identity
from career_os.platform.market_research.skills import DynamicSkillTaxonomy
from career_os.platform.prompt.loader import load_market_research_extraction_prompt

if TYPE_CHECKING:
    from career_os.platform.market_research.runner import (
        DirectionRunContext,
        StageHandler,
    )


LLMCall = Callable[[str, str], dict[str, Any] | None]
"""LLMCall（受限模型调用）只接收 System 与 user JSON，并返回解析后的 JSON 对象。"""


class EvidenceSemanticItem(BaseModel):
    """EvidenceSemanticItem（带依据语义项）仅在运行时存在，验证后丢弃 evidence。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    label: str = Field(min_length=1, max_length=200)  # 规范化职责、要求、优先或岗位证据主题
    category: str | None = Field(default=None, max_length=100)  # 可选语义分类
    evidence: str = Field(min_length=1, max_length=300)  # 对应内存 JD 中的最短连续原文依据


class EvidenceSkillCandidate(BaseModel):
    """EvidenceSkillCandidate（带依据技能候选）保存规范名、别名、用途和临时原文依据。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    canonical_name: str = Field(min_length=1, max_length=100)  # LLM 提议或复用的规范技能名
    aliases: tuple[str, ...] = Field(default=(), max_length=10)  # 当前 JD 中出现的技能别名
    usage: Literal["required", "preferred", "mention"]  # 必需、优先或普通提及
    evidence: str = Field(min_length=1, max_length=300)  # 对应内存 JD 中的最短连续原文依据


class JobExtractionOutput(BaseModel):
    """JobExtractionOutput（逐岗位提取输出）要求稳定身份和五类结构化结论。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    job_id: str = Field(min_length=1, max_length=200)  # 必须逐字复制输入的岗位身份
    responsibilities: tuple[EvidenceSemanticItem, ...] = Field(default=(), max_length=20)
    requirements: tuple[EvidenceSemanticItem, ...] = Field(default=(), max_length=20)
    preferences: tuple[EvidenceSemanticItem, ...] = Field(default=(), max_length=20)
    evidence_items: tuple[EvidenceSemanticItem, ...] = Field(default=(), max_length=20)
    skills: tuple[EvidenceSkillCandidate, ...] = Field(default=(), max_length=30)

    @model_validator(mode="after")
    def require_core_semantics(self) -> JobExtractionOutput:
        """语义有效岗位至少需要一条职责或任职要求，避免空壳输出被计为成功。"""
        if not self.responsibilities and not self.requirements:
            raise ValueError("responsibilities or requirements are required")
        return self


class SemanticExtractionEngine:
    """SemanticExtractionEngine（岗位语义提取引擎）执行 10/10/剩余策略和依据校验。"""

    def __init__(self, *, llm_call: LLMCall | None = None) -> None:
        """注入无工具 JSON 调用 seam；默认固定 Worker 模型角色和 temperature=0。"""
        self.llm_call = llm_call or _invoke_worker_json  # 不接 tools 的现有 Worker 模型调用
        self.system_prompt = load_market_research_extraction_prompt()  # 不包含任何岗位 JD 的系统指令

    def extract(self, context: DirectionRunContext, *, fallback: bool = False) -> None:
        """提取方向岗位并冻结动态技能词表；无论成功失败都从上下文移除原始 JD。"""
        jobs = list(context.data.get("jobs") or [])
        raw_descriptions = dict(context.data.get("raw_job_descriptions") or {})
        if not jobs or not raw_descriptions:
            raise MarketResearchError(
                MarketResearchErrorCode.EXECUTION_FAILED,
                stage=ResearchStage.EXTRACTING_SEMANTICS.value,
                message="collected jobs or in-memory JD is missing",
            )
        taxonomy = DynamicSkillTaxonomy(context.direction.direction_key)
        outputs: dict[str, JobExtractionOutput] = {}
        processed: set[str] = set()
        extraction_succeeded = False
        try:
            if fallback:
                batch = [job for job in jobs if job_identity(job) in raw_descriptions]
                self._match_known_skills(batch, raw_descriptions, taxonomy)
                outputs.update(
                    self._extract_batch(
                        context,
                        batch,
                        raw_descriptions,
                        taxonomy,
                        discovery_source="fallback",
                        allow_budget_exception=True,
                    )
                )
                processed.update(job_identity(job) for job in batch)
            else:
                for keyword in context.direction.boss_keywords:
                    keyword_jobs = [
                        job
                        for job in jobs
                        if keyword in job.matched_keywords and job_identity(job) not in processed
                    ]
                    first_ten = keyword_jobs[:10]
                    middle_ten = keyword_jobs[10:20]
                    remaining = keyword_jobs[20:]
                    for batch_name, batch in (
                        ("first10", first_ten),
                        ("middle10", middle_ten),
                    ):
                        self._match_known_skills(batch, raw_descriptions, taxonomy)
                        if batch and context.budget.remaining_seconds() > 0:
                            outputs.update(
                                self._extract_batch(
                                    context,
                                    batch,
                                    raw_descriptions,
                                    taxonomy,
                                    discovery_source=f"{keyword}:{batch_name}",
                                    allow_budget_exception=False,
                                )
                            )
                        processed.update(job_identity(job) for job in batch)
                    self._match_known_skills(remaining, raw_descriptions, taxonomy)
                    processed.update(job_identity(job) for job in remaining)

                unprocessed = [job for job in jobs if job_identity(job) not in processed]
                self._match_known_skills(unprocessed, raw_descriptions, taxonomy)

            updated_jobs = self._apply_valid_outputs(
                jobs,
                raw_descriptions,
                outputs,
                taxonomy,
            )
            semantic_count = sum(1 for job in updated_jobs if job.semantic_valid)
            context.semantic_analyzed_count = semantic_count
            context.data["jobs"] = updated_jobs
            context.data["skill_taxonomy"] = taxonomy.freeze(
                valid_job_count=len(jobs),
                semantic_analyzed_count=semantic_count,
            )
            if semantic_count < 3:
                raise MarketResearchError(
                    MarketResearchErrorCode.EXECUTION_FAILED,
                    stage=ResearchStage.EXTRACTING_SEMANTICS.value,
                    message="fewer than three jobs passed semantic validation",
                )
            extraction_succeeded = True
        finally:
            raw_descriptions.clear()
            if not fallback or extraction_succeeded:
                context.data.pop("raw_job_descriptions", None)

    def _extract_batch(
        self,
        context: DirectionRunContext,
        jobs: list[CollectedJob],
        raw_descriptions: dict[str, str],
        taxonomy: DynamicSkillTaxonomy,
        *,
        discovery_source: str,
        allow_budget_exception: bool,
    ) -> dict[str, JobExtractionOutput]:
        """整批顶层失败重试一次，随后只把缺失、重复、Schema 或依据失败岗位重试一次。"""
        expected = {job_identity(job): job for job in jobs}
        payload: dict[str, Any] | None = None
        for top_attempt in range(2):
            try:
                payload = self._call_batch(
                    context,
                    jobs,
                    raw_descriptions,
                    taxonomy,
                    discover_new_skills=True,
                    allow_budget_exception=allow_budget_exception,
                )
                _require_top_level(payload)
                break
            except _TopLevelInvalid:
                payload = None
                if top_attempt == 1:
                    self._record_semantic_failures(
                        context,
                        jobs,
                        {job_identity(job): ("top_level_invalid", ("__root__",)) for job in jobs},
                        attempt=2,
                    )
                    return {}
        if payload is None:
            return {}

        valid, failures = _validate_job_outputs(payload, expected, raw_descriptions)
        if failures:
            retry_jobs = [expected[job_id] for job_id in failures]
            try:
                retry_payload = self._call_batch(
                    context,
                    retry_jobs,
                    raw_descriptions,
                    taxonomy,
                    discover_new_skills=True,
                    allow_budget_exception=allow_budget_exception,
                )
                _require_top_level(retry_payload)
                retry_valid, retry_failures = _validate_job_outputs(
                    retry_payload,
                    {job_identity(job): job for job in retry_jobs},
                    raw_descriptions,
                )
                valid.update(retry_valid)
                self._record_semantic_failures(context, retry_jobs, retry_failures, attempt=2)
            except _TopLevelInvalid:
                self._record_semantic_failures(
                    context,
                    retry_jobs,
                    {job_identity(job): ("top_level_invalid", ("__root__",)) for job in retry_jobs},
                    attempt=2,
                )

        for output in valid.values():
            taxonomy.discover_from_output(
                output.skills,
                discovery_source=discovery_source,
            )
        return valid

    @staticmethod
    def _record_semantic_failures(
        context: DirectionRunContext,
        jobs: list[CollectedJob],
        failures: dict[str, tuple[str, tuple[str, ...]]],
        *,
        attempt: int,
    ) -> None:
        """将最终失败岗位写为脱敏审计；不传递 JD、evidence 或模型错误原文。"""
        for job in jobs:
            failure = failures.get(job_identity(job))
            if failure is None:
                continue
            failure_type, field_paths = failure
            context.record_semantic_validation_failure(
                SemanticValidationAudit(
                    job_id=job_identity(job),
                    job_url=job.job_url,
                    failure_type=failure_type,
                    field_paths=field_paths,
                    attempt=attempt,
                    occurred_at=datetime.now(UTC),
                )
            )

    def _call_batch(
        self,
        context: DirectionRunContext,
        jobs: list[CollectedJob],
        raw_descriptions: dict[str, str],
        taxonomy: DynamicSkillTaxonomy,
        *,
        discover_new_skills: bool,
        allow_budget_exception: bool,
    ) -> dict[str, Any] | None:
        """把 JD 仅放入 user JSON 数据字段，并在发起真实调用前递增 LLM 尝试计数。"""
        if not allow_budget_exception and context.budget.remaining_seconds() <= 0:
            raise MarketResearchError(
                MarketResearchErrorCode.BUDGET_EXHAUSTED,
                stage=ResearchStage.EXTRACTING_SEMANTICS.value,
            )
        user_payload = {
            "known_skills": taxonomy.known_skills_payload(),
            "discover_new_skills": discover_new_skills,
            "jobs": [
                {
                    "job_id": job_identity(job),
                    "jd": raw_descriptions[job_identity(job)],
                }
                for job in jobs
            ],
        }
        context.llm_attempt_count += 1
        try:
            return self.llm_call(
                self.system_prompt,
                json.dumps(user_payload, ensure_ascii=False),
            )
        except Exception:
            return None

    @staticmethod
    def _match_known_skills(
        jobs: list[CollectedJob],
        raw_descriptions: dict[str, str],
        taxonomy: DynamicSkillTaxonomy,
    ) -> None:
        """在当前词表时点执行 mention 匹配；之后新发现技能不回扫这些岗位。"""
        for job in jobs:
            identity = job_identity(job)
            raw_jd = raw_descriptions.get(identity)
            if raw_jd is not None:
                taxonomy.match_mentions(identity, raw_jd)

    @staticmethod
    def _apply_valid_outputs(
        jobs: list[CollectedJob],
        raw_descriptions: dict[str, str],
        outputs: dict[str, JobExtractionOutput],
        taxonomy: DynamicSkillTaxonomy,
    ) -> list[CollectedJob]:
        """把通过校验的五类结构化字段写入岗位，绝不复制 evidence 或原始 JD。"""
        updated: list[CollectedJob] = []
        for job in jobs:
            identity = job_identity(job)
            output = outputs.get(identity)
            raw_jd = raw_descriptions.get(identity)
            if output is None or raw_jd is None:
                updated.append(job)
                continue
            semantic_skills = taxonomy.record_semantic_usage(identity, output.skills)
            updated.append(
                job.model_copy(
                    update={
                        "semantic_valid": True,
                        "responsibilities": _strip_evidence(output.responsibilities),
                        "requirements": _strip_evidence(output.requirements),
                        "preferences": _strip_evidence(output.preferences),
                        "evidence_items": _strip_evidence(output.evidence_items),
                        "semantic_skills": semantic_skills,
                    }
                )
            )
        return updated


def build_extraction_stage_handler(engine: SemanticExtractionEngine) -> StageHandler:
    """创建常规 extracting_semantics（语义提取）阶段处理器。"""

    def extract_semantics(context: DirectionRunContext) -> None:
        """按每关键词 10/10/剩余策略提取，并在完成后清除内存 JD。"""
        engine.extract(context, fallback=False)

    return extract_semantics


def build_fallback_extractor(engine: SemanticExtractionEngine) -> StageHandler:
    """创建预算外唯一兜底批量处理器；整批一次，失败子集仍只重试一次。"""

    def extract_fallback(context: DirectionRunContext) -> None:
        """仅由 Runner 在零常规调用且至少一个有效岗位时调用。"""
        engine.extract(context, fallback=True)

    return extract_fallback


class _TopLevelInvalid(Exception):
    """_TopLevelInvalid（顶层 JSON 无效）触发整批最多一次重试。"""


def _require_top_level(payload: dict[str, Any] | None) -> None:
    """校验顶层是只含 jobs 数组的 JSON 对象；逐岗位 Schema 留给子集重试。"""
    if not isinstance(payload, dict) or set(payload) != {"jobs"}:
        raise _TopLevelInvalid()
    if not isinstance(payload.get("jobs"), list):
        raise _TopLevelInvalid()


def _validate_job_outputs(
    payload: dict[str, Any],
    expected: dict[str, CollectedJob],
    raw_descriptions: dict[str, str],
) -> tuple[dict[str, JobExtractionOutput], dict[str, tuple[str, tuple[str, ...]]]]:
    """逐岗位检查缺失、重复、Schema 和原文依据，返回有效输出与一次重试 ID。"""
    entries = payload.get("jobs")
    if not isinstance(entries, list):
        return {}, {job_id: ("top_level_invalid", ("__root__",)) for job_id in expected}
    raw_ids = [
        entry.get("job_id")
        for entry in entries
        if isinstance(entry, dict) and isinstance(entry.get("job_id"), str)
    ]
    duplicate_ids = {job_id for job_id, count in Counter(raw_ids).items() if count > 1}
    valid: dict[str, JobExtractionOutput] = {}
    failures: dict[str, tuple[str, tuple[str, ...]]] = {
        job_id: ("duplicate_output", ("job_id",))
        for job_id in duplicate_ids & expected.keys()
    }
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        raw_id = entry.get("job_id")
        if not isinstance(raw_id, str) or raw_id not in expected or raw_id in duplicate_ids:
            continue
        try:
            parsed = JobExtractionOutput.model_validate(entry)
        except ValidationError as error:
            failures[raw_id] = (
                "schema_validation",
                tuple(
                    dict.fromkeys(
                        ".".join(str(segment) for segment in item["loc"]) or "__root__"
                        for item in error.errors()
                    )
                )[:10]
                or ("__root__",),
            )
            continue
        raw_jd = raw_descriptions.get(raw_id)
        if raw_jd is None or not _all_evidence_exists(parsed, raw_jd):
            failures[raw_id] = ("evidence_not_found", ("evidence",))
            continue
        valid[raw_id] = parsed
    for job_id in expected:
        if job_id not in valid and job_id not in failures:
            failures[job_id] = ("missing_output", ("__root__",))
    return valid, {job_id: failures[job_id] for job_id in expected if job_id in failures}


def _all_evidence_exists(output: JobExtractionOutput, raw_jd: str) -> bool:
    """要求每条临时最短原文依据能在对应内存 JD 中直接找到。"""
    evidence_values = [
        item.evidence
        for group in (
            output.responsibilities,
            output.requirements,
            output.preferences,
            output.evidence_items,
            output.skills,
        )
        for item in group
    ]
    normalized_jd = unicodedata.normalize("NFKC", raw_jd)
    return all(unicodedata.normalize("NFKC", evidence) in normalized_jd for evidence in evidence_values)


def _strip_evidence(items: tuple[EvidenceSemanticItem, ...]) -> tuple[JobSemanticItem, ...]:
    """只保留规范 label 和 category，丢弃运行时 evidence 原文。"""
    return tuple(JobSemanticItem(label=item.label, category=item.category) for item in items)


def _invoke_worker_json(system: str, user: str) -> dict[str, Any] | None:
    """固定使用现有 WORKER_MODEL、LLMRole.WORKER 和 temperature=0 的无工具 JSON 调用。"""
    return invoke_json(
        system,
        user,
        role=LLMRole.WORKER,
        temperature=0,
    )
