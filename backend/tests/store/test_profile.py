def test_profile_created_empty_on_first_access(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from career_os.platform.store.profile import ProfileStore

    store = ProfileStore()
    assert store.ensure_empty_profile() is True
    assert (tmp_path / "profile.json").exists()
    data = store.get(["basic", "intent", "market"])
    assert data["basic"] == {}
    assert data["intent"] == {}
    assert data["market"]["role_families"] == []
    assert store.ensure_empty_profile() is False


def test_profile_patch_set(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from career_os.platform.store.profile import ProfileStore

    store = ProfileStore()
    store.patch([{"path": "basic.name", "value": "测试", "op": "set"}])
    assert store.get(["basic.name"])["basic"]["name"] == "测试"
