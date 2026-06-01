import importlib
import re

import pytest

from career_os.agents.graphs.coordinator import run_coordinator_turn
from career_os.agents.graphs.workers.registry import build_harness_worker_runner
from career_os.harness.executor import Harness
from career_os.platform.store.profile import ProfileStore
from tests.conftest import seed_jd_ready_profile


@pytest.fixture
def harness(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    import career_os.config as config_mod
    import career_os.platform.store.profile as profile_mod

    importlib.reload(config_mod)
    importlib.reload(profile_mod)
    return Harness()


def test_jd_chain_market_then_opportunity(harness):
    seed_jd_ready_profile(ProfileStore())
    runner = build_harness_worker_runner(harness)
    state = run_coordinator_turn(
        harness,
        session_id="sess_jd",
        session_state={
            "session_id": "sess_jd",
            "list_type": "pipeline",
            "explore_gate_confirmed": True,
            "prior_results": {},
            "gates": {"flags": {}},
        },
        user_message="请评估这个 JD：后端工程师，要求 Kubernetes",
        pending_workers=["market", "opportunity"],
        worker_runner=runner,
    )
    assert state["delegate_count"] == 2
    profile = ProfileStore().get(["market.opportunity_snapshots"])
    assert len(profile["market"]["opportunity_snapshots"]) >= 1


def test_market_before_opportunity_order(harness):
    seed_jd_ready_profile(ProfileStore())
    runner = build_harness_worker_runner(harness)
    calls: list[str] = []

    original = runner

    def tracking_runner(worker_id, goal, session_state, context):
        calls.append(worker_id)
        return original(worker_id, goal, session_state, context)

    run_coordinator_turn(
        harness,
        session_id="sess_order",
        session_state={
            "session_id": "sess_order",
            "list_type": "pipeline",
            "explore_gate_confirmed": True,
            "prior_results": {},
            "gates": {"flags": {}},
        },
        user_message="JD eval",
        pending_workers=["market", "opportunity"],
        worker_runner=tracking_runner,
    )
    assert calls == ["market", "opportunity"]
