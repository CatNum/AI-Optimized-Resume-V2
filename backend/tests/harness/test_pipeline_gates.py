import importlib
from datetime import UTC, datetime, timedelta

import importlib

import pytest

from career_os.harness.pipeline_gates import (
    advance_current_phase,
    compute_needs_full_explore,
    jump_to_phase,
    validate_jump_target,
)
from career_os.platform.store.profile import ProfileStore
from career_os.platform.pipeline_template import instantiate_pipeline_for_session


@pytest.fixture
def env(tmp_path, monkeypatch):
    """构造测试环境和基础状态。"""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import career_os.config as config_mod
    import career_os.platform.store.profile as profile_mod
    import career_os.platform.store.session as session_mod
    import career_os.platform.store.task as task_mod

    importlib.reload(config_mod)
    importlib.reload(profile_mod)
    importlib.reload(session_mod)
    importlib.reload(task_mod)
    return session_mod.SessionStore(), task_mod.TaskStore()


def test_jump_resume_optimize_forbidden(env):
    """验证跳转简历优化禁止的处理符合预期。"""
    session_store, _ = env
    session_id = session_store.create_session()
    state = session_store.get_state(session_id)
    err = validate_jump_target("resume_optimize", state)
    assert err is not None
    assert err.code == "jump_target_forbidden"


def test_jump_explore_allowed_without_gate(env):
    """验证缺少 gate 时允许跳转到 explore。"""
    session_store, _task_store = env
    session_id = session_store.create_session()
    instantiate_pipeline_for_session(session_id)
    state = session_store.get_state(session_id)
    assert validate_jump_target("explore", state) is None


def test_jump_market_requires_explore_gate(env):
    """验证跳转 market Worker 会要求探索 gate。"""
    session_store, task_store = env
    session_id = session_store.create_session()
    list_id = instantiate_pipeline_for_session(session_id)
    state = session_store.get_state(session_id)
    err = jump_to_phase(session_id, list_id, "market", state)
    assert hasattr(err, "code")
    assert err.code == "explore_gate_required"


def test_jump_market_allowed_after_profile_completion_seeds_session(env):
    """验证跳转 market Worker 允许之后 profile 完成写入会话的处理符合预期。"""
    session_store, _task_store = env
    session_id = session_store.create_session()
    profile = ProfileStore()
    profile.patch(
        [
            {
                "path": "exploration.completed_at",
                "value": "2026-06-07T12:39:05.787050+00:00",
                "op": "set",
            }
        ]
    )
    instantiate_pipeline_for_session(session_id)
    state = session_store.get_state(session_id)
    assert state["explore_gate_confirmed"] is True
    assert validate_jump_target("market", state) is None


def test_advance_resume_optimize_does_not_create_default_works(env):
    """验证推进简历优化不会创建默认工作产物。"""
    session_store, task_store = env
    session_id = session_store.create_session()
    list_id = instantiate_pipeline_for_session(session_id)
    state = session_store.get_state(session_id)
    state["list_id"] = list_id
    state["list_type"] = "pipeline"
    state["gates"] = {"flags": {"optimize_confirmed": True}}
    task_store.set_current_phase(list_id, "resume_strategy")

    result = advance_current_phase(session_id, list_id, "resume_optimize", state)

    assert not hasattr(result, "code")
    assert result["current_phase"] == "resume_optimize"
    assert result["created"] == []
    assert result["claimed_work"] is None
    assert task_store.list_works_for_phase(list_id, "resume_optimize") == []


def test_compute_needs_full_explore_false_for_recent_completed_profile(env):
    """验证近期已完成 profile 时不需要完整 explore。"""
    session_store, _ = env
    session_id = session_store.create_session()
    state = session_store.get_state(session_id)

    profile = {
        "basic": {"name": "测试"},
        "capability": {},
        "intent": {
            "years_of_experience": "3",
            "current_salary": "20k",
            "target_salary": "25k",
            "target_role": "AI 产品经理",
        },
        "resume": {"source_text": "简历正文"},
        "exploration": {
            "completed_at": (datetime.now(UTC) - timedelta(days=10)).isoformat(),
            "intake": {
                "submitted_at": "2026-06-01T00:00:00+00:00",
                "resume_text": "简历正文",
            },
            "intake_baseline": {
                "submitted_at": "2026-06-01T00:00:00+00:00",
                "resume_text": "简历正文",
            },
        },
    }

    assert compute_needs_full_explore(profile, state) is False


def test_compute_needs_full_explore_true_for_old_completed_profile(env):
    """验证过期已完成 profile 时需要完整 explore。"""
    session_store, _ = env
    session_id = session_store.create_session()
    state = session_store.get_state(session_id)

    profile = {
        "basic": {"name": "测试"},
        "capability": {},
        "intent": {
            "years_of_experience": "3",
            "current_salary": "20k",
            "target_salary": "25k",
            "target_role": "AI 产品经理",
        },
        "resume": {"source_text": "简历正文"},
        "exploration": {
            "completed_at": (datetime.now(UTC) - timedelta(days=40)).isoformat(),
            "intake": {
                "submitted_at": "2026-06-01T00:00:00+00:00",
                "resume_text": "简历正文",
            },
            "intake_baseline": {
                "submitted_at": "2026-06-01T00:00:00+00:00",
                "resume_text": "简历正文",
            },
        },
    }

    assert compute_needs_full_explore(profile, state) is True


def test_compute_needs_full_explore_true_for_explicit_revisit(env):
    """验证显式重新探索时需要完整 explore。"""
    session_store, _ = env
    session_id = session_store.create_session()
    state = session_store.get_state(session_id)

    profile = {
        "basic": {"name": "测试"},
        "capability": {},
        "intent": {
            "years_of_experience": "3",
            "current_salary": "20k",
            "target_salary": "25k",
            "target_role": "AI 产品经理",
            "requires_career_revisit": True,
        },
        "resume": {"source_text": "简历正文"},
        "exploration": {
            "completed_at": (datetime.now(UTC) - timedelta(days=10)).isoformat(),
            "intake": {
                "submitted_at": "2026-06-01T00:00:00+00:00",
                "resume_text": "简历正文",
            },
            "intake_baseline": {
                "submitted_at": "2026-06-01T00:00:00+00:00",
                "resume_text": "简历正文",
            },
        },
    }

    assert compute_needs_full_explore(profile, state) is True
