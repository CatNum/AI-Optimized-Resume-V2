from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING, Any, Iterable

from career_os.platform.market_research.errors import (
    MarketResearchError,
    MarketResearchErrorCode,
)
from career_os.platform.market_research.models import (
    CollectedJob,
    DirectionPlan,
    DirectionStatistics,
    ResearchStage,
    SkillTaxonomy,
)
from career_os.platform.market_research.parsers import normalize_company_name
from career_os.platform.market_research.skills import freeze_taxonomy_counts

if TYPE_CHECKING:
    from career_os.platform.market_research.runner import DirectionRunContext, StageHandler


_EXPERIENCE_LADDER: tuple[tuple[str, float, float], ...] = (
    ("1 年以内", 0.0, 1.0),
    ("1-3 年", 1.0, 3.0),
    ("3-5 年", 3.0, 5.0),
    ("5-10 年", 5.0, 10.0),
    ("10 年以上", 10.0, float("inf")),
)
_EDUCATION_ORDER = (
    "不限",
    "初中及以下",
    "中专/中技",
    "高中",
    "大专",
    "本科",
    "硕士",
    "博士",
    "未注明",
    "未识别",
)


class DeterministicStatisticsCalculator:
    """DeterministicStatisticsCalculator（确定性统计器）只用冻结岗位字段和岗位 ID 计数。"""

    def calculate(self, context: DirectionRunContext) -> DirectionStatistics:
        """计算两类分母、经验、学历、薪资、行业、规模、公司和技能统计。"""
        jobs = [
            CollectedJob.model_validate(job)
            for job in list(context.data.get("jobs") or [])
            if job.collection_valid
        ]
        valid_job_count = len(jobs)
        semantic_analyzed_count = sum(1 for job in jobs if job.semantic_valid)
        sample_level = classify_sample_level(valid_job_count, semantic_analyzed_count)
        taxonomy = SkillTaxonomy.model_validate(context.data.get("skill_taxonomy"))
        frozen_taxonomy = freeze_taxonomy_counts(taxonomy, jobs)

        statistics = DirectionStatistics(
            valid_job_count=valid_job_count,
            semantic_analyzed_count=semantic_analyzed_count,
            company_count=_company_count(jobs),
            sample_level=sample_level,
            experience_analysis=build_experience_analysis(jobs, context.direction),
            education_distribution=_ordered_distribution(
                (job.education_group or "未注明" for job in jobs),
                preferred_order=_EDUCATION_ORDER,
            ),
            salary_analysis=build_salary_analysis(jobs),
            industry_distribution=_ordered_distribution(
                (job.company_industry or "未知" for job in jobs)
            ),
            company_size_distribution=_ordered_distribution(
                (job.company_size or "未知" for job in jobs)
            ),
            skill_taxonomy=frozen_taxonomy,
        )
        context.record_statistics(statistics)
        return statistics


def classify_sample_level(
    valid_job_count: int,
    semantic_analyzed_count: int,
) -> str:
    """按固定岗位数和至少三条语义有效门槛返回 normal、limited 或 limited_no_reference。"""
    if valid_job_count < 3 or semantic_analyzed_count < 3:
        raise MarketResearchError(
            MarketResearchErrorCode.EXECUTION_FAILED,
            stage=ResearchStage.CALCULATING_STATISTICS.value,
            message="direction does not meet the minimum sample threshold",
        )
    if valid_job_count >= 30:
        return "normal"
    if valid_job_count >= 10:
        return "limited"
    return "limited_no_reference"


def build_salary_analysis(jobs: list[CollectedJob]) -> dict[str, Any]:
    """分别计算上下限中位数与最低下限到最高上限的观察区间，不计算平均薪资。"""
    if not jobs:
        raise ValueError("salary analysis requires at least one job")
    salary_mins = [job.salary_min for job in jobs]
    salary_maxes = [job.salary_max for job in jobs]
    return {
        "salary_min_median": rounded_integer_median(salary_mins),
        "salary_max_median": rounded_integer_median(salary_maxes),
        "observation_min": min(salary_mins),
        "observation_max": max(salary_maxes),
        "currency": "CNY",
        "period": "month",
        "includes_bonus_stock_or_total_compensation": False,
    }


def rounded_integer_median(values: Iterable[int]) -> int:
    """计算整数中位数；偶数样本的 .5 使用正数向上实现四舍五入到元。"""
    ordered = sorted(values)
    if not ordered:
        raise ValueError("median requires at least one value")
    middle = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle] + 1) // 2


def build_experience_analysis(
    jobs: list[CollectedJob],
    direction: DirectionPlan,
) -> dict[str, Any]:
    """生成经验分布、用户重点档位、相邻次要档位和组内薪资观察。"""
    distribution = _ordered_distribution(job.experience_group or "未注明" for job in jobs)
    focus_groups = _focus_experience_groups(
        direction.experience_min,
        direction.experience_max,
    )
    ladder_names = [name for name, _low, _high in _EXPERIENCE_LADDER]
    focus_indexes = {ladder_names.index(group) for group in focus_groups}
    secondary_indexes = {
        adjacent
        for index in focus_indexes
        for adjacent in (index - 1, index + 1)
        if 0 <= adjacent < len(ladder_names) and adjacent not in focus_indexes
    }
    secondary_groups = tuple(ladder_names[index] for index in sorted(secondary_indexes))
    other_groups = tuple(
        group
        for group in distribution
        if group not in set(focus_groups) | set(secondary_groups)
    )

    group_observations: dict[str, dict[str, Any]] = {}
    for group, sample_count in distribution.items():
        group_jobs = [job for job in jobs if (job.experience_group or "未注明") == group]
        observation: dict[str, Any] = {
            "sample_count": sample_count,
            "salary_observation_min": min(job.salary_min for job in group_jobs),
            "salary_observation_max": max(job.salary_max for job in group_jobs),
            "distribution_status": "stable" if sample_count >= 5 else "sample_only",
        }
        if sample_count >= 5:
            observation["salary_min_median"] = rounded_integer_median(
                job.salary_min for job in group_jobs
            )
            observation["salary_max_median"] = rounded_integer_median(
                job.salary_max for job in group_jobs
            )
        group_observations[group] = observation

    return {
        "experience_basis": direction.experience_basis,
        "configured_year_range": {
            "min": direction.experience_min,
            "max": direction.experience_max,
        },
        "distribution": distribution,
        "focus_groups": focus_groups,
        "secondary_groups": secondary_groups,
        "other_groups": other_groups,
        "group_observations": group_observations,
    }


def build_statistics_stage_handler(
    calculator: DeterministicStatisticsCalculator,
) -> StageHandler:
    """创建 calculating_statistics（确定性统计）阶段处理器，不调用 LLM 或浏览器。"""

    def calculate_statistics(context: DirectionRunContext) -> None:
        """从方向线程内存中的清洗岗位和技能岗位 ID 集合生成冻结统计。"""
        calculator.calculate(context)

    return calculate_statistics


def _focus_experience_groups(experience_min: int, experience_max: int) -> tuple[str, ...]:
    """把用户年限范围映射到内部相交的 BOSS 数值档位，边界相邻档位不重复算重点。"""
    if experience_min == experience_max:
        point = float(experience_min)
        matches = [
            name
            for name, low, high in _EXPERIENCE_LADDER
            if low <= point < high or point == high == float("inf")
        ]
    else:
        matches = [
            name
            for name, low, high in _EXPERIENCE_LADDER
            if max(low, float(experience_min)) < min(high, float(experience_max))
        ]
    if matches:
        return tuple(matches)
    return ("1 年以内",) if experience_max < 1 else ("10 年以上",)


def _company_count(jobs: list[CollectedJob]) -> int:
    """公司 ID 优先，缺失时使用规范公司名，返回不同公司数量。"""
    identities = {
        f"company_id:{job.company_id}"
        if job.company_id
        else f"company_name:{normalize_company_name(job.company_name)}"
        for job in jobs
    }
    return len(identities)


def _ordered_distribution(
    values: Iterable[str],
    *,
    preferred_order: tuple[str, ...] = (),
) -> dict[str, int]:
    """确定性输出分类计数：固定已知顺序在前，其余分类按文本排序。"""
    counts = Counter(values)
    result: dict[str, int] = {}
    for name in preferred_order:
        if counts.get(name):
            result[name] = counts.pop(name)
    for name in sorted(counts):
        result[name] = counts[name]
    return result
