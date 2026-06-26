from unittest.mock import MagicMock, patch

from career_os.agents.lc.client import stream_text


def test_stream_text_yields_deltas(monkeypatch):
    """test_stream_text_yields_deltas（测试 stream text yields deltas）的函数说明。

    monkeypatch（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    import career_os.agents.lc.models as models_mod

    models_mod.model_settings.__init__()

    chunk1 = MagicMock()
    chunk1.choices = [MagicMock(delta=MagicMock(content="Hello"))]
    chunk2 = MagicMock()
    chunk2.choices = [MagicMock(delta=MagicMock(content=" world"))]

    with patch("career_os.agents.lc.providers.litellm.completion") as mocked:
        mocked.return_value = iter([chunk1, chunk2])
        tokens = list(stream_text("system", "user"))
    assert tokens == ["Hello", " world"]
