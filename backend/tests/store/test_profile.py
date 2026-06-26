def test_profile_created_empty_on_first_access(tmp_path, monkeypatch):
    """test_profile_created_empty_on_first_access（测试 profile created empty on first access）的函数说明。

    tmp_path（参数）、monkeypatch（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
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
    """test_profile_patch_set（测试 profile patch set）的函数说明。

    tmp_path（参数）、monkeypatch（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
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
    """test_profile_patch_rejects_session_scoped_path（测试 profile patch rejects session scoped path）的函数说明。

    tmp_path（参数）、monkeypatch（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
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
    """test_outputs_index_requires_session_id（测试 outputs index requires session id）的函数说明。

    tmp_path（参数）、monkeypatch（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
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
