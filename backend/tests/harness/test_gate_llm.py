from career_os.harness.gate import match_gate_intent
from career_os.harness.gate_llm import classify_gate_intent_llm


def test_classify_mock_llm_reject(monkeypatch):
    """验证 classify mock llm reject 场景。"""
    monkeypatch.setattr("career_os.harness.micro_classifier.llm_enabled", lambda: True)
    monkeypatch.setattr(
        "career_os.harness.micro_classifier.invoke_json",
        lambda system, user, **kw: {
            "gate_name": "explore_repeat",
            "intent": "reject",
            "confidence": 0.9,
            "reason": "用户不想重复初探",
        },
    )
    result = classify_gate_intent_llm(
        "随便说说",
        {"name": "explore_repeat", "prompt": "是否再次初探？"},
    )
    assert result["matched"] is True
    assert result["intent"] == "reject"
    assert result["source"] == "llm"


def test_low_confidence_unknown_source_llm(monkeypatch):
    """验证 low confidence unknown source llm 场景。"""
    monkeypatch.setattr("career_os.harness.micro_classifier.llm_enabled", lambda: True)
    monkeypatch.setattr(
        "career_os.harness.micro_classifier.invoke_json",
        lambda system, user, **kw: {
            "gate_name": "explore_repeat",
            "intent": "reject",
            "confidence": 0.2,
        },
    )
    result = classify_gate_intent_llm(
        "嗯",
        {"name": "explore_repeat", "prompt": "是否再次初探？"},
    )
    assert result["matched"] is False
    assert result["intent"] == "unknown"
    assert result["source"] == "llm"


def test_rule_hit_skips_llm(monkeypatch):
    """验证 rule hit skips llm 场景。"""
    called = []

    def fake_llm(*args, **kwargs):
        """构造测试替身函数。"""
        called.append(True)
        return {"matched": True, "intent": "confirm", "confidence": 0.9, "source": "llm"}

    monkeypatch.setattr("career_os.harness.gate.classify_gate_intent_llm", fake_llm)
    result = match_gate_intent(
        "无需",
        {"name": "explore_repeat", "prompt": "再次？"},
    )
    assert result["intent"] == "reject"
    assert called == []
