from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class MarketResearchSettings(BaseModel):
    """MarketResearchSettings（市场调研设置）集中承载浏览器、采集、预算、抽样和有效期参数。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_directions: int = Field(default=3, ge=1, le=3)  # 单次调研允许的最大职业方向数
    max_keywords_per_direction: int = Field(default=3, ge=1, le=3)  # 单方向允许的最大搜索词数
    max_cities_per_direction: int = Field(default=4, ge=1, le=4)  # 单方向允许的最大城市数
    budget_seconds: int = Field(default=600, ge=1, le=3600)  # 单方向网页与岗位提取 LLM 的总预算秒数；测试可下调
    target_jobs_per_keyword: int = Field(default=30, ge=1, le=100)  # 每个 BOSS 搜索词的新增有效岗位目标；测试可下调
    max_jobs_per_company: Literal[5] = 5  # 单方向同一公司允许保留的固定岗位上限
    screenshot_probability: float = Field(default=0.1, ge=0.0, le=1.0)  # 入样岗位保存完整截图的独立概率
    click_wait_min_seconds: float = Field(default=1.5, ge=0.0)  # 页面点击或返回后的最短等待秒数
    click_wait_max_seconds: float = Field(default=3.0, gt=0.0)  # 页面点击或返回后的最长等待秒数
    condition_wait_min_seconds: float = Field(default=2.0, ge=0.0)  # 切换城市或搜索词后的最短等待秒数
    condition_wait_max_seconds: float = Field(default=5.0, gt=0.0)  # 切换城市或搜索词后的最长等待秒数
    job_detail_retry_times: int = Field(default=2, ge=0, le=5)  # 单个岗位详情读取失败后的最大重试次数
    boss_list_retry_times: int = Field(default=2, ge=0, le=5)  # BOSS 列表页失败后的最大重试次数
    trends_retry_times: int = Field(default=1, ge=0, le=1)  # 搜索关注度页面失败后的最大额外重试次数
    trends_enabled: bool = True  # 是否启用 Google Trends 页面采集；代码默认执行正式采集路径
    storage_retry_times: Literal[1] = 1  # 正式结果写入失败后的固定重试次数
    validity_months: Literal[6] = 6  # 方向结果允许下游复用的自然月数
    chrome_path: str | None = None  # 用户本机 Google Chrome 可执行文件覆盖路径
    poll_interval_seconds: float = Field(default=2.0, gt=0.0, le=30.0)  # 前端状态卡轮询间隔秒数

    @model_validator(mode="after")
    def validate_wait_ranges(self) -> MarketResearchSettings:
        """校验页面操作等待区间的下限不能大于上限。"""
        if self.click_wait_min_seconds > self.click_wait_max_seconds:
            raise ValueError("click_wait_min_seconds must not exceed click_wait_max_seconds")
        if self.condition_wait_min_seconds > self.condition_wait_max_seconds:
            raise ValueError(
                "condition_wait_min_seconds must not exceed condition_wait_max_seconds"
            )
        return self
