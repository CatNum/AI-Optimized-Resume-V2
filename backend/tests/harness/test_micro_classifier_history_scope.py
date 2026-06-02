from career_os.harness.micro_classifier import classify
from career_os.harness.micro_classifier_rules import match_history_scope_rules


def test_rule_full_history_phrases():
    r = match_history_scope_rules("请根据我们完整对话里贴的 JD 分析")
    assert r is not None
    assert r["needs_full_history"] is True
    assert r["source"] == "rule"


def test_classify_history_scope_rule_path():
    out = classify("history_scope", "检查上下文里之前的内容", {})
    assert out["needs_full_history"] is True
    assert out["source"] == "rule"


def test_classify_history_scope_mock_llm(monkeypatch):
    monkeypatch.setattr("career_os.harness.micro_classifier.llm_enabled", lambda: True)
    monkeypatch.setattr(
        "career_os.harness.micro_classifier.invoke_json",
        lambda _s, _u, **kw: {"needs_full_history": True, "confidence": 0.9},
    )
    monkeypatch.setattr(
        "career_os.harness.micro_classifier.match_history_scope_rules",
        lambda _m: None,
    )
    out = classify("history_scope", "随便说说", {})
    assert out["needs_full_history"] is True
    assert out["source"] == "llm"
