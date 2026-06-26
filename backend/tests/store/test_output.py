import importlib
from datetime import date


def test_output_write_list_delete(tmp_path, monkeypatch):
    """test_output_write_list_delete（测试 output write list delete）的函数说明。

    tmp_path（参数）、monkeypatch（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    import career_os.config as config_mod
    import career_os.platform.store.output as output_mod

    importlib.reload(config_mod)
    importlib.reload(output_mod)

    store = output_mod.OutputStore()
    day = date(2026, 5, 31)
    path = store.write("resume.html", "<html></html>", day=day)
    assert path.exists()

    files = store.list_outputs(day=day)
    assert len(files) == 1
    assert files[0].name == "resume.html"

    assert store.delete(path) is True
    assert not path.exists()
