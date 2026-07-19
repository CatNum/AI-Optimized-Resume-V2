"""只通过 Google Trends 可见无障碍表格采集周度搜索关注度。"""

from __future__ import annotations

import random
import re
import time
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any, Callable

from career_os.config import settings
from career_os.platform.market_research.models import (
    DirectionPlan,
    ResearchStage,
    TrendDiagnostic,
    TrendResearchResult,
    TrendSeries,
    WeeklyTrendPoint,
)
from career_os.platform.market_research.page_contracts import (
    PageChangedError,
    TrendsPageContract,
    validate_external_url,
)
from career_os.platform.market_research.trend_analysis import analyze_trend_series

if TYPE_CHECKING:
    from career_os.platform.market_research.runner import ActiveBudget, DirectionRunContext, StageHandler


_DEFAULT_RETRY_DELAYS = (10.0,)
_TRANSIENT_DELAY = 5.0
_RENDER_WAIT_SECONDS = 5.0
_POLL_SECONDS = 0.25
_HEADER_DECORATIONS = ("搜索字词：", "搜索字词:", "Search term:")


class GoogleTrendsCollector:
    """GoogleTrendsCollector（搜索关注度采集器）读取一次多关键词十二个月表格并可降级。"""

    def __init__(
        self,
        *,
        contract: TrendsPageContract | None = None,
        retry_times: int | None = None,
        retry_delays: tuple[float, ...] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        jitter_factor: Callable[[], float] | None = None,
        navigate_handler: Callable[[str], Any] | None = None,
        user_action_handler: Callable[[str], None] | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        """注入可替换的页面、等待和时钟依赖，便于测试受控状态机。"""
        self.contract = contract or TrendsPageContract()
        self.retry_times = settings.market_research.trends_retry_times if retry_times is None else retry_times
        self.retry_delays = retry_delays or _DEFAULT_RETRY_DELAYS
        if not 0 <= self.retry_times <= 1 or len(self.retry_delays) < self.retry_times:
            raise ValueError("retry_times must be between zero and one")
        self._sleep = sleep
        self._jitter_factor = jitter_factor or (lambda: random.uniform(0.8, 1.2))
        self.navigate_handler = navigate_handler
        self.user_action_handler = user_action_handler
        self._now = now or (lambda: datetime.now(UTC))

    def collect(self, direction: DirectionPlan, page: Any, budget: ActiveBudget) -> TrendResearchResult:
        """以冻结关键词构造一个共同归一化页面，任何 Trends 故障都返回来源降级结果。"""
        query = ",".join(direction.trends_keywords)
        url = validate_external_url(
            self.contract.build_explore_url(query, "past_12_months"), self.contract.allowed_hosts
        )
        rate_limit_attempt = 0
        transient_attempted = False
        for attempt in range(1, self.retry_times + 2):
            self._navigate(page, url)
            if self.contract.user_action_required(page):
                if self.user_action_handler is None:
                    return self._degraded(direction, url, "verification_required", attempt)
                self.user_action_handler(url)
            state = self._wait_for_terminal_state(page, budget)
            if state is None:
                self._refresh(page, url)
                state = self._wait_for_terminal_state(page, budget)
                if state is None:
                    return self._degraded(direction, url, "render_timeout", 2)
            if state == "rate_limited":
                if rate_limit_attempt >= self.retry_times or not self._wait(self.retry_delays[rate_limit_attempt], budget):
                    return self._degraded(direction, url, "rate_limited", attempt)
                rate_limit_attempt += 1
                continue
            if state == "transient_error":
                if transient_attempted or not self._wait(_TRANSIENT_DELAY, budget):
                    return self._degraded(direction, url, "transient_error", attempt)
                transient_attempted = True
                continue
            if state == "no_data":
                return self._no_data(direction, url, attempt)
            if state != "data_ready":
                return self._degraded(direction, url, "render_timeout", attempt)
            try:
                table = self.contract.read_required(page, self.contract.interest_over_time_table, stage=ResearchStage.COLLECTING_TRENDS.value)
                points = parse_weekly_points(table, direction.trends_keywords, contract=self.contract)
            except PageChangedError as error:
                return self._degraded(direction, url, "page_changed", attempt, failed_field=error.field_name)
            actual_keywords = set().union(*(point.values.keys() for point in points)) if points else set()
            diagnostic = None
            if actual_keywords != set(direction.trends_keywords):
                diagnostic = TrendDiagnostic(
                    page_state="partial_columns", attempt=min(attempt, 2),
                    expected_keyword_count=len(direction.trends_keywords), actual_series_count=len(actual_keywords),
                )
            series = TrendSeries(page_url=url, fetched_at=self._now(), keywords=direction.trends_keywords, weekly_points=points)
            return analyze_trend_series(series, as_of_date=self._now().date(), diagnostic=diagnostic)
        return self._degraded(direction, url, "rate_limited", self.retry_times + 1)

    def _navigate(self, page: Any, url: str) -> None:
        """导航到已白名单校验的 URL，并拒绝最终落到非官方 host。"""
        if self.navigate_handler is None:
            page.get(url)
        else:
            self.navigate_handler(url)
        validate_external_url(str(getattr(page, "url", url)), self.contract.allowed_hosts)

    def _state(self, page: Any) -> str:
        """识别页面终止状态，明确 429 优先于通用技术错误。"""
        if self.contract.rate_limited(page):
            return "rate_limited"
        if self.contract.technical_retry_required(page):
            return "transient_error"
        if self.contract.read_optional(page, self.contract.no_data_marker) is not None:
            return "no_data"
        if self.contract.read_optional(page, self.contract.interest_over_time_table) is not None:
            return "data_ready"
        return "render_timeout"

    def _wait_for_terminal_state(self, page: Any, budget: ActiveBudget) -> str | None:
        """每 0.25 秒轮询最多五秒；未命中终止状态时交由调用方执行唯一一次刷新。"""
        remaining_at_start = budget.remaining_seconds()
        while remaining_at_start - budget.remaining_seconds() < _RENDER_WAIT_SECONDS:
            state = self._state(page)
            if state != "render_timeout":
                return state
            wait_seconds = min(
                _POLL_SECONDS,
                _RENDER_WAIT_SECONDS - (remaining_at_start - budget.remaining_seconds()),
                budget.remaining_seconds(),
            )
            if wait_seconds <= 0:
                return None
            self._sleep(wait_seconds)
        return None

    def _refresh(self, page: Any, url: str) -> None:
        """最多刷新当前页一次；测试替身没有 refresh 时以同一 URL 重新导航模拟刷新。"""
        refresh = getattr(page, "refresh", None)
        if callable(refresh):
            refresh()
        else:
            self._navigate(page, url)

    def _wait(self, seconds: float, budget: ActiveBudget) -> bool:
        """只在剩余有效预算足够时等待，避免 Trends 吞掉 BOSS 的预算。"""
        factor = float(self._jitter_factor())
        if not 0.8 <= factor <= 1.2:
            raise ValueError("jitter_factor must be between 0.8 and 1.2")
        delay = seconds * factor
        if budget.remaining_seconds() < delay:
            return False
        self._sleep(delay)
        return True

    def _series(self, direction: DirectionPlan, url: str) -> TrendSeries:
        """构造空周点序列，用于无数据和技术降级的统一可审计结果。"""
        return TrendSeries(page_url=url, fetched_at=self._now(), keywords=direction.trends_keywords)

    def _no_data(self, direction: DirectionPlan, url: str, attempt: int) -> TrendResearchResult:
        """记录页面明确无数据，不把它伪装成页面故障。"""
        diagnostic = TrendDiagnostic(page_state="no_data", attempt=min(attempt, 2), expected_keyword_count=len(direction.trends_keywords), actual_series_count=0)
        return analyze_trend_series(self._series(direction, url), as_of_date=self._now().date(), diagnostic=diagnostic)

    def _degraded(self, direction: DirectionPlan, url: str, page_state: str, attempt: int, *, failed_field: str | None = None) -> TrendResearchResult:
        """把仅影响 Trends 的故障转换为结构化来源限制，供 Runner 继续 BOSS 阶段。"""
        diagnostic = TrendDiagnostic(page_state=page_state, failed_field=failed_field, attempt=min(attempt, 2), expected_keyword_count=len(direction.trends_keywords), actual_series_count=0)
        return analyze_trend_series(self._series(direction, url), as_of_date=self._now().date(), diagnostic=diagnostic)


def parse_weekly_points(table: Any, keywords: tuple[str, ...], *, contract: TrendsPageContract) -> tuple[WeeklyTrendPoint, ...]:
    """解析趋势组件的无障碍表格，并依据每个表头显式绑定冻结关键词。"""
    rows = list(table.eles("tag:tr"))
    if len(rows) < 2:
        raise PageChangedError(contract.contract_version, ResearchStage.COLLECTING_TRENDS.value, "weekly_rows")
    header_cells = list(rows[0].eles("tag:th")) or list(rows[0].eles("tag:td"))
    headers = tuple(_element_text(cell) for cell in header_cells)
    if len(headers) < 2 or not _is_time_axis_header(headers[0]):
        raise PageChangedError(contract.contract_version, ResearchStage.COLLECTING_TRENDS.value, "time_axis_header")
    bound = _bind_keyword_headers(headers[1:], keywords, contract=contract)
    points: list[WeeklyTrendPoint] = []
    for row in rows[1:]:
        cells = list(row.eles("tag:td"))
        if len(cells) != len(header_cells):
            raise PageChangedError(contract.contract_version, ResearchStage.COLLECTING_TRENDS.value, "row_alignment")
        try:
            week_start = date.fromisoformat(_element_text(cells[0]).strip())
            values = {keyword: _parse_normalized_value(_element_text(cells[index + 1])) for index, keyword in enumerate(bound)}
        except ValueError as error:
            raise PageChangedError(contract.contract_version, ResearchStage.COLLECTING_TRENDS.value, "weekly_value") from error
        points.append(WeeklyTrendPoint(week_start=week_start, values=values))
    return tuple(sorted(points, key=lambda item: item.week_start))


def _bind_keyword_headers(headers: tuple[str, ...], keywords: tuple[str, ...], *, contract: TrendsPageContract) -> tuple[str, ...]:
    """以有限规范化唯一绑定表头；未知、重复和歧义列一律拒绝，绝不按位置回退。"""
    normalized_keywords = {_normalize_header(keyword): keyword for keyword in keywords}
    if len(normalized_keywords) != len(keywords):
        raise PageChangedError(contract.contract_version, ResearchStage.COLLECTING_TRENDS.value, "frozen_keyword_headers")
    bound: list[str] = []
    for header in headers:
        keyword = normalized_keywords.get(_normalize_header(header))
        if keyword is None or keyword in bound:
            raise PageChangedError(contract.contract_version, ResearchStage.COLLECTING_TRENDS.value, "keyword_header_binding")
        bound.append(keyword)
    if not bound:
        raise PageChangedError(contract.contract_version, ResearchStage.COLLECTING_TRENDS.value, "keyword_header_binding")
    return tuple(bound)


def _normalize_header(value: str) -> str:
    """仅移除页面固定装饰文字并合并空白，保持表头与关键词的精确可审计比较。"""
    normalized = " ".join(value.strip().split())
    for decoration in _HEADER_DECORATIONS:
        if normalized.startswith(decoration):
            normalized = normalized[len(decoration):].strip()
    return normalized


def _is_time_axis_header(value: str) -> bool:
    """识别 v2 表格的日期/时间轴首列表头，避免将数据列误当时间。"""
    return _normalize_header(value).lower() in {"日期", "时间", "date", "week"}


def _parse_normalized_value(value: str) -> float:
    """解析 0～100 归一化热度；0 是合法数据，空值和越界值是契约错误。"""
    parsed = float(value.strip())
    if not 0 <= parsed <= 100:
        raise ValueError("normalized_value_out_of_range")
    return parsed


def _element_text(element: Any) -> str:
    """读取单个单元格的可见文本或无障碍标签，不读取整页 DOM。"""
    text = getattr(element, "text", None)
    if isinstance(text, str) and text.strip():
        return text.strip()
    for attribute in ("aria-label", "data-value", "title"):
        try:
            value = element.attr(attribute)
        except Exception:
            continue
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def build_trends_stage_handler(collector: GoogleTrendsCollector) -> StageHandler:
    """创建 collecting_trends（搜索关注度采集）阶段处理器并写入 v2 结果。"""
    def collect_trends(context: DirectionRunContext) -> None:
        """采集单一 v2 结果；降级结果仍进入上下文以保留来源限制。"""
        context.record_trend_result(collector.collect(context.direction, context.require_browser_page(), context.budget))
    return collect_trends
