from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    data_dir: str = "./data"
    output_dir: str = "./output"
    session_idle_ttl: int = 86400
    chat_history_max_messages: int = 40
    chat_history_max_tokens: int = 12000
    chat_history_warn_ratio: float = 0.95
    cors_origins: str = "http://127.0.0.1:15173"
    gate_llm_accept_threshold: float = Field(
        default=0.75, validation_alias="GATE_LLM_ACCEPT_THRESHOLD"
    )


settings = Settings()
