from __future__ import annotations

import json
import os
import platform
import shutil
import threading
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

import psutil

from career_os.config import settings
from career_os.platform.market_research.errors import (
    MarketResearchError,
    MarketResearchErrorCode,
)
from career_os.platform.market_research.models import ResearchStage
from career_os.platform.market_research.page_contracts import validate_external_url
from career_os.platform.market_research.store import MarketResearchStore

if TYPE_CHECKING:
    from career_os.platform.market_research.runner import (
        DirectionRunContext,
        MarketResearchRunner,
    )


@dataclass(frozen=True)
class ChromeProcessIdentity:
    """ChromeProcessIdentity（专用 Chrome 进程身份）保存安全关闭前必须复核的字段。"""

    pid: int  # DrissionPage 报告的专用 Chrome 浏览器主进程编号
    process_started_at: float  # 操作系统报告的进程启动时间戳，用于防止 PID 重用
    executable_path: str  # 操作系统报告的浏览器主进程可执行文件绝对路径
    configured_chrome_path: str  # 本次启动明确选择的 Google Chrome 可执行文件路径
    demo_data_root: str  # 当前 demo 数据根目录，防止跨 demo 清理
    research_id: str  # 创建并拥有该专用浏览器的市场调研任务编号


class DedicatedChromeSession:
    """DedicatedChromeSession（专用浏览器会话）管理可见、独立 Profile、单标签页 Chrome。"""

    def __init__(
        self,
        store: MarketResearchStore,
        *,
        browser_factory: Callable[[Any], Any] | None = None,
        options_factory: Callable[[], Any] | None = None,
    ) -> None:
        """注入 Store 与可测试工厂；构造对象本身不会启动 Chrome 或创建线程。"""
        self.store = store  # 当前 demo 的市场调研存储器
        self.profile_dir = store.browser_profile_dir.resolve()  # 与日常 Chrome 隔离的登录 Profile
        self.registry_path = store.runtime_dir / "chrome.json"  # 专用 Chrome 进程身份登记文件
        self._browser_factory = browser_factory  # 创建 DrissionPage Chromium 的可选测试工厂
        self._options_factory = options_factory  # 创建 ChromiumOptions 的可选测试工厂
        self._browser: Any | None = None  # 当前线程拥有的唯一 Chromium 实例
        self._page: Any | None = None  # 当前线程复用的唯一可见标签页
        self._research_id: str | None = None  # 当前专用 Chrome 所属调研编号
        self._owner_thread_id: int | None = None  # 创建浏览器的线程编号，限制跨线程使用

    def open(self, research_id: str) -> Any:
        """在调用线程启动可见 Chrome，使用独立 Profile 并返回唯一标签页。"""
        if self._browser is not None:
            raise RuntimeError("dedicated Chrome session is already open")
        self.store.validate_research_id(research_id)
        chrome_path = discover_google_chrome_path(settings.market_research.chrome_path)
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        options = self._build_options(chrome_path)
        browser_factory = self._browser_factory
        if browser_factory is None:
            from DrissionPage import Chromium

            browser_factory = Chromium
        try:
            browser = browser_factory(options)
            pid = browser.process_id
            if not isinstance(pid, int) or pid <= 0:
                raise RuntimeError("DrissionPage did not report the browser PID")
            process = psutil.Process(pid)
            identity = ChromeProcessIdentity(
                pid=pid,
                process_started_at=process.create_time(),
                executable_path=str(Path(process.exe()).resolve()),
                configured_chrome_path=str(chrome_path),
                demo_data_root=str(self.store.root.parent.resolve()),
                research_id=research_id,
            )
            page = self._enforce_single_tab(browser)
            self._write_identity(identity)
        except Exception as error:
            try:
                if "browser" in locals():
                    browser.quit(timeout=3, force=False, del_data=False)
            except Exception:
                pass
            raise MarketResearchError(
                MarketResearchErrorCode.BROWSER_FAILED,
                stage=ResearchStage.STARTING_BROWSER.value,
                message=type(error).__name__,
            ) from error
        self._browser = browser
        self._page = page
        self._research_id = research_id
        self._owner_thread_id = threading.get_ident()
        return page

    @property
    def page(self) -> Any:
        """返回当前唯一标签页，并拒绝在创建 Chrome 之外的线程使用。"""
        self._assert_owner_thread()
        if self._page is None:
            raise RuntimeError("dedicated Chrome session is not open")
        return self._page

    def navigate(self, url: str, allowed_hosts: frozenset[str] | set[str]) -> Any:
        """通过官方 HTTPS 白名单校验后，在唯一标签页内导航且不创建新标签页。"""
        safe_url = validate_external_url(url, allowed_hosts)
        page = self.page
        page.get(safe_url)
        return page

    def wait_for_user_verification(
        self,
        *,
        runner: MarketResearchRunner,
        context: DirectionRunContext,
        contract: Any,
        stage: ResearchStage,
        target_url: str,
    ) -> None:
        """检测登录或验证时暂停预算，无限等待继续或取消，并重新检查目标页面。"""
        self._assert_owner_thread()
        while contract.user_action_required(self.page):
            runner.wait_for_user(context, stage=stage)
            current_url = str(getattr(self.page, "url", "") or "")
            try:
                validate_external_url(current_url, contract.allowed_hosts)
            except ValueError:
                self.navigate(target_url, contract.allowed_hosts)
        validate_external_url(str(getattr(self.page, "url", target_url)), contract.allowed_hosts)

    def close(self) -> None:
        """复核五项进程身份后只关闭已登记专用 Chrome，绝不按进程名称批量终止。"""
        if self._browser is None:
            return
        self._assert_owner_thread()
        identity = self._read_identity()
        if identity is None:
            raise RuntimeError("dedicated Chrome identity is missing; refusing to terminate")
        match = self._registered_process_matches(identity, self._research_id)
        if match == "mismatch":
            raise RuntimeError("dedicated Chrome identity changed; refusing to terminate")
        try:
            if match == "matched":
                self._browser.quit(timeout=5, force=False, del_data=False)
                if (
                    self._registered_process_matches(identity, self._research_id)
                    == "matched"
                ):
                    self.terminate_registered_process(
                        research_id=self._research_id,
                        timeout_seconds=5.0,
                        force=True,
                    )
        finally:
            if match in {"matched", "missing"}:
                self.registry_path.unlink(missing_ok=True)
                self._browser = None
                self._page = None
                self._research_id = None
                self._owner_thread_id = None

    def restart(self) -> Any:
        """在同一 Runner 线程安全关闭并重开当前调研的专用 Chrome，返回新的唯一标签页。"""
        self._assert_owner_thread()
        research_id = self._research_id
        if research_id is None:
            raise RuntimeError("dedicated Chrome session is not open")
        self.close()
        return self.open(research_id)

    def terminate_registered_process(
        self,
        *,
        research_id: str | None = None,
        timeout_seconds: float = 10.0,
        force: bool = False,
    ) -> bool:
        """供清理流程按登记身份终止专用进程；force 也只作用于身份仍匹配的同一 PID。"""
        identity = self._read_identity()
        if identity is None:
            return False
        match = self._registered_process_matches(identity, research_id)
        if match == "missing":
            self.registry_path.unlink(missing_ok=True)
            return False
        if match != "matched":
            raise RuntimeError("registered Chrome identity does not match; refusing cleanup")
        process = psutil.Process(identity.pid)
        process.terminate()
        try:
            process.wait(timeout=timeout_seconds)
        except psutil.TimeoutExpired:
            if not force:
                return False
            if self._registered_process_matches(identity, research_id) != "matched":
                raise RuntimeError("Chrome identity changed before forced cleanup")
            process.kill()
            process.wait(timeout=timeout_seconds)
        self.registry_path.unlink(missing_ok=True)
        return True

    def _build_options(self, chrome_path: Path) -> Any:
        """构造始终可见、独立 Profile、自动本地调试端口的 ChromiumOptions。"""
        options_factory = self._options_factory
        if options_factory is None:
            from DrissionPage import ChromiumOptions

            options_factory = lambda: ChromiumOptions(read_file=False)
        options = options_factory()
        options.set_browser_path(chrome_path)
        options.set_user_data_path(self.profile_dir)
        options.auto_port(True)
        options.headless(False)
        options.set_argument("--no-first-run")
        options.set_argument("--no-default-browser-check")
        options.set_argument("--disable-session-crashed-bubble")
        return options

    @staticmethod
    def _enforce_single_tab(browser: Any) -> Any:
        """复用已有最新标签页并关闭 Profile 恢复出的额外标签页，不调用 new_tab。"""
        tabs = list(browser.get_tabs())
        if not tabs:
            raise RuntimeError("dedicated Chrome did not create an initial tab")
        page = browser.latest_tab
        page_id = getattr(page, "tab_id", None)
        extras = [tab for tab in tabs if getattr(tab, "tab_id", None) != page_id]
        if extras:
            browser.close_tabs(extras)
        if browser.tabs_count != 1:
            raise RuntimeError("dedicated Chrome must contain exactly one tab")
        return page

    def _write_identity(self, identity: ChromeProcessIdentity) -> None:
        """用同目录临时文件原子登记专用 Chrome 进程身份。"""
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.registry_path.with_name(
            f".{self.registry_path.name}.{uuid.uuid4().hex}.tmp"
        )
        try:
            with temp.open("w", encoding="utf-8") as file:
                json.dump(asdict(identity), file, ensure_ascii=False, indent=2, sort_keys=True)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temp, self.registry_path)
            directory_fd = os.open(self.registry_path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            temp.unlink(missing_ok=True)

    def _read_identity(self) -> ChromeProcessIdentity | None:
        """读取 chrome.json 并校验字段结构，不接受任意 PID 或路径参数。"""
        if not self.registry_path.exists():
            return None
        try:
            with self.registry_path.open(encoding="utf-8") as file:
                payload = json.load(file)
            return ChromeProcessIdentity(**payload)
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise RuntimeError("invalid dedicated Chrome identity file") from error

    def _registered_process_matches(
        self,
        identity: ChromeProcessIdentity,
        research_id: str | None,
    ) -> str:
        """复核 PID、启动时间、可执行路径、demo 根和 research_id，返回 matched/missing/mismatch。"""
        if identity.demo_data_root != str(self.store.root.parent.resolve()):
            return "mismatch"
        if research_id is not None and identity.research_id != research_id:
            return "mismatch"
        if not psutil.pid_exists(identity.pid):
            return "missing"
        try:
            process = psutil.Process(identity.pid)
            if abs(process.create_time() - identity.process_started_at) > 0.001:
                return "mismatch"
            if str(Path(process.exe()).resolve()) != identity.executable_path:
                return "mismatch"
        except (psutil.Error, OSError):
            return "missing"
        return "matched"

    def _assert_owner_thread(self) -> None:
        """保证 DrissionPage 的创建、页面操作和关闭都发生在同一 Runner 线程。"""
        if self._owner_thread_id is not None and self._owner_thread_id != threading.get_ident():
            raise RuntimeError("dedicated Chrome cannot be used from another thread")


def discover_google_chrome_path(configured_path: str | None = None) -> Path:
    """优先校验配置覆盖路径，再按当前系统查找常见 Google Chrome 可执行文件。"""
    if configured_path:
        override = Path(configured_path).expanduser().resolve()
        if not _is_executable_file(override):
            raise MarketResearchError(
                MarketResearchErrorCode.BROWSER_FAILED,
                stage=ResearchStage.STARTING_BROWSER.value,
                message="configured Chrome path is not executable",
            )
        return override

    candidates: list[Path] = []
    system = platform.system().lower()
    if system == "darwin":
        candidates.extend(
            [
                Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
                Path.home()
                / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            ]
        )
    elif system == "windows":
        for env_name in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            base = os.getenv(env_name)
            if base:
                candidates.append(Path(base) / "Google/Chrome/Application/chrome.exe")
    else:
        candidates.extend(
            Path(path)
            for path in (
                "/usr/bin/google-chrome",
                "/usr/bin/google-chrome-stable",
                "/opt/google/chrome/google-chrome",
            )
        )
        for command in ("google-chrome", "google-chrome-stable"):
            discovered = shutil.which(command)
            if discovered:
                candidates.append(Path(discovered))

    for candidate in candidates:
        resolved = candidate.expanduser().resolve()
        if _is_executable_file(resolved):
            return resolved
    raise MarketResearchError(
        MarketResearchErrorCode.BROWSER_FAILED,
        stage=ResearchStage.STARTING_BROWSER.value,
        message="Google Chrome executable was not found",
    )


def _is_executable_file(path: Path) -> bool:
    """判断路径是普通文件且当前用户拥有执行权限。"""
    return path.is_file() and os.access(path, os.X_OK)
