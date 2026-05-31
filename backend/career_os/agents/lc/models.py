from enum import Enum
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMRole(str, Enum):
    COORDINATOR = "coordinator"
    WORKER = "worker"


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
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm_provider: str = Field(default="deepseek", validation_alias="LLM_PROVIDER")
    llm_api_key: str | None = Field(default=None, validation_alias="LLM_API_KEY")
    llm_base_url: str | None = Field(default=None, validation_alias="LLM_BASE_URL")
    coordinator_model: str | None = Field(default=None, validation_alias="COORDINATOR_MODEL")
    worker_model: str | None = Field(default=None, validation_alias="WORKER_MODEL")
    llm_temperature: float = Field(default=0.2, validation_alias="LLM_TEMPERATURE")


model_settings = ModelSettings()


class UnsupportedLLMProviderError(ValueError):
    pass


def to_litellm_model(provider: str, model: str) -> str:
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
    provider = (model_settings.llm_provider or "deepseek").lower()
    preset = PROVIDER_PRESETS.get(provider)
    if preset is None:
        raise UnsupportedLLMProviderError(f"Unsupported LLM provider: {provider}")

    role_model = (
        model
        or (
            model_settings.coordinator_model
            if role == LLMRole.COORDINATOR
            else model_settings.worker_model
        )
        or preset["coordinator_model" if role == LLMRole.COORDINATOR else "worker_model"]
    )

    return {
        "provider": provider,
        "litellm_model": to_litellm_model(provider, role_model),
        "api_key": model_settings.llm_api_key,
        "api_base": model_settings.llm_base_url or preset.get("api_base"),
        "temperature": temperature if temperature is not None else model_settings.llm_temperature,
    }
