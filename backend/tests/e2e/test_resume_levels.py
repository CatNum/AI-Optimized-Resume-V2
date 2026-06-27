import importlib

import pytest

from career_os.agents.graphs.workers.react_mocks import mock_run_worker_react
from career_os.harness.executor import Harness


@pytest.fixture
def harness(tmp_path, monkeypatch):
    """构造测试用 Harness。"""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    import career_os.config as config_mod
    import career_os.platform.store.profile as profile_mod
    import career_os.platform.store.output as output_mod
    import career_os.platform.tool.handlers.outputs as outputs_mod

    importlib.reload(config_mod)
    importlib.reload(profile_mod)
    importlib.reload(output_mod)
    importlib.reload(outputs_mod)
    return Harness()


def test_resume_writes_multiple_levels(harness, tmp_path):
    """验证 resume writes multiple levels 场景。"""
    session_state = {
        "session_id": "sess_resume",
        "gates": {"flags": {"optimize_confirmed": True}},
        "prior_results": {},
    }
    result = mock_run_worker_react(
        harness,
        worker_id="resume",
        goal="optimize",
        session_state=session_state,
        context={"selected_optimization_levels": ["标准", "进取"]},
    )
    assert result["status"] == "completed"
    deliveries = result["structured_output"]["html_deliveries"]
    assert len(deliveries) == 2
    levels_written = {d["optimization_level"] for d in deliveries}
    assert levels_written == {"标准", "进取"}
    for d in deliveries:
        assert d["path"].endswith(".html")
        assert d["optimization_level"] in d["path"]
