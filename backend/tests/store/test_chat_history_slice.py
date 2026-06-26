import importlib

import pytest


def _reload_store(tmp_path, monkeypatch, **env):
    """_reload_store（内部函数 reload store）的函数说明。

    tmp_path（参数）、monkeypatch（参数）、**env（参数）用于向该函数传入运行所需的数据。

    该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    for k, v in env.items():
        monkeypatch.setenv(k, str(v))
    import career_os.config as config_mod
    import career_os.platform.store.session as session_mod

    importlib.reload(config_mod)
    importlib.reload(session_mod)
    return session_mod.SessionStore, session_mod


def test_slice_one_round_current_user_only(tmp_path, monkeypatch):
    """test_slice_one_round_current_user_only（测试 slice one round current user only）的函数说明。

    tmp_path（参数）、monkeypatch（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    _, session_mod = _reload_store(tmp_path, monkeypatch)
    messages = [{"role": "user", "content": "a"}]
    got = session_mod.slice_chat_rounds(messages, max_rounds=1)
    assert got == messages


def test_slice_one_user_round_is_current_user_only(tmp_path, monkeypatch):
    """test_slice_one_user_round_is_current_user_only（测试 slice one user round is current user only）的函数说明。

    tmp_path（参数）、monkeypatch（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    _, session_mod = _reload_store(tmp_path, monkeypatch)
    messages = [
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "u2"},
    ]
    got = session_mod.slice_chat_rounds(messages, max_rounds=1)
    assert got == [{"role": "user", "content": "u2"}]


def test_slice_synthesize_includes_prior_assistant(tmp_path, monkeypatch):
    """test_slice_synthesize_includes_prior_assistant（测试 slice synthesize includes prior assistant）的函数说明。

    tmp_path（参数）、monkeypatch（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    _, session_mod = _reload_store(tmp_path, monkeypatch)
    messages = [
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "u2"},
    ]
    got = session_mod.slice_synthesize_chat_history(messages)
    assert got == messages[-2:]


def test_slice_six_rounds_from_tail(tmp_path, monkeypatch):
    """test_slice_six_rounds_from_tail（测试 slice six rounds from tail）的函数说明。

    tmp_path（参数）、monkeypatch（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    SessionStore, session_mod = _reload_store(tmp_path, monkeypatch)
    messages = []
    for i in range(8):
        messages.append({"role": "user", "content": f"u{i}"})
        messages.append({"role": "assistant", "content": f"a{i}"})
    messages.append({"role": "user", "content": "u8"})
    got = session_mod.slice_chat_rounds(messages, max_rounds=6)
    # 8 轮完整 + 第9轮仅 user；取最近6轮应从 u3 开始
    assert got[0]["content"] == "u3"
    assert got[-1]["content"] == "u8"
