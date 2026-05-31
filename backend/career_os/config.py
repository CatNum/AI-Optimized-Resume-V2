from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    data_dir: str = "./data"
    output_dir: str = "./output"
    session_idle_ttl: int = 86400
    chat_history_max_messages: int = 40
    chat_history_max_tokens: int = 12000
    chat_history_warn_ratio: float = 0.95


settings = Settings()
