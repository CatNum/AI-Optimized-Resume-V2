def test_touch_index_on_create(tmp_path, monkeypatch):
    """验证更新索引在创建的处理符合预期。"""
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
    """验证更新索引会更新预览和数量。"""
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


def _reload_session_store(tmp_path, monkeypatch):
    """构造测试环境和基础状态。"""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import importlib

    import career_os.config as config_mod
    import career_os.platform.store.session as session_mod

    importlib.reload(config_mod)
    importlib.reload(session_mod)
    return session_mod.SessionStore()


def test_rebuild_index_from_disk_dirs(tmp_path, monkeypatch):
    """验证重建索引从磁盘目录的处理符合预期。"""
    s = _reload_session_store(tmp_path, monkeypatch)
    session_id = "sess_" + "a" * 32
    session_dir = tmp_path / "sessions" / session_id
    session_dir.mkdir(parents=True)
    now = "2026-05-31T08:00:00+00:00"
    (session_dir / "state.json").write_text(
        f'{{"session_id": "{session_id}", "last_activity_at": "{now}", '
        f'"list_type": null, "prior_results": {{}}, "explore_closure": null, '
        f'"messages_meta": {{}}, "gates": {{}}, "list_id": null}}',
        encoding="utf-8",
    )
    (session_dir / "messages.json").write_text(
        '{"messages": [{"role": "user", "content": "hello from disk"}]}',
        encoding="utf-8",
    )

    s.rebuild_index()
    index = s.load_index()
    rows = {r["session_id"]: r for r in index["sessions"]}
    assert session_id in rows
    assert rows[session_id]["message_count"] == 1
    assert rows[session_id]["preview"] == "hello from disk"


def test_rebuild_prunes_orphan_index_entries(tmp_path, monkeypatch):
    """验证重建清理孤儿索引条目的处理符合预期。"""
    s = _reload_session_store(tmp_path, monkeypatch)
    orphan_id = "sess_" + "0" * 32
    real_id = "sess_" + "1" * 32
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir(parents=True)
    now = "2026-05-31T08:00:00+00:00"
    (sessions_dir / "_index.json").write_text(
        f"""{{
  "version": 1,
  "sessions": [
    {{
      "session_id": "{orphan_id}",
      "title": "ghost",
      "title_source": "fallback",
      "preview": "",
      "created_at": "{now}",
      "last_activity_at": "{now}",
      "message_count": 0,
      "list_type": null,
      "archived": false
    }}
  ]
}}""",
        encoding="utf-8",
    )
    real_dir = sessions_dir / real_id
    real_dir.mkdir()
    (real_dir / "state.json").write_text(
        f'{{"session_id": "{real_id}", "last_activity_at": "{now}", '
        f'"list_type": null, "prior_results": {{}}, "explore_closure": null, '
        f'"messages_meta": {{}}, "gates": {{}}, "list_id": null}}',
        encoding="utf-8",
    )
    (real_dir / "messages.json").write_text('{"messages": []}', encoding="utf-8")

    s.rebuild_index()
    index = s.load_index()
    rows = {r["session_id"]: r for r in index["sessions"]}
    assert orphan_id not in rows
    assert real_id in rows


def test_delete_session_removes_dir_index_and_tasks(tmp_path, monkeypatch):
    """验证删除会话会删除目录索引和任务。"""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import importlib

    import career_os.config as config_mod
    import career_os.platform.store.session as session_mod
    import career_os.platform.store.task as task_mod

    importlib.reload(config_mod)
    importlib.reload(session_mod)
    importlib.reload(task_mod)
    s = session_mod.SessionStore()
    t = task_mod.TaskStore()
    sid = s.create_session()
    s.append_message(sid, "user", "hello")
    list_id = t.create_task_list(sid, list_type="plan")
    t.create_task(list_id, "milestone_1", "Step")

    s.delete_session(sid)

    assert not (tmp_path / "sessions" / sid).exists()
    index = s.load_index()
    rows = {r["session_id"]: r for r in index["sessions"]}
    assert sid not in rows
    assert not (tmp_path / "tasks" / list_id).exists()
    assert not (tmp_path / "tasks" / "_active.json").exists()
