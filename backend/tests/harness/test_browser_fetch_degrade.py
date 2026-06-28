import pytest

from career_os.harness.executor import Harness
from career_os.platform.tool.handlers.browser_fetch import browser_fetch


def test_browser_fetch_degrades_without_api_key(monkeypatch):
    """验证缺少接口密钥时，浏览器抓取降级的处理符合预期。"""
    monkeypatch.delenv("SEARCH_API_KEY", raising=False)
    result = browser_fetch("market", {"query": "云原生趋势"})
    assert result["status"] == "failed"
    assert result["results"] == []


def test_worker_can_complete_despite_browser_fetch_failure(monkeypatch):
    """验证 Worker 可以完成即使浏览器抓取失败。"""
    monkeypatch.delenv("SEARCH_API_KEY", raising=False)
    harness = Harness()
    result = harness.execute_tool("market", "browser_fetch", {"query": "test"})
    assert result["status"] == "failed"
