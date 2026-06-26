import json
from typing import Any, AsyncIterator


def format_sse(event: str, data: dict[str, Any]) -> str:
    """format_sse（format sse）的函数说明。

    event（参数）、data（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def stream_tokens(text: str, chunk_size: int = 8) -> AsyncIterator[str]:
    """stream_tokens（stream tokens）的异步函数说明。

    text（参数）、chunk_size（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    for i in range(0, len(text), chunk_size):
        yield format_sse("token", {"delta": text[i : i + chunk_size]})
