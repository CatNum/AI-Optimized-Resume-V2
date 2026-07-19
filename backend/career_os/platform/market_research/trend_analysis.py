"""Google Trends 周度序列的确定性统计函数。

本模块只把已经校验并绑定关键词的 ``TrendSeries`` 转为派生统计；不访问网页、
不读取时钟，也不修改 Store，因此同一输入始终产生同一结果。
"""

from __future__ import annotations

from collections import Counter
from datetime import date
from statistics import fmean

from .models import (
    KeywordTrendAnalysis,
    TrendChange,
    TrendDiagnostic,
    TrendPeriodAverage,
    TrendRankingItem,
    TrendResearchResult,
    TrendSeries,
)


_ANNUAL_WEEK_COUNT = 52
_HALF_YEAR_WEEK_COUNT = 26
_MONTH_MINIMUM_WEEK_COUNT = 3
_DIRECTION_THRESHOLD = 10.0


def _direction(delta_points: float) -> str:
    """把 delta_points（后期均值减前期均值）映射为稳定趋势方向。"""
    if delta_points >= _DIRECTION_THRESHOLD:
        return "up"
    if delta_points <= -_DIRECTION_THRESHOLD:
        return "down"
    return "flat"


def _period_average(
    *, label: str, points: list[tuple[date, float]], complete: bool
) -> TrendPeriodAverage:
    """构造一个期间均值；points（周点）为空时明确保留空日期和均值。"""
    if not points:
        return TrendPeriodAverage(
            label=label,
            start_date=None,
            end_date=None,
            point_count=0,
            mean=None,
            complete=complete,
        )
    return TrendPeriodAverage(
        label=label,
        start_date=points[0][0],
        end_date=points[-1][0],
        point_count=len(points),
        mean=fmean(value for _, value in points),
        complete=complete,
    )


def _change(first: TrendPeriodAverage, second: TrendPeriodAverage) -> TrendChange | None:
    """计算相邻完整期间的点差；缺失或不足期间不生成正式趋势判断。"""
    if not first.complete or not second.complete or first.mean is None or second.mean is None:
        return None
    delta_points = second.mean - first.mean
    return TrendChange(
        from_label=first.label,
        to_label=second.label,
        delta_points=delta_points,
        direction=_direction(delta_points),
    )


def _month_key(value: date) -> tuple[int, int]:
    """返回日期所属的 (year, month)（自然月键），用于按 UTC 日期分组。"""
    return value.year, value.month


def _source_status(diagnostic: TrendDiagnostic | None) -> str:
    """根据采集诊断确定来源可用等级；没有诊断即为完整成功。"""
    if diagnostic is None:
        return "success"
    if diagnostic.page_state == "partial_columns":
        return "partial"
    if diagnostic.page_state == "no_data":
        return "no_data"
    return "degraded"


def _direction_summary(analyses: tuple[KeywordTrendAnalysis, ...]) -> str:
    """按年度有效关键词的多数一致规则生成方向级概括，不聚合热度数值。"""
    directions = [
        item.annual_change.direction
        for item in analyses
        if item.annual_change is not None
        and item.annual_change.direction in {"up", "down", "flat"}
    ]
    if len(directions) <= 1:
        return "insufficient_data"
    counts = Counter(directions)
    direction, count = counts.most_common(1)[0]
    if len(directions) == 2:
        return direction if count == 2 else "divergent"
    return direction if count >= 2 else "divergent"


def _rank(items: list[tuple[str, float]]) -> tuple[TrendRankingItem, ...]:
    """按同页归一化均值降序排序；同分时保持冻结关键词的输入顺序。"""
    ordered = sorted(enumerate(items), key=lambda pair: (-pair[1][1], pair[0]))
    return tuple(
        TrendRankingItem(keyword=keyword, mean=mean, rank=index + 1)
        for index, (_, (keyword, mean)) in enumerate(ordered)
    )


def analyze_trend_series(
    series: TrendSeries,
    *,
    as_of_date: date,
    diagnostic: TrendDiagnostic | None = None,
) -> TrendResearchResult:
    """计算年度、月度、排序和方向概括。

    series（趋势原始序列）中的 values 已由采集器按表头绑定到冻结关键词；
    as_of_date（UTC 参考日期）由调用方显式传入，避免服务器本地时区改变统计边界。
    """
    analyses: list[KeywordTrendAnalysis] = []
    annual_candidates: list[tuple[str, float]] = []
    recent_candidates: list[tuple[str, float]] = []
    current_month = _month_key(as_of_date)

    for keyword in series.keywords:
        all_points = [
            (point.week_start, point.values[keyword])
            for point in series.weekly_points
            if keyword in point.values
        ]
        annual_points = all_points[-_ANNUAL_WEEK_COUNT:]
        if len(annual_points) == _ANNUAL_WEEK_COUNT:
            first_half = _period_average(
                label="前 26 周", points=annual_points[:_HALF_YEAR_WEEK_COUNT], complete=True
            )
            second_half = _period_average(
                label="后 26 周", points=annual_points[_HALF_YEAR_WEEK_COUNT:], complete=True
            )
            annual_change = _change(first_half, second_half)
            annual_candidates.append((keyword, fmean(value for _, value in annual_points)))
        else:
            first_half = None
            second_half = None
            annual_change = None

        month_points: dict[tuple[int, int], list[tuple[date, float]]] = {}
        for week_start, value in all_points:
            month_points.setdefault(_month_key(week_start), []).append((week_start, value))
        complete_month_keys = sorted(key for key in month_points if key < current_month)[-3:]
        recent_months = tuple(
            _period_average(
                label=f"{year:04d}-{month:02d}",
                points=month_points[key],
                complete=len(month_points[key]) >= _MONTH_MINIMUM_WEEK_COUNT,
            )
            for key in complete_month_keys
            for year, month in [key]
        )
        monthly_changes = tuple(
            change
            for change in (
                _change(recent_months[index], recent_months[index + 1])
                for index in range(len(recent_months) - 1)
            )
            if change is not None
        )
        if len(recent_months) == 3 and all(item.complete and item.mean is not None for item in recent_months):
            recent_candidates.append((keyword, fmean(item.mean for item in recent_months if item.mean is not None)))

        current_points = month_points.get(current_month, [])
        current_partial_month = (
            _period_average(label="截至当前月（未参与正式趋势判断）", points=current_points, complete=False)
            if current_points
            else None
        )
        analyses.append(
            KeywordTrendAnalysis(
                keyword=keyword,
                first_half=first_half,
                second_half=second_half,
                annual_change=annual_change,
                recent_months=recent_months,
                monthly_changes=monthly_changes,
                current_partial_month=current_partial_month,
            )
        )

    frozen_analyses = tuple(analyses)
    return TrendResearchResult(
        series=series,
        source_status=_source_status(diagnostic),
        keyword_analyses=frozen_analyses,
        direction_summary=_direction_summary(frozen_analyses),
        annual_ranking=_rank(annual_candidates) if len(annual_candidates) >= 2 else (),
        recent_ranking=_rank(recent_candidates) if len(recent_candidates) >= 2 else (),
        diagnostic=diagnostic,
    )
