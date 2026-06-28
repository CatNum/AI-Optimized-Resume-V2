import importlib
from datetime import date


def test_output_write_list_delete(tmp_path, monkeypatch):
    """验证输出写入列表删除的处理符合预期。"""
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
