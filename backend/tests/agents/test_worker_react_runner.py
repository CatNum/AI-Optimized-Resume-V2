from unittest.mock import MagicMock, patch

import pytest

from career_os.agents.graphs.workers.react_runner import run_worker_react
from career_os.harness.executor import Harness


@pytest.fixture
def harness(tmp_path, monkeypatch):
    """harness（harness）的函数说明。

    tmp_path（参数）、monkeypatch（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    return Harness()


def test_react_emits_valid_market_output(harness, monkeypatch):
    """test_react_emits_valid_market_output（测试 react emits valid market output）的函数说明。

    harness（参数）、monkeypatch（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    tool_call = MagicMock()
    tool_call.function.name = "profile_patch"
    tool_call.function.arguments = '{"path":"market.role_families","value":["后端"],"op":"set"}'
    tool_call.id = "call_1"

    final_msg = MagicMock()
    final_msg.content = '{"user_visible_summary":"调研完成","topics":[{"topic":"云原生","summary":"需求上升"}]}'
    final_msg.tool_calls = None

    with patch("career_os.agents.graphs.workers.react_runner.litellm.completion") as mocked:
        mocked.side_effect = [
            MagicMock(choices=[MagicMock(message=MagicMock(content=None, tool_calls=[tool_call]))]),
            MagicMock(choices=[MagicMock(message=final_msg)]),
        ]
        result = run_worker_react(
            harness,
            worker_id="market",
            goal="调研 JD 相关市场",
            session_state={"session_id": "s1"},
            context={"capability_bundle": {"skill_index": [], "tool_index": []}},
        )

    assert result["status"] == "completed"
    assert result["structured_output"]["topics"]
