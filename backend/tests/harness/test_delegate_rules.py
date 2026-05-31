import importlib

import pytest

from career_os.harness.executor import Harness
from career_os.platform.store.profile import ProfileStore
from tests.conftest import seed_jd_ready_profile


@pytest.fixture
def harness(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import career_os.config as config_mod
    import career_os.platform.store.profile as profile_mod

    importlib.reload(config_mod)
    importlib.reload(profile_mod)
    return Harness()


@pytest.fixture
def session_state():
    return {
        "list_type": "jd",
        "prior_results": {},
        "gates": {"flags": {"optimize_confirmed": False}},
    }


def test_market_blocked_without_jd_prerequisites(harness, session_state):
    err = harness.delegate_worker("coordinator", "market", "research jd", session_state)
    assert err.code == "delegate_blocked"
    assert err.message.startswith("JD-B1:")


def test_market_allowed_with_jd_prerequisites(harness, session_state):
    seed_jd_ready_profile(ProfileStore())
    result = harness.delegate_worker("coordinator", "market", "research jd", session_state)
    assert result["status"] == "delegated"


def test_opportunity_blocked_without_market(harness, session_state, jd_ready_profile):
    session_state["list_type"] = "jd"
    session_state["prior_results"] = {}
    err = harness.delegate_worker(
        "coordinator", "opportunity", "eval jd", session_state
    )
    assert err.code == "delegate_blocked"
    assert "JD-R1" in err.message


def test_opportunity_allowed_with_market(harness, session_state, jd_ready_profile):
    session_state["prior_results"] = {"market": {"topics": ["cloud"]}}
    result = harness.delegate_worker(
        "coordinator", "opportunity", "eval jd", session_state
    )
    assert result["status"] == "delegated"


def test_resume_blocked_without_optimize_confirmed(harness, session_state):
    session_state["gates"]["flags"]["optimize_confirmed"] = False
    err = harness.delegate_worker(
        "coordinator", "resume", "optimize resume", session_state
    )
    assert err.code == "gate_blocked"


def test_resume_allowed_with_optimize_confirmed(harness, session_state):
    session_state["gates"]["flags"]["optimize_confirmed"] = True
    result = harness.delegate_worker(
        "coordinator", "resume", "optimize resume", session_state
    )
    assert result["status"] == "delegated"


def test_worker_cannot_complete_task(harness):
    err = harness.execute_tool(
        "identity", "complete_task", {"task_id": "milestone_1"}
    )
    assert err.code == "tool_not_allowed"


def test_worker_cannot_delegate(harness, session_state):
    err = harness.delegate_worker(
        "identity", "market", "research", session_state
    )
    assert err.code == "tool_not_allowed"
