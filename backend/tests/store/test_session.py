def test_usage_ratio_scales_with_message_count(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CHAT_HISTORY_MAX_MESSAGES", "40")
    monkeypatch.setenv("CHAT_HISTORY_MAX_TOKENS", "12000")
    import importlib

    import career_os.config as config_mod
    import career_os.platform.store.session as session_mod

    importlib.reload(config_mod)
    importlib.reload(session_mod)
    SessionStore = session_mod.SessionStore

    s = SessionStore()
    sid = s.create_session()
    for i in range(4):
        s.append_message(sid, "user" if i % 2 == 0 else "assistant", f"m{i}")
    _, meta = s.load_messages_for_coordinator(sid)
    assert meta["message_count"] == 4
    assert meta["max_messages"] == 40
    assert meta["usage_ratio"] == 0.1
    assert meta["trimmed"] is False


def test_messages_trim_keeps_first_user(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CHAT_HISTORY_MAX_MESSAGES", "5")
    import importlib

    import career_os.config as config_mod
    import career_os.platform.store.session as session_mod

    importlib.reload(config_mod)
    importlib.reload(session_mod)
    SessionStore = session_mod.SessionStore

    s = SessionStore()
    sid = s.create_session()
    for i in range(10):
        s.append_message(sid, "user" if i % 2 == 0 else "assistant", f"m{i}")
    loaded, meta = s.load_messages_for_coordinator(sid)
    assert loaded[0]["content"] == "m0"  # 首条 user
    assert len(loaded) <= 5
    assert meta["trimmed"] is True


def test_reset_session_clears_messages_and_state(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import importlib

    import career_os.config as config_mod
    import career_os.platform.store.session as session_mod

    importlib.reload(config_mod)
    importlib.reload(session_mod)
    SessionStore = session_mod.SessionStore

    s = SessionStore()
    sid = s.create_session()
    s.append_message(sid, "user", "hello")
    s.update_state(sid, {"gates": {"flags": {"deep_explore_accepted": True}}})
    s.reset_session(sid)
    loaded, meta = s.load_messages_for_coordinator(sid)
    assert loaded == []
    assert meta["total_count"] == 0
    state = s.get_state(sid)
    assert state.get("gates", {}).get("flags", {}).get("deep_explore_accepted") is not True
