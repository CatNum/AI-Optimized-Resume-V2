from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Settings（应用设置）承载后端运行时从环境变量和默认值读取的配置。
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")  # 模型配置

    data_dir: str = "./data"  # 数据目录
    output_dir: str = "./output"  # 输出目录
    chat_history_max_tokens: int = 200_000  # 聊天历史最大 token 数
    chat_history_warn_ratio: float = 0.95  # 聊天历史告警比例
    coordinator_analyze_max_rounds: int = 6  # Coordinator 分析历史轮数
    coordinator_synthesize_max_rounds: int = 1  # Coordinator 合成历史轮数
    worker_default_max_rounds: int = 10  # Worker 默认历史轮数
    cors_origins: str = "http://127.0.0.1:15173"  # 允许跨域来源
    gate_llm_accept_threshold: float = Field(  # 门禁 LLM 接受阈值
        default=0.75, validation_alias="GATE_LLM_ACCEPT_THRESHOLD"
    )
    history_scope_llm_accept_threshold: float = Field(  # 历史范围分类阈值
        default=0.75, validation_alias="HISTORY_SCOPE_LLM_ACCEPT_THRESHOLD"
    )


settings = Settings()
