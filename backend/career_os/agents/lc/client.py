import json
import re
from collections.abc import Iterator
from typing import Any

from career_os.agents.lc.models import LLMRole, model_settings, resolve_llm_config
from career_os.agents.lc.providers import complete_chat, stream_chat


def llm_enabled() -> bool:
    """判断 LLM 是否启用。"""
    return bool(model_settings.llm_api_key)


def invoke_text(
    system: str,
    user: str,
    *,
    role: LLMRole = LLMRole.WORKER,
    model: str | None = None,
    temperature: float | None = None,
) -> str:
    """调用 LLM 并返回文本。"""
    config = resolve_llm_config(role=role, model=model, temperature=temperature)
    return complete_chat(
        config,
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )


def extract_json_object(text: str) -> dict[str, Any] | None:
    """从文本中提取 JSON 对象。"""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        payload = json.loads(match.group())
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def stream_text(
    system: str,
    user: str,
    *,
    role: LLMRole = LLMRole.WORKER,
    model: str | None = None,
    temperature: float | None = None,
) -> Iterator[str]:
    """流式调用 LLM 并逐段返回文本。"""
    config = resolve_llm_config(role=role, model=model, temperature=temperature)
    yield from stream_chat(
        config,
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )


def invoke_json(
    system: str,
    user: str,
    *,
    role: LLMRole = LLMRole.WORKER,
    model: str | None = None,
    temperature: float | None = None,
) -> dict[str, Any] | None:
    """调用 LLM 并尝试返回 JSON 对象。"""
    raw = invoke_text(system, user, role=role, model=model, temperature=temperature)
    return extract_json_object(raw)
