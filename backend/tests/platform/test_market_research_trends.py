from __future__ import annotations

from typing import Any

import pytest

from career_os.platform.market_research.errors import MarketResearchError
from career_os.platform.market_research.errors import MarketResearchErrorCode
from career_os.platform.market_research.models import DirectionPlan
from career_os.platform.market_research.page_contracts import PageChangedError
from career_os.platform.market_research.runner import ActiveBudget
from career_os.platform.market_research.trends import GoogleTrendsCollector


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


def test_collector_defaults_to_three_rate_limit_retries() -> None:
    """默认首次请求后允许三次退避，完整覆盖 10、30、60 秒序列。"""
    assert GoogleTrendsCollector().retry_times == 3


def test_collect_backs_off_10_30_60_seconds_before_recovering() -> None:
    """前三次 429 页面错误后按固定基础间隔退避，第四次恢复并继续。"""
    page = FakePage()
    clock = FakeClock()
    navigation_count = 0
    user_action_count = 0

    def navigate(url: str) -> None:
        nonlocal navigation_count
        navigation_count += 1
        page.url = url
        page.visible_locators = (
            {"text:糟糕！出了点问题"}
            if navigation_count <= 3
            else {"text:没有足够的数据"}
        )

    def wait_for_user(_url: str) -> None:
        nonlocal user_action_count
        user_action_count += 1

    collector = GoogleTrendsCollector(
        retry_times=3,
        retry_delays=(10.0, 30.0, 60.0),
        sleep=clock.sleep,
        jitter_factor=lambda: 1.0,
        navigate_handler=navigate,
        user_action_handler=wait_for_user,
    )
    budget = ActiveBudget(600, monotonic=clock.monotonic)

    observations = collector.collect(_direction(), page, budget)

    assert clock.sleeps == [10.0, 30.0, 60.0]
    assert budget.elapsed_seconds() == 100.0
    assert [item.direction for item in observations] == ["no_data", "no_data"]
    assert user_action_count == 0


def test_collect_does_not_sleep_past_remaining_budget() -> None:
    """剩余预算不足以完成下一次退避时直接终止，不执行超预算等待。"""
    page = FakePage()
    clock = FakeClock()

    def navigate(url: str) -> None:
        page.url = url
        page.visible_locators = {"text:请稍后重试"}

    collector = GoogleTrendsCollector(
        retry_times=3,
        retry_delays=(10.0, 30.0, 60.0),
        sleep=clock.sleep,
        jitter_factor=lambda: 1.0,
        navigate_handler=navigate,
    )

    with pytest.raises(MarketResearchError) as captured:
        collector.collect(
            _direction(),
            page,
            ActiveBudget(9, monotonic=clock.monotonic),
        )

    assert captured.value.error_code == MarketResearchErrorCode.BUDGET_EXHAUSTED
    assert clock.sleeps == []


def test_collect_allows_retry_delay_equal_to_remaining_budget() -> None:
    """剩余预算恰好等于退避时间时允许等待，下一检查点再判定耗尽。"""
    page = FakePage()
    clock = FakeClock()

    def navigate(url: str) -> None:
        page.url = url
        page.visible_locators = {"text:请稍后重试"}

    collector = GoogleTrendsCollector(
        retry_times=3,
        retry_delays=(10.0, 30.0, 60.0),
        sleep=clock.sleep,
        jitter_factor=lambda: 1.0,
        navigate_handler=navigate,
    )

    with pytest.raises(MarketResearchError) as captured:
        collector.collect(
            _direction(),
            page,
            ActiveBudget(10, monotonic=clock.monotonic),
        )

    assert captured.value.error_code == MarketResearchErrorCode.BUDGET_EXHAUSTED
    assert clock.sleeps == [10.0]


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

    with pytest.raises(PageChangedError):
        collector.collect(_direction(), page, ActiveBudget(600, monotonic=clock.monotonic))

    assert clock.sleeps == []


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
            page.visible_locators = set()
        elif navigation_count == 2:
            page.visible_locators = {"text:请稍后重试"}
        else:
            page.visible_locators = {"text:没有足够的数据"}

    collector = GoogleTrendsCollector(
        retry_times=3,
        retry_delays=(10.0, 30.0, 60.0),
        sleep=clock.sleep,
        jitter_factor=lambda: 1.0,
        navigate_handler=navigate,
    )

    observations = collector.collect(
        _direction(),
        page,
        ActiveBudget(600, monotonic=clock.monotonic),
    )

    assert clock.sleeps == [10.0]
    assert [item.direction for item in observations] == ["no_data", "no_data"]


def test_collect_returns_structured_error_after_three_rate_limit_retries() -> None:
    """持续 429 页面错误在三次退避后返回稳定的 execution_failed。"""
    page = FakePage()
    clock = FakeClock()

    def navigate(url: str) -> None:
        page.url = url
        page.visible_locators = {"text:Oops! Something went wrong"}

    collector = GoogleTrendsCollector(
        retry_times=3,
        retry_delays=(10.0, 30.0, 60.0),
        sleep=clock.sleep,
        jitter_factor=lambda: 1.0,
        navigate_handler=navigate,
    )

    with pytest.raises(MarketResearchError) as captured:
        collector.collect(_direction(), page, ActiveBudget(600, monotonic=clock.monotonic))

    assert captured.value.error_code == MarketResearchErrorCode.EXECUTION_FAILED
    assert captured.value.message == "trends_rate_limited"
    assert clock.sleeps == [10.0, 30.0, 60.0]


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

    observations = collector.collect(_direction(), page, ActiveBudget(600))

    assert [item.direction for item in observations] == ["no_data", "no_data"]
    assert user_action_count == 0
