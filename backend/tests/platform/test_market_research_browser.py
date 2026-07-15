from __future__ import annotations

from pathlib import Path
from typing import Any

from career_os.platform.market_research.browser import DedicatedChromeSession
from career_os.platform.market_research.store import MarketResearchStore


class FakeOptions:
    """记录专用 Chrome 最终收到的启动配置。"""

    def __init__(self) -> None:
        self.browser_path: Path | None = None
        self.local_port: int | None = None
        self.user_data_path: Path | None = None
        self.auto_port_enabled = False
        self.headless_enabled: bool | None = None
        self.arguments: list[str] = []

    def set_browser_path(self, path: Path) -> None:
        self.browser_path = path

    def set_local_port(self, port: int) -> None:
        self.local_port = port

    def set_user_data_path(self, path: Path) -> None:
        self.user_data_path = path

    def auto_port(self, enabled: bool) -> None:
        self.auto_port_enabled = enabled

    def headless(self, enabled: bool) -> None:
        self.headless_enabled = enabled

    def set_argument(self, argument: str) -> None:
        self.arguments.append(argument)


class FakeBrowser:
    """提供 DedicatedChromeSession.open() 需要的最小浏览器公开接口。"""

    process_id = 32100

    def __init__(self, options: FakeOptions) -> None:
        self.options = options
        self.latest_tab = object()
        self.tabs_count = 1

    def get_tabs(self) -> list[object]:
        return [self.latest_tab]

    def close_tabs(self, tabs: list[object]) -> None:
        raise AssertionError(f"unexpected extra tabs: {tabs}")

    def quit(self, **_: Any) -> None:
        return None


class FakeProcess:
    """提供进程身份登记所需的启动时间和可执行文件。"""

    def __init__(self, executable: Path) -> None:
        self.executable = executable

    def create_time(self) -> float:
        return 123.5

    def exe(self) -> str:
        return str(self.executable)


def test_open_uses_persistent_profile_with_manually_allocated_port(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """专用 Chrome 使用当前 demo 的持久化 Profile，而不是 autoPortData。"""
    chrome_path = tmp_path / "Google Chrome"
    chrome_path.write_text("fake", encoding="utf-8")
    chrome_path.chmod(0o755)
    monkeypatch.setattr(
        "career_os.platform.market_research.browser.discover_google_chrome_path",
        lambda _configured: chrome_path,
    )
    options = FakeOptions()
    store = MarketResearchStore(tmp_path / "market_research")
    session = DedicatedChromeSession(
        store,
        options_factory=lambda: options,
        browser_factory=FakeBrowser,
        port_factory=lambda: 45123,
        process_factory=lambda _pid: FakeProcess(chrome_path),
    )

    session.open("research_" + "1" * 32)

    assert options.local_port == 45123
    assert options.user_data_path == store.browser_profile_dir.resolve()
    assert options.auto_port_enabled is False
    assert options.headless_enabled is False
