import importlib

import pytest

from career_os.agents.graphs.workers.react_mocks import mock_run_worker_react
from career_os.harness.executor import Harness
from career_os.platform.store.profile import ProfileStore


@pytest.fixture
def harness(tmp_path, monkeypatch):
    """构造测试用 Harness。"""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    import career_os.config as config_mod
    import career_os.platform.store.output as output_mod
    import career_os.platform.store.profile as profile_mod
    import career_os.platform.tool.handlers.outputs as outputs_mod

    importlib.reload(config_mod)
    importlib.reload(output_mod)
    importlib.reload(profile_mod)
    importlib.reload(outputs_mod)
    return Harness()


def test_asset_registers_resume_deliveries(harness):
    """验证 asset Worker 会登记 resume Worker 交付物。"""
    session_state = {
        "session_id": "sess_asset",
        "gates": {"flags": {"optimize_confirmed": True}},
        "prior_results": {},
    }
    resume_result = mock_run_worker_react(
        harness,
        worker_id="resume",
        goal="optimize",
        session_state=session_state,
        context={"selected_optimization_levels": ["标准"]},
    )
    session_state["prior_results"]["resume"] = resume_result["structured_output"]
    asset_result = mock_run_worker_react(
        harness,
        worker_id="asset",
        goal="register",
        session_state=session_state,
        context={"run_kind": "register"},
    )
    assert asset_result["status"] == "completed"
    index = ProfileStore().get(["outputs_index"])["outputs_index"]
    assert len(index) >= 1
