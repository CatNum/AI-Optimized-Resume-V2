from collections.abc import Iterator
from typing import Any

import litellm

from career_os.agents.lc.models import UnsupportedLLMProviderError


def _completion_kwargs(config: dict[str, Any], messages: list[dict[str, str]]) -> dict[str, Any]:
    """组装 LiteLLM completion 参数。

    config（模型配置）包含 litellm_model、api_key、temperature、api_base；
    messages（消息列表）是 system/user/assistant 消息。返回值是可直接传给
    litellm.completion 的关键字参数。
    """
    kwargs: dict[str, Any] = {
        "model": config["litellm_model"],
        "messages": messages,
        "api_key": config["api_key"],
        "temperature": config["temperature"],
    }
    if config.get("api_base"):
        kwargs["api_base"] = config["api_base"]
    return kwargs


def complete_chat(config: dict[str, Any], messages: list[dict[str, str]]) -> str:
    """执行一次非流式聊天补全。

    config（模型配置）由 resolve_llm_config 生成；
    messages（消息列表）是发送给模型的上下文。返回值是模型回复文本；
    如果 provider 或网络调用失败，会包装成 UnsupportedLLMProviderError。
    """
    if not config.get("api_key"):
        raise RuntimeError("LLM_API_KEY is not configured")

    try:
        response = litellm.completion(**_completion_kwargs(config, messages))
    except Exception as exc:
        raise UnsupportedLLMProviderError(
            f"LiteLLM completion failed for {config.get('litellm_model')}: {exc}"
        ) from exc

    content = response.choices[0].message.content
    if content is None:
        return ""
    if isinstance(content, list):
        return "".join(str(part) for part in content)
    return str(content)


def stream_chat(
    config: dict[str, Any], messages: list[dict[str, str]]
) -> Iterator[str]:
    """执行一次流式聊天补全。

    config（模型配置）指定模型、key、base_url 和温度；
    messages（消息列表）提供本次对话上下文。返回值是增量文本迭代器，
    每个 yield 对应 LiteLLM 返回的一段 delta。
    """
    if not config.get("api_key"):
        raise RuntimeError("LLM_API_KEY is not configured")

    try:
        response = litellm.completion(
            **_completion_kwargs(config, messages),
            stream=True,
        )
    except Exception as exc:
        raise UnsupportedLLMProviderError(
            f"LiteLLM stream failed for {config.get('litellm_model')}: {exc}"
        ) from exc

    for chunk in response:
        delta = chunk.choices[0].delta.content
        if delta:
            yield str(delta)
