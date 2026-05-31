import importlib

import pytest

from career_os.platform.store.profile import ProfileStore


def seed_jd_ready_profile(store: ProfileStore | None = None) -> ProfileStore:
    profile = store or ProfileStore()
    profile.patch(
        [
            {"path": "basic.name", "value": "测试", "op": "set"},
            {"path": "exploration.completed_at", "value": "2026-05-31T00:00:00Z", "op": "set"},
        ]
    )
    return profile


@pytest.fixture
def jd_ready_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import career_os.config as config_mod
    import career_os.platform.store.profile as profile_mod

    importlib.reload(config_mod)
    importlib.reload(profile_mod)
    return seed_jd_ready_profile(ProfileStore())


@pytest.fixture(autouse=True)
def _reset_llm_settings_for_l1(request, monkeypatch):
    """Avoid stale model_settings.llm_api_key leaking from LLM unit tests."""
    if request.node.get_closest_marker("llm"):
        yield
        return
    from career_os.agents.lc import models as models_mod

    # Empty env var overrides backend/.env so L1 keeps react_mocks (not real API).
    monkeypatch.setenv("LLM_API_KEY", "")
    models_mod.model_settings.__init__()
    yield
    models_mod.model_settings.__init__()
