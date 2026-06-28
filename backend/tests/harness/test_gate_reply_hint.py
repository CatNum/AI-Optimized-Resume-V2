from career_os.harness.gate import append_gate_reply_hint, gate_reply_hint


def test_gate_reply_hint_explore_repeat():
    """验证 gate 回复提示 explore 重复探索的处理符合预期。"""
    assert "不需要" in gate_reply_hint("explore_repeat")


def test_append_gate_reply_hint_idempotent():
    """验证追加 gate 回复提示幂等的处理符合预期。"""
    text = append_gate_reply_hint("请问是否需要再次初探？", "explore_repeat")
    again = append_gate_reply_hint(text, "explore_repeat")
    assert again.count("请回复") == 1
