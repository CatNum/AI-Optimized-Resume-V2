from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings（Settings）的项目代码结构说明。

    该类封装当前模块中的一组相关状态或行为，供业务代码、测试代码或运行时流程复用。"""
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    data_dir: str = "./data"
    output_dir: str = "./output"
    chat_history_max_tokens: int = 200_000
    chat_history_warn_ratio: float = 0.95
    coordinator_analyze_max_rounds: int = 6
    coordinator_synthesize_max_rounds: int = 1
    worker_default_max_rounds: int = 10
    cors_origins: str = "http://127.0.0.1:15173"
    gate_llm_accept_threshold: float = Field(
        default=0.75, validation_alias="GATE_LLM_ACCEPT_THRESHOLD"
    )
    history_scope_llm_accept_threshold: float = Field(
        default=0.75, validation_alias="HISTORY_SCOPE_LLM_ACCEPT_THRESHOLD"
    )


settings = Settings()
