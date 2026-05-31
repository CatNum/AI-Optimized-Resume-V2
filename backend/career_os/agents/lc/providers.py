from collections.abc import Iterator
from typing import Any

import litellm

from career_os.agents.lc.models import UnsupportedLLMProviderError


def _completion_kwargs(config: dict[str, Any], messages: list[dict[str, str]]) -> dict[str, Any]:
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
