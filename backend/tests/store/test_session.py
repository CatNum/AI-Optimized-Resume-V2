import importlib


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
    return session_mod.SessionStore


def test_load_chat_history_full_count(tmp_path, monkeypatch):
    """test_load_chat_history_full_count（测试 load chat history full count）的函数说明。

    tmp_path（参数）、monkeypatch（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    SessionStore = _reload_store(tmp_path, monkeypatch, CHAT_HISTORY_MAX_TOKENS="200000")
    s = SessionStore()
    sid = s.create_session()
    for i in range(10):
        s.append_message(sid, "user" if i % 2 == 0 else "assistant", f"m{i}")
    loaded, meta = s.load_chat_history(sid)
    assert len(loaded) == 10
    assert meta["total_count"] == 10
    assert meta["loaded_count"] == 10
    assert "trimmed" not in meta
    assert meta["over_limit"] is False


def test_usage_ratio_is_token_based(tmp_path, monkeypatch):
    """test_usage_ratio_is_token_based（测试 usage ratio is token based）的函数说明。

    tmp_path（参数）、monkeypatch（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    SessionStore = _reload_store(tmp_path, monkeypatch, CHAT_HISTORY_MAX_TOKENS="12000")
    s = SessionStore()
    sid = s.create_session()
    for i in range(4):
        s.append_message(sid, "user" if i % 2 == 0 else "assistant", f"m{i}")
    _, meta = s.load_chat_history(sid)
    assert meta["total_count"] == 4
    assert meta["token_count"] == 4
    assert meta["usage_ratio"] == round(4 / 12000, 4)


def test_reset_session_clears_messages_and_state(tmp_path, monkeypatch):
    """test_reset_session_clears_messages_and_state（测试 reset session clears messages and state）的函数说明。

    tmp_path（参数）、monkeypatch（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    SessionStore = _reload_store(tmp_path, monkeypatch)
    s = SessionStore()
    sid = s.create_session()
    s.append_message(sid, "user", "hello")
    s.update_state(sid, {"gates": {"flags": {"deep_explore_accepted": True}}})
    s.reset_session(sid)
    loaded, meta = s.load_chat_history(sid)
    assert loaded == []
    assert meta["total_count"] == 0
    state = s.get_state(sid)
    assert state.get("gates", {}).get("flags", {}).get("deep_explore_accepted") is not True


def test_session_artifacts_default_and_patch(tmp_path, monkeypatch):
    """test_session_artifacts_default_and_patch（测试 session artifacts default and patch）的函数说明。

    tmp_path（参数）、monkeypatch（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    SessionStore = _reload_store(tmp_path, monkeypatch)
    s = SessionStore()
    sid = s.create_session()
    artifacts = s.get_artifacts(sid)
    assert artifacts["session_id"] == sid
    assert artifacts["market"] == {}
    s.patch_artifacts(
        sid,
        [
            {"path": "market", "value": {"role_families": ["x"]}, "op": "set"},
            {"path": "exploration.identity", "value": {"summary": "ok"}, "op": "set"},
        ],
    )
    updated = s.get_artifacts(sid)
    assert updated["market"]["role_families"] == ["x"]
    assert updated["exploration"]["identity"]["summary"] == "ok"
