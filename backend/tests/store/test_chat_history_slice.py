import importlib

import pytest


def _reload_store(tmp_path, monkeypatch, **env):
    """加载测试所需模块或存储对象。"""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    for k, v in env.items():
        monkeypatch.setenv(k, str(v))
    import career_os.config as config_mod
    import career_os.platform.store.session as session_mod

    importlib.reload(config_mod)
    importlib.reload(session_mod)
    return session_mod.SessionStore, session_mod


def test_slice_one_round_current_user_only(tmp_path, monkeypatch):
    """验证截取一轮当前用户仅的处理符合预期。"""
    _, session_mod = _reload_store(tmp_path, monkeypatch)
    messages = [{"role": "user", "content": "a"}]
    got = session_mod.slice_chat_rounds(messages, max_rounds=1)
    assert got == messages


def test_slice_one_user_round_is_current_user_only(tmp_path, monkeypatch):
    """验证截取一用户轮是否当前用户仅的处理符合预期。"""
    _, session_mod = _reload_store(tmp_path, monkeypatch)
    messages = [
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "u2"},
    ]
    got = session_mod.slice_chat_rounds(messages, max_rounds=1)
    assert got == [{"role": "user", "content": "u2"}]


def test_slice_synthesize_includes_prior_assistant(tmp_path, monkeypatch):
    """验证截取汇总 phase 会包含 prior_results 助手。"""
    _, session_mod = _reload_store(tmp_path, monkeypatch)
    messages = [
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "u2"},
    ]
    got = session_mod.slice_synthesize_chat_history(messages)
    assert got == messages[-2:]


def test_slice_six_rounds_from_tail(tmp_path, monkeypatch):
    """验证截取六轮从尾部的处理符合预期。"""
    SessionStore, session_mod = _reload_store(tmp_path, monkeypatch)
    messages = []
    for i in range(8):
        messages.append({"role": "user", "content": f"u{i}"})
        messages.append({"role": "assistant", "content": f"a{i}"})
    messages.append({"role": "user", "content": "u8"})
    got = session_mod.slice_chat_rounds(messages, max_rounds=6)
    # 八轮完整对话加第九轮仅用户消息；取最近六轮应从第三轮用户消息开始
    assert got[0]["content"] == "u3"
    assert got[-1]["content"] == "u8"
