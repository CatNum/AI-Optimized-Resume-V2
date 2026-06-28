import importlib

import pytest

from career_os.agents.graphs.coordinator import run_coordinator_turn
from career_os.agents.graphs.workers.registry import build_harness_worker_runner
from career_os.harness.executor import Harness
from career_os.platform.store.profile import ProfileStore
from tests.conftest import seed_jd_ready_profile


@pytest.fixture
def harness(tmp_path, monkeypatch):
    """构造测试用 Harness。"""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    import career_os.config as config_mod
    import career_os.platform.store.output as output_mod
    import career_os.platform.store.profile as profile_mod

    importlib.reload(config_mod)
    importlib.reload(output_mod)
    importlib.reload(profile_mod)
    return Harness()


@pytest.mark.llm
def test_golden_jd_to_html_structure(harness):
    """验证 JD 到简历 HTML 的黄金路径结构符合预期。"""
    seed_jd_ready_profile(ProfileStore())
    runner = build_harness_worker_runner(harness)
    session_state = {
        "session_id": "sess_golden",
        "list_type": "pipeline",
        "explore_gate_confirmed": True,
        "explore_closure": {"completed": True},
        "intake_status": {"submitted_at": "2026-05-31T00:00:00Z"},
        "prior_results": {},
        "gates": {"flags": {"optimize_confirmed": True}},
    }
    state = run_coordinator_turn(
        harness,
        session_id="sess_golden",
        session_state=session_state,
        user_message="评估 JD 并优化简历",
        pending_workers=["market", "opportunity", "strategy", "resume", "asset"],
        worker_runner=runner,
    )
    assert state["delegate_count"] >= 2
    assert "market" in state["session_state"]["prior_results"]
