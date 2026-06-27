import os
from dataclasses import dataclass
from typing import Any


@dataclass
class BrowserFetchResult:
    """
    BrowserFetchResult（浏览器抓取结果）承载搜索抓取工具的状态和结果列表。
    """

    status: str  # 状态
    results: list[dict[str, Any]]  # 结果列表
    message: str = ""  # 错误消息


def browser_fetch(actor: str, args: dict[str, Any]) -> dict[str, Any]:
    """抓取浏览器搜索结果。"""
    if not os.getenv("SEARCH_API_KEY"):
        return {
            "status": "failed",
            "results": [],
            "message": "SEARCH_API_KEY not configured; degraded",
        }
    query = args.get("query", "")
    return {
        "status": "ok",
        "results": [{"url": "https://example.com", "snippet": f"Result for {query}"}],
    }
