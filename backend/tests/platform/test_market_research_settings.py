from career_os.platform.market_research.settings import MarketResearchSettings


def test_boss_collection_defaults_match_production_budget() -> None:
    """默认保持每关键词 30 个有效岗位与单方向十分钟预算。"""
    settings = MarketResearchSettings()

    assert settings.target_jobs_per_keyword == 30
    assert settings.budget_seconds == 600


def test_boss_collection_budget_allows_fast_test_override() -> None:
    """测试可构造更小的岗位数和预算，不再被固定 Literal（字面量）限制。"""
    settings = MarketResearchSettings(target_jobs_per_keyword=2, budget_seconds=60)

    assert settings.target_jobs_per_keyword == 2
    assert settings.budget_seconds == 60
