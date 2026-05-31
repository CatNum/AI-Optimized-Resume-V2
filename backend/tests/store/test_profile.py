def test_profile_patch_set(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from career_os.platform.store.profile import ProfileStore

    store = ProfileStore()
    store.patch([{"path": "basic.name", "value": "测试", "op": "set"}])
    assert store.get(["basic.name"])["basic"]["name"] == "测试"
