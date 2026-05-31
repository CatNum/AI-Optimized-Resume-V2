import pytest

from career_os.harness.gate import match_gate_intent


def test_explore_complete_confirm():
    result = match_gate_intent("确认完成初探")
    assert result["matched"] is True
    assert result["gate_name"] == "explore_complete"
    assert result["intent"] == "confirm"


def test_optimize_confirm_reject():
    result = match_gate_intent(
        "先不优化",
        pending_gate={"name": "optimize_confirm", "prompt": "是否确认优化？"},
    )
    assert result["matched"] is True
    assert result["gate_name"] == "optimize_confirm"
    assert result["intent"] == "reject"


def test_unknown_when_no_match():
    result = match_gate_intent(
        "随便聊聊",
        pending_gate={"name": "optimize_confirm"},
    )
    assert result["intent"] == "unknown"
