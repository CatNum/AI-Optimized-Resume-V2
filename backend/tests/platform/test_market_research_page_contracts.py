from __future__ import annotations

from typing import Any

import pytest

from career_os.platform.market_research.page_contracts import TrendsPageContract


class FakePage:
    """按定位器返回页面上可见的测试标记。"""

    def __init__(self, visible_locators: set[str]) -> None:
        self.visible_locators = visible_locators

    def ele(self, locator: str, **_: Any) -> object | None:
        return object() if locator in self.visible_locators else None


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
