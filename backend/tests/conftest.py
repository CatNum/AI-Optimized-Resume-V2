import pytest


@pytest.fixture(autouse=True)
def _reset_llm_settings_for_l1(request, monkeypatch):
    """Avoid stale model_settings.llm_api_key leaking from LLM unit tests."""
    if request.node.get_closest_marker("llm"):
        yield
        return
    from career_os.agents.lc import models as models_mod

    monkeypatch.delenv("LLM_API_KEY", raising=False)
    models_mod.model_settings.__init__()
    yield
    models_mod.model_settings.__init__()
