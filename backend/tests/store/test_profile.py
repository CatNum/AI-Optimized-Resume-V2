def test_profile_created_empty_on_first_access(tmp_path, monkeypatch):
    """验证 profile created empty on first access 场景。"""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import importlib

    import career_os.config as config_mod
    import career_os.platform.store.profile as profile_mod

    importlib.reload(config_mod)
    importlib.reload(profile_mod)
    store = profile_mod.ProfileStore()
    assert store.ensure_empty_profile() is True
    assert (tmp_path / "profile.json").exists()
    data = store.get(["basic", "intent", "market"])
    assert data["basic"] == {}
    assert data["intent"] == {}
    assert data["market"]["role_families"] == []
    assert store.ensure_empty_profile() is False


def test_profile_patch_set(tmp_path, monkeypatch):
    """验证 profile patch set 场景。"""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import importlib

    import career_os.config as config_mod
    import career_os.platform.store.profile as profile_mod

    importlib.reload(config_mod)
    importlib.reload(profile_mod)
    store = profile_mod.ProfileStore()
    store.patch([{"path": "basic.name", "value": "测试", "op": "set"}])
    assert store.get(["basic.name"])["basic"]["name"] == "测试"


def test_profile_patch_rejects_session_scoped_path(tmp_path, monkeypatch):
    """验证 profile patch rejects session scoped path 场景。"""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import importlib

    import career_os.config as config_mod
    import career_os.platform.store.profile as profile_mod

    importlib.reload(config_mod)
    importlib.reload(profile_mod)
    store = profile_mod.ProfileStore()
    try:
        store.patch([{"path": "market.role_families", "value": ["x"], "op": "set"}])
        assert False, "expected profile_path_forbidden"
    except ValueError as exc:
        assert "profile_path_forbidden" in str(exc)


def test_outputs_index_requires_session_id(tmp_path, monkeypatch):
    """验证 outputs index requires session id 场景。"""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import importlib

    import career_os.config as config_mod
    import career_os.platform.store.profile as profile_mod

    importlib.reload(config_mod)
    importlib.reload(profile_mod)
    store = profile_mod.ProfileStore()
    try:
        store.patch(
            [
                {
                    "path": "outputs_index",
                    "value": [{"path": "output/demo/a.html", "kind": "resume_html"}],
                    "op": "set",
                }
            ]
        )
        assert False, "expected outputs_index session_id validation"
    except ValueError as exc:
        assert "outputs_index" in str(exc)
