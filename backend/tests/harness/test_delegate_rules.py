import pytest

from career_os.harness.executor import Harness


@pytest.fixture
def harness():
    return Harness()


@pytest.fixture
def session_state():
    return {
        "list_type": "jd",
        "prior_results": {},
        "gates": {"flags": {"optimize_confirmed": False}},
    }


def test_opportunity_blocked_without_market(harness, session_state):
    session_state["list_type"] = "jd"
    session_state["prior_results"] = {}
    err = harness.delegate_worker(
        "coordinator", "opportunity", "eval jd", session_state
    )
    assert err.code == "delegate_blocked"


def test_opportunity_allowed_with_market(harness, session_state):
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
