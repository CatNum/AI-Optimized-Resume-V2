from enum import Enum
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMRole(str, Enum):
    """LLMRole（模型角色）区分不同调用场景。

    COORDINATOR（协调器）用于主控分析与合成；
    WORKER（工作者）用于各 Worker 执行任务；
    GATE_INTENT（门禁意图）用于判断用户是否确认继续。
    """
    COORDINATOR = "coordinator"
    WORKER = "worker"
    GATE_INTENT = "gate_intent"


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
    """ModelSettings（模型设置）从环境变量读取 LLM 配置。

    llm_provider（模型提供商）选择 deepseek/openai/openai_compatible；
    llm_api_key（模型密钥）决定是否启用真实 LLM；
    llm_base_url（模型基础地址）支持兼容接口；
    coordinator_model（协调器模型）覆盖 Coordinator 默认模型；
    worker_model（工作者模型）覆盖 Worker 默认模型；
    llm_temperature（模型温度）控制输出随机性。
    """
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm_provider: str = Field(default="deepseek", validation_alias="LLM_PROVIDER")
    llm_api_key: str | None = Field(default=None, validation_alias="LLM_API_KEY")
    llm_base_url: str | None = Field(default=None, validation_alias="LLM_BASE_URL")
    coordinator_model: str | None = Field(default=None, validation_alias="COORDINATOR_MODEL")
    worker_model: str | None = Field(default=None, validation_alias="WORKER_MODEL")
    llm_temperature: float = Field(default=0.2, validation_alias="LLM_TEMPERATURE")


model_settings = ModelSettings()


class UnsupportedLLMProviderError(ValueError):
    """UnsupportedLLMProviderError（不支持的模型提供商错误）表示模型配置或调用失败。"""
    pass


def to_litellm_model(provider: str, model: str) -> str:
    """转换为 LiteLLM 识别的模型名。

    provider（模型提供商）用于决定是否添加 deepseek/openai 前缀；
    model（模型名）是配置中的原始模型名称。返回值是 LiteLLM 可识别的模型字符串。
    """
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
    """解析当前 LLM 调用配置。

    role（模型角色）决定使用 coordinator_model 还是 worker_model；
    model（模型名）可临时覆盖环境配置；
    temperature（温度）可临时覆盖默认温度。返回值包含 provider、litellm_model、
    api_key、api_base 和 temperature，供 provider 层实际调用。
    """
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
