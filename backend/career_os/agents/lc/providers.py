from typing import Any

import litellm

from career_os.agents.lc.models import UnsupportedLLMProviderError


def complete_chat(config: dict[str, Any], messages: list[dict[str, str]]) -> str:
    if not config.get("api_key"):
        raise RuntimeError("LLM_API_KEY is not configured")

    kwargs: dict[str, Any] = {
        "model": config["litellm_model"],
        "messages": messages,
        "api_key": config["api_key"],
        "temperature": config["temperature"],
    }
    if config.get("api_base"):
        kwargs["api_base"] = config["api_base"]

    try:
        response = litellm.completion(**kwargs)
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
