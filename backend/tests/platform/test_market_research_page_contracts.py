from __future__ import annotations

from typing import Any

import pytest

from career_os.platform.market_research.boss import _is_explicitly_non_full_time
from career_os.platform.market_research.page_contracts import BossPageContract, TrendsPageContract


class FakeElementStates:
    """FakeElementStates（元素状态）提供是否实际显示的测试值。"""

    def __init__(self, is_displayed: bool) -> None:
        self.is_displayed = is_displayed


class FakeElement:
    """FakeElement（页面元素）模拟 DrissionPage 的可见性状态。"""

    def __init__(self, *, is_displayed: bool = True) -> None:
        self.states = FakeElementStates(is_displayed)


class FakePage:
    """按定位器返回页面测试标记，并区分可见与隐藏元素。"""

    def __init__(
        self,
        visible_locators: set[str],
        *,
        hidden_locators: set[str] | None = None,
    ) -> None:
        self.visible_locators = visible_locators
        self.hidden_locators = hidden_locators or set()

    def ele(self, locator: str, **_: Any) -> object | None:
        if locator in self.visible_locators:
            return FakeElement(is_displayed=True)
        if locator in self.hidden_locators:
            return FakeElement(is_displayed=False)
        return None


@pytest.mark.parametrize(
    "login_marker",
    ["text:没有更多职位，尝试登录查看全部职位"],
)
def test_boss_login_limited_result_requires_user_action(login_marker: str) -> None:
    """未登录受限空页必须暂停扫码登录，不能继续误报岗位列表结构变化。"""
    assert BossPageContract().user_action_required(FakePage({login_marker})) is True


@pytest.mark.parametrize("login_text", ["text:立即登录", "text:登录/注册"])
def test_boss_regular_login_entry_does_not_mask_an_already_logged_in_list(login_text: str) -> None:
    """页面常驻的登录入口不是未登录证据，不能阻塞职位列表采集。"""
    assert BossPageContract().user_action_required(FakePage({login_text})) is False


def test_hidden_boss_login_dialog_does_not_pause_an_already_logged_in_page() -> None:
    """BOSS SPA 常驻但隐藏的登录弹窗不能被当作用户必须操作的证据。"""
    assert BossPageContract().user_action_required(
        FakePage(set(), hidden_locators={"css:.login-dialog"})
    ) is False


def test_boss_contract_builds_current_plural_jobs_search_url() -> None:
    """BOSS 当前 /jobs 页面使用已验证的列表与职位卡片容器。"""
    contract = BossPageContract()
    url = contract.build_search_url("LLM Agent 应用开发", "101010100")

    assert url.startswith("https://www.zhipin.com/web/geek/jobs?")
    assert "/web/geek/job?" not in url
    assert contract.job_list.locators[0] == "css:.job-list-container"
    assert contract.job_card.locators[0] == "css:.job-list-container .card-area"
    assert contract.job_card_link.locators[0] == "css:a.job-name"
    assert contract.detail_title.locators[0] == "css:.job-detail-container .job-detail-info .job-name"
    assert contract.detail_salary.locators[0] == "css:.job-detail-container .job-detail-info .job-salary"
    assert contract.detail_city.locators[0] == (
        "xpath://div[contains(@class,'job-header-info')]"
        "//ul[contains(@class,'tag-list')]/li[1]"
    )
    assert contract.company_name.locators[0] == "css:.job-list-container .card-area .job-card-wrap.active .boss-name"
    assert contract.job_description.locators[0] == "css:.job-detail-container .job-detail-body .desc"


@pytest.mark.parametrize(
    ("employment_text", "expected"),
    [(None, False), ("全职", False), ("兼职", True)],
)
def test_boss_list_url_enforces_full_time_when_detail_panel_omits_employment_text(
    employment_text: str | None,
    expected: bool,
) -> None:
    """jobType=1901 已限制全职；右侧详情缺少标签不能触发页面结构变化。"""
    assert _is_explicitly_non_full_time(employment_text) is expected


@pytest.mark.parametrize("login_text", ["text:登录", "text:Sign in"])
def test_regular_trends_login_button_does_not_require_user_action(login_text: str) -> None:
    """匿名可用页面顶部的普通登录入口不会暂停调研。"""
    contract = TrendsPageContract()

    assert contract.user_action_required(FakePage({login_text})) is False


@pytest.mark.parametrize(
    "verification_text",
    ["text:验证您的身份", "text:异常流量", "text:Verify it's you"],
)
def test_trends_verification_challenge_requires_user_action(
    verification_text: str,
) -> None:
    """真正的身份验证或异常流量页面仍暂停并等待用户。"""
    contract = TrendsPageContract()

    assert contract.user_action_required(FakePage({verification_text})) is True


def test_hidden_invisible_recaptcha_does_not_require_user_action() -> None:
    """正常 Trends 页面常驻的隐藏 reCAPTCHA iframe 不会暂停调研。"""
    contract = TrendsPageContract()
    recaptcha_iframe = "css:iframe[src*='recaptcha']"

    page = FakePage(set(), hidden_locators={recaptcha_iframe})

    assert contract.user_action_required(page) is False


def test_visible_recaptcha_requires_user_action() -> None:
    """真正显示出来的 reCAPTCHA 仍暂停调研并等待用户处理。"""
    contract = TrendsPageContract()
    recaptcha_iframe = "css:iframe[src*='recaptcha']"

    assert contract.user_action_required(FakePage({recaptcha_iframe})) is True


@pytest.mark.parametrize(
    "error_text",
    [
        "text:糟糕！出了点问题",
        "text:请稍后重试",
        "text:Oops! Something went wrong",
        "text:Please try again later",
    ],
)
def test_trends_transient_widget_error_requires_technical_retry(
    error_text: str,
) -> None:
    """429 对应页面错误进入自动技术重试，不进入人工验证。"""
    contract = TrendsPageContract()
    page = FakePage({error_text})

    assert contract.technical_retry_required(page) is True
    assert contract.user_action_required(page) is False


def test_v2_contract_builds_one_chinese_twelve_month_query() -> None:
    """v2 查询固定中国、简体中文和过去十二个月，多个关键词共用同一页。"""
    contract = TrendsPageContract()

    url = contract.build_explore_url("LLM Agent,AI Agent", "past_12_months")

    assert contract.contract_version == "google_trends_web_v2"
    assert "q=LLM+Agent%2CAI+Agent" in url
    assert "date=today+12-m" in url
    assert "geo=CN" in url
    assert "hl=zh-CN" in url
    assert contract.interest_over_time_table.field_name == "interest_over_time_table"


def test_generic_error_is_not_a_rate_limit() -> None:
    """通用页面错误只走短重试，不能被误认为明确 429 限流。"""
    contract = TrendsPageContract()

    assert contract.rate_limited(FakePage({"text:Too Many Requests"})) is True
    assert contract.rate_limited(FakePage({"text:糟糕！出了点问题"})) is False
