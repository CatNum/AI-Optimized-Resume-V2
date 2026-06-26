import json
import re
from collections.abc import Iterator
from typing import Any

from career_os.agents.lc.models import LLMRole, model_settings, resolve_llm_config
from career_os.agents.lc.providers import complete_chat, stream_chat


def llm_enabled() -> bool:
    """判断 LLM 是否启用。

    返回值表示当前是否配置了 LLM_API_KEY；没有 key 时系统会走 mock 或确定性兜底。
    """
    return bool(model_settings.llm_api_key)


def invoke_text(
    system: str,
    user: str,
    *,
    role: LLMRole = LLMRole.WORKER,
    model: str | None = None,
    temperature: float | None = None,
) -> str:
    """调用 LLM 并返回文本。

    system（系统提示词）定义模型角色和规则；user（用户提示词）提供任务输入；
    role（模型角色）用于选择 coordinator/worker 等模型配置；
    model（模型名）可覆盖默认模型；temperature（温度）可覆盖默认随机性。
    返回值是模型生成的纯文本。
    """
    config = resolve_llm_config(role=role, model=model, temperature=temperature)
    return complete_chat(
        config,
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )


def extract_json_object(text: str) -> dict[str, Any] | None:
    """从文本中提取 JSON 对象。

    text（文本）是模型原始输出。返回值是解析出的 dict；如果没有 JSON 对象、
    JSON 不合法或顶层不是对象，则返回 None。
    """
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
    """流式调用 LLM 并逐段返回文本。

    system（系统提示词）定义模型行为；user（用户提示词）提供任务；
    role（模型角色）、model（模型名）、temperature（温度）用于解析调用配置。
    返回值是字符串迭代器，每次 yield 一段增量文本。
    """
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
    """调用 LLM 并尝试返回 JSON 对象。

    system（系统提示词）和 user（用户提示词）组成一次请求；
    role（模型角色）、model（模型名）、temperature（温度）控制模型配置。
    返回值是解析后的 dict；如果模型没有输出合法 JSON 对象则返回 None。
    """
    raw = invoke_text(system, user, role=role, model=model, temperature=temperature)
    return extract_json_object(raw)
