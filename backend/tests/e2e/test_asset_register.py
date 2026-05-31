import importlib

import pytest

from career_os.agents.graphs.workers import asset as asset_worker
from career_os.agents.graphs.workers import resume as resume_worker
from career_os.harness.executor import Harness
from career_os.platform.store.profile import ProfileStore


@pytest.fixture
def harness(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    import career_os.config as config_mod
    import career_os.platform.store.output as output_mod
    import career_os.platform.store.profile as profile_mod

    importlib.reload(config_mod)
    importlib.reload(output_mod)
    importlib.reload(profile_mod)
    return Harness()


def test_asset_registers_resume_deliveries(harness):
    session_state = {
        "session_id": "sess_asset",
        "gates": {"flags": {"optimize_confirmed": True}},
        "prior_results": {},
    }
    resume_result = resume_worker.run(
        harness,
        "optimize",
        session_state,
        {"selected_optimization_levels": ["标准"]},
    )
    session_state["prior_results"]["resume"] = resume_result["structured_output"]
    asset_result = asset_worker.run(
        harness,
        "register",
        session_state,
        {"run_kind": "register"},
    )
    assert asset_result["status"] == "completed"
    index = ProfileStore().get(["outputs_index"])["outputs_index"]
    assert len(index) >= 1
