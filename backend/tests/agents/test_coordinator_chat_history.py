import json

from career_os.agents.lc import coordinator_llm as mod
from career_os.platform.store.session import slice_chat_rounds, slice_synthesize_chat_history


def test_analyze_payload_uses_six_round_window(monkeypatch):
    """test_analyze_payload_uses_six_round_window（测试 analyze payload uses six round window）的函数说明。

    monkeypatch（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    captured: dict = {}

    def fake_invoke(_s, user, **kw):
        """fake_invoke（fake invoke）的函数说明。

        _s（参数）、user（参数）、**kw（参数）用于向该函数传入运行所需的数据。

        返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
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
    """test_synthesis_payload_uses_one_round_window（测试 synthesis payload uses one round window）的函数说明。

    该函数用于验证对应业务场景的行为是否符合预期。"""
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
