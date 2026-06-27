import importlib
import json
from datetime import UTC, datetime, timedelta

import pytest

from career_os.harness.jd_prerequisites import check_jd_prerequisites, is_jd_intent
from career_os.platform.store.profile import ProfileStore


@pytest.fixture
def profile_env(tmp_path, monkeypatch):
    """profile_env（profile env）的函数说明。

    tmp_path（参数）、monkeypatch（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import career_os.config as config_mod
    import career_os.platform.store.profile as profile_mod

    importlib.reload(config_mod)
    importlib.reload(profile_mod)
    yield ProfileStore()


def test_is_jd_intent():
    """test_is_jd_intent（测试 is jd intent）的函数说明。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    assert is_jd_intent("帮我评估这份 JD")
    assert is_jd_intent("这个岗位匹配吗")
    assert not is_jd_intent("你好")


def test_jd_blocked_without_onboarding(profile_env):
    """test_jd_blocked_without_onboarding（测试 jd blocked without onboarding）的函数说明。

    profile_env（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    ready, reason = check_jd_prerequisites({"prior_results": {}})
    assert ready is False
    assert reason == "onboarding"


def test_jd_blocked_without_explore(profile_env):
    """test_jd_blocked_without_explore（测试 jd blocked without explore）的函数说明。

    profile_env（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    profile_env.patch([{"path": "basic.name", "value": "测试", "op": "set"}])
    ready, reason = check_jd_prerequisites({"prior_results": {}})
    assert ready is False
    assert reason == "explore"


def test_jd_ready_when_only_global_exploration_completed(profile_env):
    """test_jd_ready_when_only_global_exploration_completed（测试 jd ready when only global exploration completed）的函数说明。

    profile_env（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    profile_env.patch([{"path": "basic.name", "value": "测试", "op": "set"}])
    raw = profile_env.get(["meta", "exploration", "basic", "intent", "resume", "outputs_index", "skills", "constraints", "career", "capability", "market", "strategy", "preference_tags"])
    raw.setdefault("exploration", {})["completed_at"] = "2026-05-31T00:00:00Z"
    profile_path = profile_env._profile_path  # 仅测试使用：直接写入以模拟旧数据。
    profile_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    ready, reason = check_jd_prerequisites({"prior_results": {}})
    assert ready is True
    assert reason is None


def test_jd_ready_with_session_explore_completed(profile_env):
    """test_jd_ready_with_session_explore_completed（测试 jd ready with session explore completed）的函数说明。

    profile_env（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    profile_env.patch([{"path": "basic.name", "value": "测试", "op": "set"}])
    ready, reason = check_jd_prerequisites(
        {"prior_results": {}, "explore_closure": {"completed": True}}
    )
    assert ready is True


def test_jd_ready_with_fresh_profile_explore_completed(profile_env):
    """test_jd_ready_with_fresh_profile_explore_completed（测试 jd ready with fresh profile explore completed）的函数说明。

    profile_env（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
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
    """test_jd_blocked_when_completed_at_is_stale（测试 jd blocked when completed at is stale）的函数说明。

    profile_env（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
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
    """test_jd_ready_when_current_session_has_completed_explore（测试 jd ready when current session has completed explore）的函数说明。

    profile_env（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
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
