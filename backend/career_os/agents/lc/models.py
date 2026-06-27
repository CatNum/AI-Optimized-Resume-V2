from enum import Enum
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMRole(str, Enum):
    """
    LLMRole（模型角色）区分不同调用场景。
    """

    COORDINATOR = "coordinator"  # Coordinator 角色
    WORKER = "worker"  # Worker 角色
    GATE_INTENT = "gate_intent"  # 门禁意图角色


PROVIDER_PRESETS: dict[str, dict[str, Any]] = {
    "deepseek": {
        "api_base": "https://api.deepseek.com",
        "coordinator_model": "deepseek/deepseek-chat",
        "worker_model": "deepseek/deepseek-chat",
    },
    "openai": {
        "api_base": None,
        "coordinator_model": "gpt-4o-mini",
        "worker_model": "gpt-4o-mini",
    },
    "openai_compatible": {
        "api_base": None,
        "coordinator_model": "gpt-4o-mini",
        "worker_model": "gpt-4o-mini",
    },
}


class ModelSettings(BaseSettings):
    """
    ModelSettings（模型设置）从环境变量读取 LLM 配置。
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")  # 模型配置

    llm_provider: str = Field(default="deepseek", validation_alias="LLM_PROVIDER")  # LLM 服务商
    llm_api_key: str | None = Field(default=None, validation_alias="LLM_API_KEY")  # LLM API key
    llm_base_url: str | None = Field(default=None, validation_alias="LLM_BASE_URL")  # LLM base url
    coordinator_model: str | None = Field(default=None, validation_alias="COORDINATOR_MODEL")  # Coordinator 模型
    worker_model: str | None = Field(default=None, validation_alias="WORKER_MODEL")  # Worker 模型
    llm_temperature: float = Field(default=0.2, validation_alias="LLM_TEMPERATURE")  # LLM 温度


model_settings = ModelSettings()


class UnsupportedLLMProviderError(ValueError):
    """
    UnsupportedLLMProviderError（不支持的模型提供商错误）表示模型配置或调用失败。
    """

    pass


def to_litellm_model(provider: str, model: str) -> str:
    """转换为 LiteLLM 识别的模型名。"""
    if "/" in model:
        return model
    if provider == "deepseek":
        return f"deepseek/{model}"
    if provider in {"openai", "openai_compatible"}:
        return model if model.startswith(("gpt-", "o1", "o3", "o4")) else f"openai/{model}"
    return model


def resolve_llm_config(
    *,
    role: LLMRole = LLMRole.WORKER,
    model: str | None = None,
    temperature: float | None = None,
) -> dict[str, Any]:
    """解析当前 LLM 调用配置。"""
    provider = (model_settings.llm_provider or "deepseek").lower()
    preset = PROVIDER_PRESETS.get(provider)
    if preset is None:
        raise UnsupportedLLMProviderError(f"Unsupported LLM provider: {provider}")

    if model:
        role_model = model
    elif role == LLMRole.COORDINATOR:
        role_model = model_settings.coordinator_model or preset["coordinator_model"]
    else:
        role_model = model_settings.worker_model or preset["worker_model"]

    return {
        "provider": provider,
        "litellm_model": to_litellm_model(provider, role_model),
        "api_key": model_settings.llm_api_key,
        "api_base": model_settings.llm_base_url or preset.get("api_base"),
        "temperature": temperature if temperature is not None else model_settings.llm_temperature,
    }
