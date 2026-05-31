import importlib

import pytest

from career_os.agents.graphs.coordinator import run_coordinator_turn
from career_os.agents.graphs.workers.registry import build_harness_worker_runner
from career_os.harness.explore_closure import init_explore_closure
from career_os.harness.executor import Harness


@pytest.fixture
def harness(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import career_os.config as config_mod

    importlib.reload(config_mod)
    return Harness()


def test_explore_workers_set_closure_ready(harness):
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
        user_message="开始初探",
        pending_workers=["identity", "capability"],
        worker_runner=runner,
    )
    closure = state["session_state"]["explore_closure"]
    assert closure["worker_done"]["identity"] is True
    assert closure["worker_done"]["capability"] is True
    assert "explore_complete" in state["session_state"]["gates"]["pending"]["name"]
