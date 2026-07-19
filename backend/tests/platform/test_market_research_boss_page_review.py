from __future__ import annotations

from types import SimpleNamespace

import pytest

from career_os.platform.market_research.boss import BossJobCollector
from career_os.platform.market_research.page_contracts import PageChangedError
from career_os.platform.market_research.runner import ActiveBudget
from career_os.platform.market_research.store import MarketResearchStore


class EmptyBossPage:
    """EmptyBossPage（空 BOSS 页面）模拟已加载但没有岗位列表的受限页面。"""

    url = "https://www.zhipin.com/web/geek/job"

    def get(self, url: str) -> None:
        """记录当前已导航到 BOSS 官方列表页。"""
        self.url = url

    def ele(self, *_: object, **__: object) -> None:
        """所有页面契约定位均为空，触发 job_list（岗位列表）结构检查失败。"""
        return None


class _ListWaiter:
    """模拟 DrissionPage 的显式元素等待，命中后才让 SPA 职位列表可读。"""

    def __init__(self, page: DelayedBossListPage) -> None:
        self.page = page
        self.locators: list[str] = []

    def ele_displayed(self, locator: str, **_: object) -> bool:
        self.locators.append(locator)
        self.page.rendered = True
        return True


class DelayedBossListPage:
    """模拟 BOSS SPA：导航完成后，职位列表要等一次渲染等待才出现。"""

    url = "https://www.zhipin.com/web/geek/jobs"

    def __init__(self) -> None:
        self.rendered = False
        self.wait = _ListWaiter(self)

    def get(self, url: str) -> None:
        self.url = url

    def ele(self, locator: str, **_: object) -> object | None:
        if not self.rendered:
            return None
        if locator in {"css:.job-list-container", "css:.job-list-container .card-area"}:
            return object()
        return None


def test_missing_boss_list_pauses_for_page_review_before_raising(tmp_path) -> None:
    """未识别的 BOSS 页面必须先保留给用户检查，再传播 page_changed。"""
    reviewed_fields: list[str] = []
    collector = BossJobCollector(
        MarketResearchStore(tmp_path / "market_research"),
        page_review_handler=lambda error: reviewed_fields.append(error.field_name),
        sleep=lambda _: None,
        uniform=lambda _minimum, _maximum: 0.0,
    )
    context = SimpleNamespace(budget=ActiveBudget(600), data={})

    with pytest.raises(PageChangedError):
        collector._load_list_with_recovery(
            EmptyBossPage(),
            "https://www.zhipin.com/web/geek/job?query=LLM",
            context,
        )

    assert reviewed_fields == ["job_list"]


def test_boss_list_waits_for_spa_render_before_reading_required_fields(tmp_path) -> None:
    """列表加载必须等待 BOSS SPA 渲染，不能在初始加载壳上误报 page_changed。"""
    page = DelayedBossListPage()
    collector = BossJobCollector(
        MarketResearchStore(tmp_path / "market_research"),
        sleep=lambda _: None,
        uniform=lambda _minimum, _maximum: 0.0,
    )
    context = SimpleNamespace(budget=ActiveBudget(600), data={})

    loaded = collector._load_list_with_recovery(
        page,
        "https://www.zhipin.com/web/geek/jobs?query=LLM",
        context,
    )

    assert loaded is page
    assert page.wait.locators == ["css:.job-list-container"]
