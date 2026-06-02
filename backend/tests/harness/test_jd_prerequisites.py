import importlib
import json

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


def test_jd_still_blocked_when_only_global_exploration_completed(profile_env):
    profile_env.patch([{"path": "basic.name", "value": "测试", "op": "set"}])
    raw = profile_env.get(["meta", "exploration", "basic", "intent", "resume", "outputs_index", "skills", "constraints", "career", "capability", "market", "strategy", "preference_tags"])
    raw.setdefault("exploration", {})["completed_at"] = "2026-05-31T00:00:00Z"
    profile_path = profile_env._profile_path  # test-only direct write for legacy data simulation
    profile_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    ready, reason = check_jd_prerequisites({"prior_results": {}})
    assert ready is False
    assert reason == "explore"


def test_jd_ready_with_session_explore_completed(profile_env):
    profile_env.patch([{"path": "basic.name", "value": "测试", "op": "set"}])
    ready, reason = check_jd_prerequisites(
        {"prior_results": {}, "explore_closure": {"completed": True}}
    )
    assert ready is True
