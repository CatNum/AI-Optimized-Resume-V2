import importlib

import pytest

from career_os.agents.graphs.workers.react_mocks import mock_run_worker_react
from career_os.harness.executor import Harness


@pytest.fixture
def harness(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import career_os.config as config_mod

    importlib.reload(config_mod)
    return Harness()


def test_strategy_emits_optimize_gate_on_jd(harness):
    result = mock_run_worker_react(
        harness,
        worker_id="strategy",
        goal="plan strategy",
        session_state={"list_type": "jd", "session_id": "s1"},
        context={"requires_optimize_gate": True},
    )
    assert result["structured_output"]["gate_prompt"]["name"] == "optimize_confirm"


def test_strategy_no_optimize_gate_on_plan(harness):
    result = mock_run_worker_react(
        harness,
        worker_id="strategy",
        goal="plan",
        session_state={"list_type": "plan", "session_id": "s1"},
        context={"requires_optimize_gate": True},
    )
    assert not result["structured_output"].get("gate_prompt")
