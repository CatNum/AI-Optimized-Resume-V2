from __future__ import annotations

import random
import re
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Callable, Literal

from career_os.config import settings
from career_os.platform.market_research.errors import (
    MarketResearchError,
    MarketResearchErrorCode,
)
from career_os.platform.market_research.models import (
    DirectionPlan,
    ResearchStage,
    TrendObservation,
)
from career_os.platform.market_research.page_contracts import (
    PageChangedError,
    TrendsPageContract,
    validate_external_url,
)

if TYPE_CHECKING:
    from career_os.platform.market_research.runner import (
        ActiveBudget,
        DirectionRunContext,
        StageHandler,
    )


_TIME_RANGES: tuple[Literal["past_12_months", "past_3_months"], ...] = (
    "past_12_months",
    "past_3_months",
)
_PERCENTAGE_PATTERN = re.compile(r"([+-]?\d+(?:[.,]\d+)?)\s*%")
_DISCLAIMER = "Google 搜索关注度不代表岗位需求或招聘趋势。"
_DEFAULT_RETRY_DELAYS = (10.0, 30.0, 60.0)
_RATE_LIMIT_MESSAGE = "trends_rate_limited"


class GoogleTrendsCollector:
    """GoogleTrendsCollector（搜索关注度采集器）只读取页面直接展示的窗口比较卡片。"""

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
        """注入页面契约、重试次数和浏览器回调，便于真实页面与 Fake 页面共享接口。"""
        self.contract = contract or TrendsPageContract()  # 当前版本化 Trends 页面字段契约
        self.retry_times = (
            settings.market_research.trends_retry_times
            if retry_times is None
            else retry_times
        )  # 页面技术失败后的最大重试次数，不包含首次尝试
        if self.retry_times < 0:
            raise ValueError("retry_times must not be negative")
        self.retry_delays = retry_delays or _DEFAULT_RETRY_DELAYS  # 每次技术重试前的基础等待秒数
        if len(self.retry_delays) < self.retry_times or any(
            delay <= 0 for delay in self.retry_delays
        ):
            raise ValueError("retry_delays must cover retry_times with positive values")
        self._sleep = sleep  # 自动退避等待函数；等待时间计入有效预算
        self._jitter_factor = jitter_factor or (lambda: random.uniform(0.8, 1.2))
        self.navigate_handler = navigate_handler  # 经专用浏览器白名单导航的可选回调
        self.user_action_handler = user_action_handler  # 登录或验证时暂停 Runner 的回调
        self._now = now or (lambda: datetime.now(UTC))  # 生成 fetched_at（采集时间）的时钟

    def collect(
        self,
        direction: DirectionPlan,
        page: Any,
        budget: ActiveBudget,
    ) -> tuple[TrendObservation, ...]:
        """按搜索词顺序采集过去一年和最近三个月，所有页面操作计入方向预算。"""
        observations: list[TrendObservation] = []
        for query in direction.trends_keywords:
            for time_range in _TIME_RANGES:
                if budget.remaining_seconds() <= 0:
                    raise MarketResearchError(
                        MarketResearchErrorCode.BUDGET_EXHAUSTED,
                        stage=ResearchStage.COLLECTING_TRENDS.value,
                    )
                observations.append(
                    self._collect_with_retry(query, time_range, page, budget)
                )
        return tuple(observations)

    def _collect_with_retry(
        self,
        query: str,
        time_range: Literal["past_12_months", "past_3_months"],
        page: Any,
        budget: ActiveBudget,
    ) -> TrendObservation:
        """页面技术失败最多重试配置次数；无数据或无比较卡片直接形成正常观察。"""
        last_error: Exception | None = None
        rate_limit_attempt = 0
        for attempt in range(self.retry_times + 1):
            if budget.remaining_seconds() <= 0:
                raise MarketResearchError(
                    MarketResearchErrorCode.BUDGET_EXHAUSTED,
                    stage=ResearchStage.COLLECTING_TRENDS.value,
                )
            try:
                return self._collect_once(query, time_range, page)
            except MarketResearchError as error:
                last_error = error
            except Exception as error:
                last_error = MarketResearchError(
                    MarketResearchErrorCode.EXECUTION_FAILED,
                    stage=ResearchStage.COLLECTING_TRENDS.value,
                    message=type(error).__name__,
                )
            if attempt >= self.retry_times:
                break
            if _is_rate_limit_error(last_error):
                self._sleep_before_retry(rate_limit_attempt, budget)
                rate_limit_attempt += 1
        if isinstance(last_error, MarketResearchError):
            raise last_error
        raise MarketResearchError(
            MarketResearchErrorCode.EXECUTION_FAILED,
            stage=ResearchStage.COLLECTING_TRENDS.value,
        ) from last_error

    def _sleep_before_retry(self, attempt: int, budget: ActiveBudget) -> None:
        """按当前重试序号退避，并在等待前拒绝超出方向有效预算。"""
        factor = float(self._jitter_factor())
        if not 0.8 <= factor <= 1.2:
            raise ValueError("jitter_factor must be between 0.8 and 1.2")
        delay = self.retry_delays[attempt] * factor
        if budget.remaining_seconds() < delay:
            raise MarketResearchError(
                MarketResearchErrorCode.BUDGET_EXHAUSTED,
                stage=ResearchStage.COLLECTING_TRENDS.value,
            )
        self._sleep(delay)

    def _collect_once(
        self,
        query: str,
        time_range: Literal["past_12_months", "past_3_months"],
        page: Any,
    ) -> TrendObservation:
        """读取一次页面比较卡；不下载 CSV、不读取折线点位，也不自行计算趋势。"""
        url = self.contract.build_explore_url(query, time_range)
        safe_url = validate_external_url(url, self.contract.allowed_hosts)
        if self.navigate_handler is None:
            page.get(safe_url)
        else:
            self.navigate_handler(safe_url)

        if self.contract.user_action_required(page):
            if self.user_action_handler is None:
                raise MarketResearchError(
                    MarketResearchErrorCode.EXECUTION_FAILED,
                    stage=ResearchStage.COLLECTING_TRENDS.value,
                    message="user action handler is not configured",
                )
            self.user_action_handler(safe_url)
        validate_external_url(str(getattr(page, "url", safe_url)), self.contract.allowed_hosts)

        if self.contract.technical_retry_required(page):
            raise MarketResearchError(
                MarketResearchErrorCode.EXECUTION_FAILED,
                stage=ResearchStage.COLLECTING_TRENDS.value,
                message=_RATE_LIMIT_MESSAGE,
            )

        if self.contract.read_optional(page, self.contract.no_data_marker) is not None:
            return self._status_observation(query, time_range, safe_url, "no_data")

        stage = ResearchStage.COLLECTING_TRENDS.value
        self.contract.read_required(page, self.contract.geo_filter, stage=stage)
        self.contract.read_required(page, self.contract.time_filter, stage=stage)
        self.contract.read_required(page, self.contract.interest_over_time_region, stage=stage)
        if self.contract.read_optional(page, self.contract.comparison_card) is None:
            return self._status_observation(query, time_range, safe_url, "unavailable")

        direction_element = self.contract.read_required(
            page,
            self.contract.comparison_direction,
            stage=stage,
        )
        percentage_element = self.contract.read_required(
            page,
            self.contract.comparison_percentage,
            stage=stage,
        )
        label_element = self.contract.read_required(
            page,
            self.contract.comparison_label,
            stage=stage,
        )
        percentage_text = _element_text(percentage_element)
        percentage = _parse_percentage(percentage_text, self.contract, stage)
        direction_value = _parse_direction(
            _element_text(direction_element),
            percentage,
            self.contract,
            stage,
        )
        comparison_label = _element_text(label_element).strip()
        if not comparison_label:
            raise PageChangedError(
                self.contract.contract_version,
                stage,
                self.contract.comparison_label.field_name,
            )
        return TrendObservation(
            query=query,
            time_range=time_range,
            direction=direction_value,
            percentage=percentage,
            comparison_label=comparison_label,
            page_url=safe_url,
            fetched_at=self._now(),
            contract_version=self.contract.contract_version,
        )

    def _status_observation(
        self,
        query: str,
        time_range: Literal["past_12_months", "past_3_months"],
        page_url: str,
        direction: Literal["unavailable", "no_data"],
    ) -> TrendObservation:
        """把页面正常无卡片或无数据保存为可继续的显式状态，不伪造百分比。"""
        return TrendObservation(
            query=query,
            time_range=time_range,
            direction=direction,
            percentage=None,
            comparison_label=None,
            page_url=page_url,
            fetched_at=self._now(),
            contract_version=self.contract.contract_version,
        )


def _is_rate_limit_error(error: Exception | None) -> bool:
    """判断采集异常是否来自 Trends 429 对应页面错误。"""
    return (
        isinstance(error, MarketResearchError)
        and error.error_code == MarketResearchErrorCode.EXECUTION_FAILED
        and error.message == _RATE_LIMIT_MESSAGE
    )


def build_trends_stage_handler(collector: GoogleTrendsCollector) -> StageHandler:
    """创建 collecting_trends（搜索关注度采集）阶段处理器并写入方向上下文。"""

    def collect_trends(context: DirectionRunContext) -> None:
        """复用 Runner 唯一标签页采集观察，并生成不含招聘趋势推断的确定性摘要。"""
        observations = collector.collect(
            context.direction,
            context.require_browser_page(),
            context.budget,
        )
        context.record_trend_results(
            observations,
            summarize_trend_directions(observations),
        )

    return collect_trends


def summarize_trend_directions(
    observations: tuple[TrendObservation, ...],
) -> dict[str, Any]:
    """只判断关键词方向一致性和长短期关系，并固定附带搜索关注度边界声明。"""
    usable = [item for item in observations if item.direction in {"up", "down", "flat"}]
    by_window: dict[str, set[str]] = {}
    by_query: dict[str, dict[str, str]] = {}
    for item in usable:
        by_window.setdefault(item.time_range, set()).add(item.direction)
        by_query.setdefault(item.query, {})[item.time_range] = item.direction

    window_states = {
        window: (
            "consistent"
            if len(directions) == 1
            else "divergent"
        )
        for window, directions in by_window.items()
    }
    keyword_direction_state = "insufficient"
    if window_states:
        keyword_direction_state = (
            "divergent"
            if "divergent" in window_states.values()
            else "consistent"
        )

    opposite_queries: list[str] = []
    comparable_queries = 0
    for query, windows in by_query.items():
        long_direction = windows.get("past_12_months")
        short_direction = windows.get("past_3_months")
        if long_direction is None or short_direction is None:
            continue
        comparable_queries += 1
        if {long_direction, short_direction} == {"up", "down"}:
            opposite_queries.append(query)

    if comparable_queries == 0:
        long_short_state = "insufficient"
    elif len(opposite_queries) == comparable_queries:
        long_short_state = "opposite"
    elif opposite_queries:
        long_short_state = "mixed"
    else:
        long_short_state = "aligned"

    return {
        "keyword_direction_state": keyword_direction_state,
        "window_direction_states": window_states,
        "long_short_state": long_short_state,
        "opposite_window_queries": tuple(opposite_queries),
        "disclaimer": _DISCLAIMER,
    }


def _element_text(element: Any) -> str:
    """读取页面元素直接可见文本或无障碍标签，不读取整页 DOM。"""
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


def _parse_percentage(
    value: str,
    contract: TrendsPageContract,
    stage: str,
) -> float:
    """把页面直接显示的百分比文本解析为数值，不基于折线或时间序列重算。"""
    match = _PERCENTAGE_PATTERN.search(value)
    if match is None:
        raise PageChangedError(
            contract.contract_version,
            stage,
            contract.comparison_percentage.field_name,
        )
    return float(match.group(1).replace(",", "."))


def _parse_direction(
    value: str,
    percentage: float,
    contract: TrendsPageContract,
    stage: str,
) -> Literal["up", "down", "flat"]:
    """把页面方向文本映射为上升、下降或持平；未知文案视为契约变化。"""
    normalized = value.strip().lower()
    if any(token in normalized for token in ("上升", "增长", "增加", "up", "rising")):
        return "up"
    if any(token in normalized for token in ("下降", "减少", "降低", "down", "falling")):
        return "down"
    if any(token in normalized for token in ("持平", "不变", "flat", "unchanged", "no change")):
        return "flat"
    if percentage == 0:
        return "flat"
    raise PageChangedError(
        contract.contract_version,
        stage,
        contract.comparison_direction.field_name,
    )
