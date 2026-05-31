import os
from dataclasses import dataclass
from typing import Any


@dataclass
class BrowserFetchResult:
    status: str
    results: list[dict[str, Any]]
    message: str = ""


def browser_fetch(actor: str, args: dict[str, Any]) -> dict[str, Any]:
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
