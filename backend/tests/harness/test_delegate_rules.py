import importlib

import pytest

from career_os.harness.executor import Harness
from career_os.platform.store.profile import ProfileStore
from tests.conftest import seed_jd_ready_profile


@pytest.fixture
def harness(tmp_path, monkeypatch):
    """harness（harness）的函数说明。

    tmp_path（参数）、monkeypatch（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import career_os.config as config_mod
    import career_os.platform.store.profile as profile_mod

    importlib.reload(config_mod)
    importlib.reload(profile_mod)
    return Harness()


@pytest.fixture
def session_state():
    """session_state（session state）的函数说明。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    return {
        "list_type": "pipeline",
        "explore_gate_confirmed": True,
        "prior_results": {},
        "gates": {"flags": {"optimize_confirmed": False}},
    }


def test_market_blocked_without_jd_prerequisites(harness, session_state):
    """test_market_blocked_without_jd_prerequisites（测试 market blocked without jd prerequisites）的函数说明。

    harness（参数）、session_state（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    err = harness.delegate_worker("coordinator", "market", "research jd", session_state)
    assert err.code == "delegate_blocked"
    assert err.message.startswith("JD-B1:")


def test_market_allowed_with_jd_prerequisites(harness, session_state):
    """test_market_allowed_with_jd_prerequisites（测试 market allowed with jd prerequisites）的函数说明。

    harness（参数）、session_state（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    seed_jd_ready_profile(ProfileStore())
    result = harness.delegate_worker("coordinator", "market", "research jd", session_state)
    assert result["status"] == "delegated"


def test_opportunity_blocked_without_market(harness, session_state, jd_ready_profile):
    """test_opportunity_blocked_without_market（测试 opportunity blocked without market）的函数说明。

    harness（参数）、session_state（参数）、jd_ready_profile（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    session_state["list_type"] = "pipeline"
    session_state["prior_results"] = {}
    err = harness.delegate_worker(
        "coordinator", "opportunity", "eval jd", session_state
    )
    assert err.code == "delegate_blocked"
    assert "JD-R1" in err.message


def test_opportunity_allowed_with_market(harness, session_state, jd_ready_profile):
    """test_opportunity_allowed_with_market（测试 opportunity allowed with market）的函数说明。

    harness（参数）、session_state（参数）、jd_ready_profile（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    session_state["prior_results"] = {"market": {"topics": ["cloud"]}}
    result = harness.delegate_worker(
        "coordinator", "opportunity", "eval jd", session_state
    )
    assert result["status"] == "delegated"


def test_resume_blocked_without_optimize_confirmed(harness, session_state):
    """test_resume_blocked_without_optimize_confirmed（测试 resume blocked without optimize confirmed）的函数说明。

    harness（参数）、session_state（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    session_state["gates"]["flags"]["optimize_confirmed"] = False
    err = harness.delegate_worker(
        "coordinator", "resume", "optimize resume", session_state
    )
    assert err.code == "gate_blocked"


def test_resume_allowed_with_optimize_confirmed(harness, session_state):
    """test_resume_allowed_with_optimize_confirmed（测试 resume allowed with optimize confirmed）的函数说明。

    harness（参数）、session_state（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    session_state["gates"]["flags"]["optimize_confirmed"] = True
    result = harness.delegate_worker(
        "coordinator", "resume", "optimize resume", session_state
    )
    assert result["status"] == "delegated"


def test_worker_cannot_complete_task(harness):
    """test_worker_cannot_complete_task（测试 worker cannot complete task）的函数说明。

    harness（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    err = harness.execute_tool(
        "identity", "complete_task", {"task_id": "milestone_1"}
    )
    assert err.code == "tool_not_allowed"


def test_worker_cannot_delegate(harness, session_state):
    """test_worker_cannot_delegate（测试 worker cannot delegate）的函数说明。

    harness（参数）、session_state（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    err = harness.delegate_worker(
        "identity", "market", "research", session_state
    )
    assert err.code == "tool_not_allowed"
