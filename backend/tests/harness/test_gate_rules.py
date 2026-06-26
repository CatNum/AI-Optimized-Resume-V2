import pytest

from career_os.harness.gate import match_gate_intent
from career_os.harness.gate_rules import match_gate_intent_rules


@pytest.mark.parametrize(
    "message",
    ["无需", "推进下一步", "已经完成初探 下一步", "先看看市场"],
)
def test_explore_repeat_reject_phrases(message: str):
    """test_explore_repeat_reject_phrases（测试 explore repeat reject phrases）的函数说明。

    message（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    pending = {"name": "explore_repeat", "prompt": "是否需要再次初探？"}
    result = match_gate_intent_rules(message, pending)
    assert result["matched"] is True
    assert result["intent"] == "reject"
    assert result["source"] == "rule"


def test_explore_repeat_confirm_complete_phrase_not_confirm():
    """test_explore_repeat_confirm_complete_phrase_not_confirm（测试 explore repeat confirm complete phrase not confirm）的函数说明。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    pending = {"name": "explore_repeat", "prompt": "是否需要再次初探？"}
    result = match_gate_intent_rules("确认完成初探", pending)
    assert result["intent"] != "confirm" or not result.get("matched")


def test_explore_repeat_willing_again_confirm():
    """test_explore_repeat_willing_again_confirm（测试 explore repeat willing again confirm）的函数说明。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    pending = {"name": "explore_repeat", "prompt": "是否需要再次初探？"}
    result = match_gate_intent_rules("愿意再次初探", pending)
    assert result["matched"] is True
    assert result["intent"] == "confirm"


def test_explore_repeat_wuxu_via_orchestrator(monkeypatch):
    """test_explore_repeat_wuxu_via_orchestrator（测试 explore repeat wuxu via orchestrator）的函数说明。

    monkeypatch（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    monkeypatch.setattr(
        "career_os.harness.gate.classify_gate_intent_llm",
        lambda *a, **k: {"matched": False, "intent": "unknown", "source": "llm"},
    )
    result = match_gate_intent(
        "无需",
        {"name": "explore_repeat", "prompt": "再次初探？"},
    )
    assert result["intent"] == "reject"
    assert result["source"] == "rule"
