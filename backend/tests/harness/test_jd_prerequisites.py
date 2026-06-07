import importlib
import json
from datetime import UTC, datetime, timedelta

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


def test_jd_ready_when_only_global_exploration_completed(profile_env):
    profile_env.patch([{"path": "basic.name", "value": "测试", "op": "set"}])
    raw = profile_env.get(["meta", "exploration", "basic", "intent", "resume", "outputs_index", "skills", "constraints", "career", "capability", "market", "strategy", "preference_tags"])
    raw.setdefault("exploration", {})["completed_at"] = "2026-05-31T00:00:00Z"
    profile_path = profile_env._profile_path  # test-only direct write for legacy data simulation
    profile_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    ready, reason = check_jd_prerequisites({"prior_results": {}})
    assert ready is True
    assert reason is None


def test_jd_ready_with_session_explore_completed(profile_env):
    profile_env.patch([{"path": "basic.name", "value": "测试", "op": "set"}])
    ready, reason = check_jd_prerequisites(
        {"prior_results": {}, "explore_closure": {"completed": True}}
    )
    assert ready is True


def test_jd_ready_with_fresh_profile_explore_completed(profile_env):
    profile_env.patch(
        [
            {"path": "basic.name", "value": "测试", "op": "set"},
            {"path": "intent.target_role", "value": "AI 产品经理", "op": "set"},
            {"path": "intent.current_salary", "value": "20k", "op": "set"},
            {"path": "intent.target_salary", "value": "25k", "op": "set"},
            {"path": "intent.years_of_experience", "value": "3", "op": "set"},
            {"path": "resume.source_text", "value": "简历正文", "op": "set"},
        ]
    )
    raw = profile_env.get(["meta", "exploration", "basic", "intent", "resume"])
    raw.setdefault("exploration", {})["completed_at"] = (
        datetime.now(UTC) - timedelta(days=10)
    ).isoformat()
    raw["exploration"]["intake"] = {
        "submitted_at": "2026-06-01T00:00:00+00:00",
        "resume_text": "简历正文",
    }
    raw["exploration"]["intake_baseline"] = {
        "submitted_at": "2026-06-01T00:00:00+00:00",
        "resume_text": "简历正文",
    }
    profile_env._profile_path.write_text(  # noqa: SLF001 - test-only legacy fixture
        json.dumps(raw, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    ready, reason = check_jd_prerequisites({"prior_results": {}})
    assert ready is True
    assert reason is None


def test_jd_blocked_when_completed_at_is_stale(profile_env):
    profile_env.patch(
        [
            {"path": "basic.name", "value": "测试", "op": "set"},
            {"path": "intent.target_role", "value": "AI 产品经理", "op": "set"},
            {"path": "intent.current_salary", "value": "20k", "op": "set"},
            {"path": "intent.target_salary", "value": "25k", "op": "set"},
            {"path": "intent.years_of_experience", "value": "3", "op": "set"},
            {"path": "resume.source_text", "value": "简历正文", "op": "set"},
        ]
    )
    stale_at = (datetime.now(UTC) - timedelta(days=40)).isoformat()
    raw = profile_env.get(
        ["meta", "exploration", "basic", "intent", "resume"]
    )
    raw.setdefault("exploration", {})["completed_at"] = stale_at
    raw["exploration"]["intake"] = {
        "submitted_at": "2026-04-01T00:00:00+00:00",
        "resume_text": "简历正文",
    }
    raw["exploration"]["intake_baseline"] = {
        "submitted_at": "2026-04-01T00:00:00+00:00",
        "resume_text": "简历正文",
    }
    profile_env._profile_path.write_text(  # noqa: SLF001 - test-only legacy fixture
        json.dumps(raw, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    ready, reason = check_jd_prerequisites({"prior_results": {}})
    assert ready is False
    assert reason == "explore"


def test_jd_ready_when_current_session_has_completed_explore(profile_env):
    profile_env.patch(
        [
            {"path": "basic.name", "value": "测试", "op": "set"},
            {"path": "intent.target_role", "value": "AI 产品经理", "op": "set"},
            {"path": "intent.current_salary", "value": "20k", "op": "set"},
            {"path": "intent.target_salary", "value": "25k", "op": "set"},
            {"path": "intent.years_of_experience", "value": "3", "op": "set"},
            {"path": "resume.source_text", "value": "简历正文", "op": "set"},
        ]
    )
    raw = profile_env.get(["meta", "exploration", "basic", "intent", "resume"])
    raw.setdefault("exploration", {})["completed_at"] = (
        datetime.now(UTC) - timedelta(days=40)
    ).isoformat()
    profile_env._profile_path.write_text(  # noqa: SLF001 - test-only legacy fixture
        json.dumps(raw, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    ready, reason = check_jd_prerequisites(
        {"prior_results": {}, "explore_closure": {"completed": True}}
    )
    assert ready is True
    assert reason is None
