import importlib

from typing import Any

import pytest

from career_os.platform.store.profile import ProfileStore


def explore_repeat_cleared_gates() -> dict[str, Any]:
    """Gates flags for sessions that may enter explore after global intake submit."""
    return {
        "flags": {
            "explore_repeat_accepted": True,
            "explore_repeat_baseline_at": "2026-05-30T00:00:00Z",
        }
    }


def seed_explore_intake_profile(store: ProfileStore | None = None) -> ProfileStore:
    profile = store or ProfileStore()
    resume = (
        "张三\n5年工作经验\n当前薪资：30k\n期望岗位：后端工程师\n"
        "期望薪资：35k-45k\n熟悉 Go 与 Kubernetes。"
    )
    profile.patch(
        [
            {
                "path": "exploration.intake.submitted_at",
                "value": "2026-05-31T00:00:00Z",
                "op": "set",
            },
            {"path": "exploration.intake.resume_text", "value": resume, "op": "set"},
            {"path": "exploration.intake.pending_fields", "value": [], "op": "set"},
            {"path": "exploration.intake.resolved_fields", "value": {
                "years_of_experience": "5年",
                "current_salary": "30K",
                "target_salary": "35万",
                "target_role": "后端工程师",
            }, "op": "set"},
            {"path": "resume.source_text", "value": resume, "op": "set"},
            {"path": "basic.name", "value": "测试", "op": "set"},
        ]
    )
    return profile


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
def explore_intake_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import career_os.config as config_mod
    import career_os.platform.store.profile as profile_mod

    importlib.reload(config_mod)
    importlib.reload(profile_mod)
    return seed_explore_intake_profile(ProfileStore())


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
