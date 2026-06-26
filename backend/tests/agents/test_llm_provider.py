import pytest

from career_os.agents.lc.models import (
    LLMRole,
    UnsupportedLLMProviderError,
    resolve_llm_config,
    to_litellm_model,
)


def test_deepseek_default_config(monkeypatch):
    """test_deepseek_default_config（测试 deepseek default config）的函数说明。

    monkeypatch（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("COORDINATOR_MODEL", raising=False)
    monkeypatch.delenv("WORKER_MODEL", raising=False)

    from career_os.agents.lc import models as models_mod

    models_mod.model_settings.__init__()

    coordinator = resolve_llm_config(role=LLMRole.COORDINATOR)
    worker = resolve_llm_config(role=LLMRole.WORKER)

    assert coordinator["provider"] == "deepseek"
    assert coordinator["litellm_model"] == "deepseek/deepseek-chat"
    assert coordinator["api_base"] == "https://api.deepseek.com"
    assert coordinator["api_key"] == "test-key"
    assert worker["litellm_model"] == "deepseek/deepseek-chat"


def test_custom_model_override(monkeypatch):
    """test_custom_model_override（测试 custom model override）的函数说明。

    monkeypatch（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("COORDINATOR_MODEL", "deepseek-reasoner")

    from career_os.agents.lc import models as models_mod

    models_mod.model_settings.__init__()

    config = resolve_llm_config(role=LLMRole.COORDINATOR)
    assert config["litellm_model"] == "deepseek/deepseek-reasoner"


def test_full_litellm_model_passthrough():
    """test_full_litellm_model_passthrough（测试 full litellm model passthrough）的函数说明。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    assert to_litellm_model("deepseek", "deepseek/deepseek-chat") == "deepseek/deepseek-chat"


def test_openai_compatible_custom_base_url(monkeypatch):
    """test_openai_compatible_custom_base_url（测试 openai compatible custom base url）的函数说明。

    monkeypatch（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    monkeypatch.setenv("LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://gateway.example/v1")

    from career_os.agents.lc import models as models_mod

    models_mod.model_settings.__init__()

    config = resolve_llm_config(role=LLMRole.WORKER)
    assert config["provider"] == "openai_compatible"
    assert config["api_base"] == "https://gateway.example/v1"
    assert config["litellm_model"] == "gpt-4o-mini"


def test_unknown_provider_raises(monkeypatch):
    """test_unknown_provider_raises（测试 unknown provider raises）的函数说明。

    monkeypatch（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    monkeypatch.setenv("LLM_PROVIDER", "unknown-vendor")

    from career_os.agents.lc import models as models_mod

    models_mod.model_settings.__init__()

    with pytest.raises(UnsupportedLLMProviderError):
        resolve_llm_config(role=LLMRole.WORKER)
