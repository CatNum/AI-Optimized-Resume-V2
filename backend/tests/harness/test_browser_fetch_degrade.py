import pytest

from career_os.harness.executor import Harness
from career_os.platform.tool.handlers.browser_fetch import browser_fetch


def test_browser_fetch_degrades_without_api_key(monkeypatch):
    """验证 browser fetch degrades without api key 场景。"""
    monkeypatch.delenv("SEARCH_API_KEY", raising=False)
    result = browser_fetch("market", {"query": "云原生趋势"})
    assert result["status"] == "failed"
    assert result["results"] == []


def test_worker_can_complete_despite_browser_fetch_failure(monkeypatch):
    """验证 worker can complete despite browser fetch failure 场景。"""
    monkeypatch.delenv("SEARCH_API_KEY", raising=False)
    harness = Harness()
    result = harness.execute_tool("market", "browser_fetch", {"query": "test"})
    assert result["status"] == "failed"
