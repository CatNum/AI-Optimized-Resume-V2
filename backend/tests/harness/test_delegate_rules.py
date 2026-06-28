import importlib

import pytest

from career_os.harness.executor import Harness
from career_os.platform.store.profile import ProfileStore
from tests.conftest import seed_jd_ready_profile


@pytest.fixture
def harness(tmp_path, monkeypatch):
    """构造测试用 Harness。"""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import career_os.config as config_mod
    import career_os.platform.store.profile as profile_mod

    importlib.reload(config_mod)
    importlib.reload(profile_mod)
    return Harness()


@pytest.fixture
def session_state():
    """构造测试环境和基础状态。"""
    return {
        "list_type": "pipeline",
        "explore_gate_confirmed": True,
        "prior_results": {},
        "gates": {"flags": {"optimize_confirmed": False}},
    }


def test_market_blocked_without_jd_prerequisites(harness, session_state):
    """验证缺少 JD 前置条件时，market Worker 被拦截的处理符合预期。"""
    err = harness.delegate_worker("coordinator", "market", "research jd", session_state)
    assert err.code == "delegate_blocked"
    assert err.message.startswith("JD-B1:")


def test_market_allowed_with_jd_prerequisites(harness, session_state):
    """验证 market Worker 允许具备 JD 前置条件的处理符合预期。"""
    seed_jd_ready_profile(ProfileStore())
    result = harness.delegate_worker("coordinator", "market", "research jd", session_state)
    assert result["status"] == "delegated"


def test_opportunity_blocked_without_market(harness, session_state, jd_ready_profile):
    """验证缺少 market Worker 时，opportunity Worker 被拦截的处理符合预期。"""
    session_state["list_type"] = "pipeline"
    session_state["prior_results"] = {}
    err = harness.delegate_worker(
        "coordinator", "opportunity", "eval jd", session_state
    )
    assert err.code == "delegate_blocked"
    assert "JD-R1" in err.message


def test_opportunity_allowed_with_market(harness, session_state, jd_ready_profile):
    """验证 opportunity Worker 允许具备 market Worker 的处理符合预期。"""
    session_state["prior_results"] = {"market": {"topics": ["cloud"]}}
    result = harness.delegate_worker(
        "coordinator", "opportunity", "eval jd", session_state
    )
    assert result["status"] == "delegated"


def test_resume_blocked_without_optimize_confirmed(harness, session_state):
    """验证缺少优化已确认时，resume Worker 被拦截的处理符合预期。"""
    session_state["gates"]["flags"]["optimize_confirmed"] = False
    err = harness.delegate_worker(
        "coordinator", "resume", "optimize resume", session_state
    )
    assert err.code == "gate_blocked"


def test_resume_allowed_with_optimize_confirmed(harness, session_state):
    """验证 resume Worker 允许具备优化已确认的处理符合预期。"""
    session_state["gates"]["flags"]["optimize_confirmed"] = True
    result = harness.delegate_worker(
        "coordinator", "resume", "optimize resume", session_state
    )
    assert result["status"] == "delegated"


def test_worker_cannot_complete_task(harness):
    """验证 Worker 不能完成任务。"""
    err = harness.execute_tool(
        "identity", "complete_task", {"task_id": "milestone_1"}
    )
    assert err.code == "tool_not_allowed"


def test_worker_cannot_delegate(harness, session_state):
    """验证 Worker 不能委派。"""
    err = harness.delegate_worker(
        "identity", "market", "research", session_state
    )
    assert err.code == "tool_not_allowed"
