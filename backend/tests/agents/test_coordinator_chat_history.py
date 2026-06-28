import json

from career_os.agents.lc import coordinator_llm as mod
from career_os.platform.store.session import slice_chat_rounds, slice_synthesize_chat_history


def test_analyze_payload_uses_six_round_window(monkeypatch):
    """验证分析 phase 载荷会使用六轮窗口。"""
    captured: dict = {}

    def fake_invoke(_s, user, **kw):
        """构造测试替身函数。"""
        captured["payload"] = json.loads(user)
        return {"workers": []}

    monkeypatch.setattr(mod.lc_client, "llm_enabled", lambda: True)
    monkeypatch.setattr(mod.lc_client, "invoke_json", fake_invoke)

    messages = []
    for i in range(8):
        messages.append({"role": "user", "content": f"u{i}"})
        messages.append({"role": "assistant", "content": f"a{i}"})
    messages.append({"role": "user", "content": "u8"})
    window = slice_chat_rounds(messages, max_rounds=6)

    mod.analyze_workers(
        "u8",
        {"list_type": "pipeline"},
        [],
        chat_history=window,
        messages_meta={"over_limit": False},
    )
    assert captured["payload"]["chat_history"] == window
    assert captured["payload"]["chat_history"][0]["content"] == "u3"


def test_synthesis_payload_uses_one_round_window():
    """验证汇总 phase 载荷会使用一轮窗口。"""
    messages = [
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "u2"},
    ]
    window = slice_synthesize_chat_history(messages)
    _, user = mod.build_synthesis_messages(
        "u2",
        "draft",
        {},
        None,
        chat_history=window,
        messages_meta={},
    )
    payload = json.loads(user)
    assert payload["chat_history"] == window
