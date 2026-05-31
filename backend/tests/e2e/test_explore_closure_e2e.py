import importlib

import pytest

from career_os.agents.graphs.coordinator import run_coordinator_turn
from career_os.agents.graphs.workers.registry import build_harness_worker_runner
from career_os.harness.explore_closure import (
    PHASE_IN_PROGRESS,
    PHASE_SEGMENT_COMPLETE,
    init_explore_closure,
)
from career_os.harness.executor import Harness


@pytest.fixture
def harness(tmp_path, monkeypatch, explore_intake_profile):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        "career_os.agents.lc.coordinator_llm.llm_enabled",
        lambda: False,
    )
    import career_os.config as config_mod

    importlib.reload(config_mod)
    return Harness()


def test_explore_first_turn_in_progress_no_gate(harness):
    runner = build_harness_worker_runner(harness)
    session_state = {
        "session_id": "sess_exp",
        "list_type": "explore",
        "prior_results": {},
        "gates": {"flags": {}},
        "explore_closure": init_explore_closure(),
    }
    state = run_coordinator_turn(
        harness,
        session_id="sess_exp",
        session_state=session_state,
        user_message="帮我理清职业方向",
        pending_workers=["identity", "capability"],
        worker_runner=runner,
    )
    closure = state["session_state"]["explore_closure"]
    assert closure["worker_done"]["identity"] is False
    assert closure["worker_done"]["capability"] is False
    assert state["session_state"].get("gates", {}).get("pending") is None
    assert state["session_state"]["prior_results"]["identity"]["phase_status"] == (
        PHASE_IN_PROGRESS
    )
    draft = state.get("synthesis_draft") or ""
    assert "看重" in draft or "了解" in draft


def test_explore_gate_after_both_segments_complete(harness):
    runner = build_harness_worker_runner(harness)
    session_state = {
        "session_id": "sess_exp2",
        "list_type": "explore",
        "prior_results": {},
        "gates": {"flags": {}},
        "explore_closure": init_explore_closure(),
    }

    state = run_coordinator_turn(
        harness,
        session_id="sess_exp2",
        session_state=session_state,
        user_message="帮我理清职业方向",
        pending_workers=["identity", "capability"],
        worker_runner=runner,
    )
    session_state = state["session_state"]
    assert session_state["explore_closure"]["worker_done"]["identity"] is False

    state = run_coordinator_turn(
        harness,
        session_id="sess_exp2",
        session_state=session_state,
        user_message="我看重技术深度和稳定团队",
        pending_workers=[],
        worker_runner=runner,
    )
    session_state = state["session_state"]
    assert session_state["explore_closure"]["worker_done"]["identity"] is True
    assert session_state["explore_closure"]["worker_done"]["capability"] is False
    assert "capability" not in session_state["prior_results"]

    state = run_coordinator_turn(
        harness,
        session_id="sess_exp2",
        session_state=session_state,
        user_message="做过两个后端项目，负责 API 与部署",
        pending_workers=[],
        worker_runner=runner,
    )
    session_state = state["session_state"]
    assert session_state["prior_results"]["capability"]["phase_status"] == PHASE_IN_PROGRESS

    state = run_coordinator_turn(
        harness,
        session_id="sess_exp2",
        session_state=session_state,
        user_message="项目细节已补充完整",
        pending_workers=[],
        worker_runner=runner,
    )
    closure = state["session_state"]["explore_closure"]
    assert closure["worker_done"]["identity"] is True
    assert closure["worker_done"]["capability"] is True
    assert state["session_state"]["gates"]["pending"]["name"] == "explore_complete"
