import importlib

import pytest

from career_os.agents.graphs.workers.react_mocks import mock_run_worker_react
from career_os.harness.executor import Harness


@pytest.fixture
def harness(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    import career_os.config as config_mod
    import career_os.platform.store.profile as profile_mod
    import career_os.platform.store.output as output_mod

    importlib.reload(config_mod)
    importlib.reload(profile_mod)
    importlib.reload(output_mod)
    return Harness()


def test_resume_writes_multiple_levels(harness, tmp_path):
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
    assert len(result["structured_output"]["html_deliveries"]) == 2
    day_dir = tmp_path / "output"
    assert any(day_dir.rglob("resume_标准.html"))
    assert any(day_dir.rglob("resume_进取.html"))
