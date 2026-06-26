import importlib

import pytest

from career_os.harness.executor import Harness
from career_os.platform.store.output import OutputStore
from career_os.platform.store.profile import ProfileStore
from career_os.platform.tool.handlers.outputs import dedupe_outputs_index


@pytest.fixture
def harness(tmp_path, monkeypatch):
    """harness（harness）的函数说明。

    tmp_path（参数）、monkeypatch（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    import career_os.config as config_mod
    import career_os.platform.store.output as output_mod
    import career_os.platform.store.profile as profile_mod
    import career_os.platform.tool.handlers.outputs as outputs_mod

    importlib.reload(config_mod)
    importlib.reload(output_mod)
    importlib.reload(profile_mod)
    importlib.reload(outputs_mod)
    return Harness()


def test_dedupe_outputs_index_keeps_first_entry():
    """test_dedupe_outputs_index_keeps_first_entry（测试 dedupe outputs index keeps first entry）的函数说明。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    entries = [
        {"path": "output/2026-05-31/resume_标准.html", "optimization_level": "标准"},
        {"path": "output/2026-05-31/resume_标准.html", "optimization_level": "标准"},
    ]
    assert len(dedupe_outputs_index(entries)) == 1


def test_register_outputs_index_skips_duplicate_path(harness, tmp_path):
    """test_register_outputs_index_skips_duplicate_path（测试 register outputs index skips duplicate path）的函数说明。

    harness（参数）、tmp_path（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    from datetime import date

    day = date(2026, 5, 31)
    html_path = OutputStore().write("resume_标准.html", "<html></html>", day=day)
    delivery = {
        "path": "output/2026-05-31/resume_标准.html",
        "optimization_level": "标准",
        "created_at": "2026-05-31T00:00:00+00:00",
    }

    first = harness.execute_tool(
        "asset",
        "register_outputs_index",
        {"deliveries": [delivery]},
    )
    second = harness.execute_tool(
        "asset",
        "register_outputs_index",
        {"deliveries": [delivery]},
    )

    assert first["registered"]
    assert not first["skipped"]
    assert not second["registered"]
    assert second["skipped"] == [
        {"path": "output/2026-05-31/resume_标准.html", "reason": "already_registered"}
    ]

    index = ProfileStore().get(["outputs_index"])["outputs_index"]
    assert len(index) == 1
