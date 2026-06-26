from career_os.harness.gate import append_gate_reply_hint, gate_reply_hint


def test_gate_reply_hint_explore_repeat():
    """test_gate_reply_hint_explore_repeat（测试 gate reply hint explore repeat）的函数说明。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    assert "不需要" in gate_reply_hint("explore_repeat")


def test_append_gate_reply_hint_idempotent():
    """test_append_gate_reply_hint_idempotent（测试 append gate reply hint idempotent）的函数说明。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    text = append_gate_reply_hint("请问是否需要再次初探？", "explore_repeat")
    again = append_gate_reply_hint(text, "explore_repeat")
    assert again.count("请回复") == 1
