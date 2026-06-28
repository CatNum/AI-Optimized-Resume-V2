import pytest

from career_os.harness.gate import match_gate_intent


def test_explore_complete_confirm():
    """验证探索完成确认的处理符合预期。"""
    result = match_gate_intent("确认完成初探")
    assert result["matched"] is True
    assert result["gate_name"] == "explore_complete"
    assert result["intent"] == "confirm"


def test_explore_complete_confirm_natural_phrases():
    """验证探索完成确认自然表达的处理符合预期。"""
    pending = {"name": "explore_complete", "prompt": "请确认是否完成初探？"}
    for message in ("确认完成", "足够完整梳理了", "到位了", "初探已经到位"):
        result = match_gate_intent(message, pending_gate=pending)
        assert result["matched"] is True, message
        assert result["intent"] == "confirm", message


def test_optimize_confirm_reject():
    """验证优化确认拒绝的处理符合预期。"""
    result = match_gate_intent(
        "先不优化",
        pending_gate={"name": "optimize_confirm", "prompt": "是否确认优化？"},
    )
    assert result["matched"] is True
    assert result["gate_name"] == "optimize_confirm"
    assert result["intent"] == "reject"


def test_unknown_when_no_match(monkeypatch):
    """验证不匹配时，未知的处理符合预期。"""
    monkeypatch.setattr("career_os.harness.micro_classifier.llm_enabled", lambda: False)
    result = match_gate_intent(
        "随便聊聊",
        pending_gate={"name": "optimize_confirm"},
    )
    assert result["intent"] == "unknown"
    assert result.get("source") == "none"


def test_explore_complete_with_next_step_pending(monkeypatch):
    """验证探索完成具备下一步待处理项的处理符合预期。"""
    monkeypatch.setattr("career_os.harness.micro_classifier.llm_enabled", lambda: False)
    result = match_gate_intent(
        "已经完成初探 下一步",
        pending_gate={"name": "explore_complete", "prompt": "请确认完成初探"},
    )
    assert result["matched"] is True
    assert result["intent"] == "confirm"


def test_explore_complete_question_does_not_fallback_to_llm_confirm(monkeypatch):
    """验证探索完成问题不会兜底到 LLM 确认。"""
    def fake_llm(*args, **kwargs):
        """构造测试替身函数。"""
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
    """验证探索完成继续继续补充是否拒绝的处理符合预期。"""
    result = match_gate_intent(
        "还要继续聊聊",
        pending_gate={"name": "explore_complete", "prompt": "请确认完成初探"},
    )

    assert result["matched"] is True
    assert result["intent"] == "reject"
