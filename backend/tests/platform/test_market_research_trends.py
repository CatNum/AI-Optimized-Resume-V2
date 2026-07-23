from __future__ import annotations

from typing import Any

import pytest

from career_os.config import settings
from career_os.platform.market_research.errors import MarketResearchError
from career_os.platform.market_research.errors import MarketResearchErrorCode
from career_os.platform.market_research.models import DirectionPlan
from career_os.platform.market_research.page_contracts import PageChangedError
from career_os.platform.market_research.runner import ActiveBudget
from career_os.platform.market_research.trends import (
    GoogleTrendsCollector,
    _bind_keyword_headers,
)
from career_os.platform.market_research.page_contracts import TrendsPageContract


# requires_trends_enabled（要求启用趋势采集）在配置关闭时跳过真实采集状态机测试。
requires_trends_enabled = pytest.mark.skipif(
    not settings.market_research.trends_enabled,
    reason="Google Trends collection is disabled by configuration",
)


class FakeClock:
    """同时记录退避等待并推进 ActiveBudget 使用的单调时间。"""

    def __init__(self) -> None:
        self.seconds = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.seconds

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.seconds += seconds


class FakePage:
    """按每次导航设置技术错误或正常无数据页面。"""

    def __init__(self) -> None:
        self.visible_locators: set[str] = set()
        self.url = "https://trends.google.com/trends/explore"

    def ele(self, locator: str, **_: Any) -> object | None:
        return object() if locator in self.visible_locators else None


def _direction() -> DirectionPlan:
    """构造只含一个 Trends 关键词的冻结方向。"""
    return DirectionPlan(
        direction_name="LLM 应用开发",
        direction_key="llm 应用开发",
        boss_keywords=("LLM应用开发",),
        trends_keywords=("LLM应用开发",),
        cities=("北京",),
        experience_basis="related",
        experience_min=3,
        experience_max=5,
    )


def test_keyword_headers_bind_by_name_in_page_column_order() -> None:
    """数据列可任意重排，但每列必须由实际表头唯一绑定冻结关键词。"""
    bound = _bind_keyword_headers(
        ("AI Agent", "LLM Agent"),
        ("LLM Agent", "AI Agent", "Agent 开发"),
        contract=TrendsPageContract(),
    )

    assert bound == ("AI Agent", "LLM Agent")


def test_unknown_keyword_header_is_page_changed_not_positional_fallback() -> None:
    """未知列不能仅因列数正确而按冻结关键词位置猜测映射。"""
    with pytest.raises(PageChangedError) as captured:
        _bind_keyword_headers(
            ("未知术语",),
            ("LLM Agent",),
            contract=TrendsPageContract(),
        )

    assert captured.value.field_name == "keyword_header_binding"


def test_collector_defaults_to_one_rate_limit_retry() -> None:
    """默认首次请求后最多只允许一次 429 退避重试。"""
    assert GoogleTrendsCollector().retry_times == 1


@requires_trends_enabled
def test_collect_backs_off_once_before_recovering() -> None:
    """首次 429 固定等待十秒后只重试一次，第二次恢复即继续。"""
    page = FakePage()
    clock = FakeClock()
    navigation_count = 0
    user_action_count = 0

    def navigate(url: str) -> None:
        nonlocal navigation_count
        navigation_count += 1
        page.url = url
        page.visible_locators = (
            {"text:Too Many Requests"}
            if navigation_count <= 1
            else {"text:没有足够的数据"}
        )

    def wait_for_user(_url: str) -> None:
        nonlocal user_action_count
        user_action_count += 1

    collector = GoogleTrendsCollector(
        retry_times=1,
        retry_delays=(10.0,),
        sleep=clock.sleep,
        jitter_factor=lambda: 1.0,
        navigate_handler=navigate,
        user_action_handler=wait_for_user,
    )
    budget = ActiveBudget(600, monotonic=clock.monotonic)

    result = collector.collect(_direction(), page, budget)

    assert clock.sleeps == [10.0]
    assert budget.elapsed_seconds() == 10.0
    assert result.source_status == "no_data"
    assert user_action_count == 0


@requires_trends_enabled
def test_collect_does_not_sleep_past_remaining_budget() -> None:
    """剩余预算不足以完成下一次退避时直接终止，不执行超预算等待。"""
    page = FakePage()
    clock = FakeClock()

    def navigate(url: str) -> None:
        page.url = url
        page.visible_locators = {"text:请稍后重试"}

    collector = GoogleTrendsCollector(
        retry_times=1,
        retry_delays=(10.0,),
        sleep=clock.sleep,
        jitter_factor=lambda: 1.0,
        navigate_handler=navigate,
    )

    result = collector.collect(_direction(), page, ActiveBudget(9, monotonic=clock.monotonic))

    assert result.source_status == "degraded"
    assert result.diagnostic is not None
    assert result.diagnostic.page_state == "transient_error"
    assert clock.sleeps == [5.0]


@requires_trends_enabled
def test_collect_allows_retry_delay_equal_to_remaining_budget() -> None:
    """剩余预算恰好等于退避时间时允许等待，下一检查点再判定耗尽。"""
    page = FakePage()
    clock = FakeClock()

    def navigate(url: str) -> None:
        page.url = url
        page.visible_locators = {"text:请稍后重试"}

    collector = GoogleTrendsCollector(
        retry_times=1,
        retry_delays=(10.0,),
        sleep=clock.sleep,
        jitter_factor=lambda: 1.0,
        navigate_handler=navigate,
    )

    result = collector.collect(_direction(), page, ActiveBudget(10, monotonic=clock.monotonic))

    assert result.source_status == "degraded"
    assert clock.sleeps == [5.0]


@requires_trends_enabled
def test_collect_does_not_back_off_for_page_contract_error() -> None:
    """只有 429 对应错误使用退避，普通页面契约失败保持原有立即重试。"""
    page = FakePage()
    clock = FakeClock()

    def navigate(url: str) -> None:
        page.url = url
        page.visible_locators = set()

    collector = GoogleTrendsCollector(
        retry_times=1,
        retry_delays=(10.0,),
        sleep=clock.sleep,
        jitter_factor=lambda: 1.0,
        navigate_handler=navigate,
    )

    result = collector.collect(_direction(), page, ActiveBudget(600, monotonic=clock.monotonic))

    assert result.source_status == "degraded"
    assert result.diagnostic is not None
    assert result.diagnostic.page_state == "render_timeout"
    assert sum(clock.sleeps) == 10.0


@requires_trends_enabled
def test_first_rate_limit_uses_first_delay_after_non_rate_limit_error() -> None:
    """普通页面错误不消耗 429 退避档位，首次限流仍等待 10 秒。"""
    page = FakePage()
    clock = FakeClock()
    navigation_count = 0

    def navigate(url: str) -> None:
        nonlocal navigation_count
        navigation_count += 1
        page.url = url
        if navigation_count == 1:
            page.visible_locators = {"text:Too Many Requests"}
        else:
            page.visible_locators = {"text:没有足够的数据"}

    collector = GoogleTrendsCollector(
        retry_times=1,
        retry_delays=(10.0,),
        sleep=clock.sleep,
        jitter_factor=lambda: 1.0,
        navigate_handler=navigate,
    )

    result = collector.collect(
        _direction(),
        page,
        ActiveBudget(600, monotonic=clock.monotonic),
    )

    assert clock.sleeps == [10.0]
    assert result.source_status == "no_data"


@requires_trends_enabled
def test_collect_returns_degraded_result_after_one_rate_limit_retry() -> None:
    """持续 429 在一次退避重试后返回结构化来源降级。"""
    page = FakePage()
    clock = FakeClock()

    def navigate(url: str) -> None:
        page.url = url
        page.visible_locators = {"text:Too Many Requests"}

    collector = GoogleTrendsCollector(
        retry_times=1,
        retry_delays=(10.0,),
        sleep=clock.sleep,
        jitter_factor=lambda: 1.0,
        navigate_handler=navigate,
    )

    result = collector.collect(_direction(), page, ActiveBudget(600, monotonic=clock.monotonic))

    assert result.source_status == "degraded"
    assert result.diagnostic is not None
    assert result.diagnostic.page_state == "rate_limited"
    assert clock.sleeps == [10.0]


@requires_trends_enabled
def test_collect_ignores_regular_login_button_without_user_wait() -> None:
    """匿名 Trends 页的普通登录按钮不调用人工等待回调。"""
    page = FakePage()
    user_action_count = 0

    def navigate(url: str) -> None:
        page.url = url
        page.visible_locators = {"text:登录", "text:没有足够的数据"}

    def wait_for_user(_url: str) -> None:
        nonlocal user_action_count
        user_action_count += 1

    collector = GoogleTrendsCollector(
        retry_times=0,
        navigate_handler=navigate,
        user_action_handler=wait_for_user,
    )

    result = collector.collect(_direction(), page, ActiveBudget(600))

    assert result.source_status == "no_data"
    assert user_action_count == 0
