from unittest.mock import MagicMock, patch

from career_os.agents.lc.client import invoke_text
from career_os.agents.lc.models import LLMRole


def test_invoke_text_uses_litellm(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("LLM_API_KEY", "test-key")

    from career_os.agents.lc import models as models_mod

    models_mod.model_settings.__init__()

    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content="hello from litellm"))]

    with patch("career_os.agents.lc.providers.litellm.completion", return_value=mock_response) as mocked:
        text = invoke_text("system prompt", "user prompt", role=LLMRole.WORKER)

    assert text == "hello from litellm"
    mocked.assert_called_once()
    call_kwargs = mocked.call_args.kwargs
    assert call_kwargs["model"] == "deepseek/deepseek-chat"
    assert call_kwargs["api_key"] == "test-key"
    assert call_kwargs["messages"][0]["role"] == "system"
