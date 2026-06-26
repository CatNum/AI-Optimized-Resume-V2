import pytest

from career_os.harness.gate import match_gate_intent


def test_explore_complete_confirm():
    """test_explore_complete_confirm（测试 explore complete confirm）的函数说明。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    result = match_gate_intent("确认完成初探")
    assert result["matched"] is True
    assert result["gate_name"] == "explore_complete"
    assert result["intent"] == "confirm"


def test_explore_complete_confirm_natural_phrases():
    """test_explore_complete_confirm_natural_phrases（测试 explore complete confirm natural phrases）的函数说明。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    pending = {"name": "explore_complete", "prompt": "请确认是否完成初探？"}
    for message in ("确认完成", "足够完整梳理了", "到位了", "初探已经到位"):
        result = match_gate_intent(message, pending_gate=pending)
        assert result["matched"] is True, message
        assert result["intent"] == "confirm", message


def test_optimize_confirm_reject():
    """test_optimize_confirm_reject（测试 optimize confirm reject）的函数说明。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    result = match_gate_intent(
        "先不优化",
        pending_gate={"name": "optimize_confirm", "prompt": "是否确认优化？"},
    )
    assert result["matched"] is True
    assert result["gate_name"] == "optimize_confirm"
    assert result["intent"] == "reject"


def test_unknown_when_no_match(monkeypatch):
    """test_unknown_when_no_match（测试 unknown when no match）的函数说明。

    monkeypatch（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    monkeypatch.setattr("career_os.harness.micro_classifier.llm_enabled", lambda: False)
    result = match_gate_intent(
        "随便聊聊",
        pending_gate={"name": "optimize_confirm"},
    )
    assert result["intent"] == "unknown"
    assert result.get("source") == "none"


def test_explore_complete_with_next_step_pending(monkeypatch):
    """test_explore_complete_with_next_step_pending（测试 explore complete with next step pending）的函数说明。

    monkeypatch（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    monkeypatch.setattr("career_os.harness.micro_classifier.llm_enabled", lambda: False)
    result = match_gate_intent(
        "已经完成初探 下一步",
        pending_gate={"name": "explore_complete", "prompt": "请确认完成初探"},
    )
    assert result["matched"] is True
    assert result["intent"] == "confirm"


def test_explore_complete_question_does_not_fallback_to_llm_confirm(monkeypatch):
    """test_explore_complete_question_does_not_fallback_to_llm_confirm（测试 explore complete question does not fallback to llm confirm）的函数说明。

    monkeypatch（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    def fake_llm(*args, **kwargs):
        """fake_llm（fake llm）的函数说明。

        *args（参数）、**kwargs（参数）用于向该函数传入运行所需的数据。

        返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
        return {
            "matched": True,
            "intent": "confirm",
            "gate_name": "explore_complete",
            "source": "llm",
        }

    monkeypatch.setattr("career_os.harness.gate.classify_gate_intent_llm", fake_llm)
    result = match_gate_intent(
        "素材线，也就是能力图谱线我们完成了探索？",
        pending_gate={"name": "explore_complete", "prompt": "请确认完成初探"},
    )

    assert result["matched"] is False
    assert result["intent"] == "unknown"
    assert result["source"] == "none"


def test_explore_complete_continue_more_is_reject():
    """test_explore_complete_continue_more_is_reject（测试 explore complete continue more is reject）的函数说明。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    result = match_gate_intent(
        "还要继续聊聊",
        pending_gate={"name": "explore_complete", "prompt": "请确认完成初探"},
    )

    assert result["matched"] is True
    assert result["intent"] == "reject"
