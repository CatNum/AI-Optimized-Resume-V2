def test_touch_index_on_create(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import importlib

    import career_os.config as config_mod
    import career_os.platform.store.session as session_mod

    importlib.reload(config_mod)
    importlib.reload(session_mod)
    s = session_mod.SessionStore()
    sid = s.create_session()
    index = s.load_index()
    assert index["version"] == 1
    rows = {r["session_id"]: r for r in index["sessions"]}
    assert sid in rows
    row = rows[sid]
    assert row["title"] == "未命名会话"
    assert row["title_source"] == "fallback"
    assert row["message_count"] == 0
    assert row["preview"] == ""
    assert row["archived"] is False


def test_touch_index_updates_preview_and_count(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import importlib

    import career_os.config as config_mod
    import career_os.platform.store.session as session_mod

    importlib.reload(config_mod)
    importlib.reload(session_mod)
    s = session_mod.SessionStore()
    sid = s.create_session()
    s.append_message(sid, "assistant", "hi there")
    long_user_msg = "A" * 50
    s.append_message(sid, "user", long_user_msg)
    s.touch_index(sid)
    index = s.load_index()
    rows = {r["session_id"]: r for r in index["sessions"]}
    row = rows[sid]
    assert row["message_count"] == 2
    assert row["preview"] == "A" * 40

    s.append_message(sid, "assistant", "reply")
    s.append_message(sid, "user", "latest user message")
    s.touch_index(sid)
    index = s.load_index()
    rows = {r["session_id"]: r for r in index["sessions"]}
    row = rows[sid]
    assert row["message_count"] == 4
    assert row["preview"] == "latest user message"
