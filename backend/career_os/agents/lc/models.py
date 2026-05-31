from pydantic_settings import BaseSettings, SettingsConfigDict


class ModelSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm_api_key: str | None = None
    llm_base_url: str | None = None
    coordinator_model: str = "gpt-4o-mini"
    worker_model: str = "gpt-4o-mini"


model_settings = ModelSettings()
