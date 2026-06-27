import json
from typing import Any, AsyncIterator


def format_sse(event: str, data: dict[str, Any]) -> str:
    """格式化sse。"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def stream_tokens(text: str, chunk_size: int = 8) -> AsyncIterator[str]:
    """流式返回tokens。"""
    for i in range(0, len(text), chunk_size):
        yield format_sse("token", {"delta": text[i : i + chunk_size]})
