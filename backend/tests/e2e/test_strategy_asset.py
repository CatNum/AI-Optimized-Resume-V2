import importlib

import pytest

from career_os.agents.graphs.workers.react_mocks import mock_run_worker_react
from career_os.harness.executor import Harness


@pytest.fixture
def harness(tmp_path, monkeypatch):
    """harness（harness）的函数说明。

    tmp_path（参数）、monkeypatch（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import career_os.config as config_mod

    importlib.reload(config_mod)
    return Harness()


def test_strategy_emits_optimize_gate_on_jd(harness):
    """test_strategy_emits_optimize_gate_on_jd（测试 strategy emits optimize gate on jd）的函数说明。

    harness（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    result = mock_run_worker_react(
        harness,
        worker_id="strategy",
        goal="plan strategy",
        session_state={
            "list_type": "pipeline",
            "explore_gate_confirmed": True,
            "session_id": "s1",
        },
        context={"requires_optimize_gate": True},
    )
    assert result["structured_output"]["gate_prompt"]["name"] == "optimize_confirm"


def test_strategy_no_optimize_gate_on_plan(harness):
    """test_strategy_no_optimize_gate_on_plan（测试 strategy no optimize gate on plan）的函数说明。

    harness（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    result = mock_run_worker_react(
        harness,
        worker_id="strategy",
        goal="plan",
        session_state={"list_type": "plan", "session_id": "s1"},
        context={"requires_optimize_gate": True},
    )
    assert not result["structured_output"].get("gate_prompt")
