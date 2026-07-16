from __future__ import annotations

from typing import Any

import pytest

from career_os.platform.market_research.page_contracts import TrendsPageContract


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
