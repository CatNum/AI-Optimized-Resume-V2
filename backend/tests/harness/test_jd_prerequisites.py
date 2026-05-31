import importlib

import pytest

from career_os.harness.jd_prerequisites import check_jd_prerequisites, is_jd_intent
from career_os.platform.store.profile import ProfileStore


@pytest.fixture
def profile_env(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import career_os.config as config_mod
    import career_os.platform.store.profile as profile_mod

    importlib.reload(config_mod)
    importlib.reload(profile_mod)
    yield ProfileStore()


def test_is_jd_intent():
    assert is_jd_intent("帮我评估这份 JD")
    assert is_jd_intent("这个岗位匹配吗")
    assert not is_jd_intent("你好")


def test_jd_blocked_without_onboarding(profile_env):
    ready, reason = check_jd_prerequisites({"prior_results": {}})
    assert ready is False
    assert reason == "onboarding"


def test_jd_blocked_without_explore(profile_env):
    profile_env.patch([{"path": "basic.name", "value": "测试", "op": "set"}])
    ready, reason = check_jd_prerequisites({"prior_results": {}})
    assert ready is False
    assert reason == "explore"


def test_jd_ready_with_exploration_completed_at(profile_env):
    profile_env.patch(
        [
            {"path": "basic.name", "value": "测试", "op": "set"},
            {"path": "exploration.completed_at", "value": "2026-05-31T00:00:00Z", "op": "set"},
        ]
    )
    ready, reason = check_jd_prerequisites({"prior_results": {}})
    assert ready is True
    assert reason is None


def test_jd_ready_with_session_explore_completed(profile_env):
    profile_env.patch([{"path": "basic.name", "value": "测试", "op": "set"}])
    ready, reason = check_jd_prerequisites(
        {"prior_results": {}, "explore_closure": {"completed": True}}
    )
    assert ready is True
