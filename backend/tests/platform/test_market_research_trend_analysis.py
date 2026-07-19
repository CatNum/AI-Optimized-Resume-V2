from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from pydantic import ValidationError

from career_os.platform.market_research.models import (
    TrendDiagnostic,
    TrendResearchResult,
    TrendSeries,
    WeeklyTrendPoint,
)
from career_os.platform.market_research.trend_analysis import analyze_trend_series


def test_v2_result_rejects_old_visible_comparison_fields() -> None:
    """v2 正式结果不再接受双窗口百分比比较卡片。"""
    with pytest.raises(ValidationError):
        TrendResearchResult.model_validate(
            {
                "contract_version": "google_trends_web_v2",
                "query": "LLM Agent",
                "time_range": "past_12_months",
                "metric_kind": "visible_period_comparison",
                "percentage": 110,
                "comparison_label": "飙升",
            }
        )


def _series(values: list[float], keyword: str = "LLM Agent") -> TrendSeries:
    """构造按周连续的单关键词序列，供确定性统计测试复用。"""
    start = date(2025, 7, 7)
    return TrendSeries(
        page_url="https://trends.google.com/trends/explore?geo=CN&hl=zh-CN",
        fetched_at=datetime(2026, 7, 16, tzinfo=UTC),
        keywords=(keyword,),
        weekly_points=tuple(
            WeeklyTrendPoint(
                week_start=start + timedelta(days=index * 7),
                values={keyword: value},
            )
            for index, value in enumerate(values)
        ),
    )


def test_analysis_drops_oldest_boundary_week_and_includes_zero() -> None:
    """53 周序列丢弃最早边界点后，0 仍参与前半年均值。"""
    result = analyze_trend_series(
        _series([99.0, *([0.0] * 26), *([20.0] * 26)]),
        as_of_date=date(2026, 7, 16),
    )

    analysis = result.keyword_analyses[0]
    assert analysis.first_half is not None
    assert analysis.first_half.mean == 0.0
    assert analysis.second_half is not None
    assert analysis.second_half.mean == 20.0
    assert analysis.annual_change is not None
    assert analysis.annual_change.delta_points == 20.0
    assert analysis.annual_change.direction == "up"


def test_partial_series_requires_diagnostic_and_keeps_direction_insufficient() -> None:
    """只有一个有效关键词的部分结果不代表方向整体趋势。"""
    start = date(2025, 7, 14)
    series = TrendSeries(
        page_url="https://trends.google.com/trends/explore?geo=CN&hl=zh-CN",
        fetched_at=datetime(2026, 7, 16, tzinfo=UTC),
        keywords=("LLM Agent", "AI Agent", "Agent 开发"),
        weekly_points=tuple(
            WeeklyTrendPoint(
                week_start=start + timedelta(days=index * 7),
                values={"LLM Agent": 20.0 if index < 26 else 40.0},
            )
            for index in range(52)
        ),
    )

    result = analyze_trend_series(
        series,
        as_of_date=date(2026, 7, 16),
        diagnostic=TrendDiagnostic(
            page_state="partial_columns",
            attempt=1,
            expected_keyword_count=3,
            actual_series_count=1,
        ),
    )

    assert result.source_status == "partial"
    assert result.direction_summary == "insufficient_data"
    assert [item.keyword for item in result.keyword_analyses] == [
        "LLM Agent",
        "AI Agent",
        "Agent 开发",
    ]
