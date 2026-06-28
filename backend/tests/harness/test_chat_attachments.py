import importlib
from pathlib import Path

import pytest

from career_os.harness.chat_attachments import (
    build_request_context_from_attachments,
    enrich_user_message_with_attachments,
)


@pytest.fixture
def output_env(tmp_path, monkeypatch):
    """构造测试环境和基础状态。"""
    out = tmp_path / "output" / "demo" / "2026-06-02"
    out.mkdir(parents=True)
    html = out / "resume.html"
    html.write_text("<html><body>ok</body></html>", encoding="utf-8")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    import career_os.config as config_mod
    import career_os.platform.store.output as output_mod
    import career_os.platform.tool.handlers.outputs as outputs_mod

    importlib.reload(config_mod)
    importlib.reload(output_mod)
    importlib.reload(outputs_mod)
    return f"output/demo/2026-06-02/{html.name}"


def test_build_request_context_resolves_file_ref(output_env):
    """验证构建请求上下文会解析文件引用。"""
    ctx = build_request_context_from_attachments(
        [{"type": "file_ref", "path": output_env, "optimization_level": "保守"}]
    )
    assert ctx["user_specified_resume_path"].endswith("resume.html")
    assert ctx["reuse_path"] == ctx["user_specified_resume_path"]
    assert len(ctx["resume_file_refs"]) == 1
    assert ctx["resume_file_refs"][0]["optimization_level"] == "保守"


def test_build_request_context_skips_missing_file(tmp_path):
    """验证构建请求上下文会跳过缺失文件。"""
    ctx = build_request_context_from_attachments(
        [{"type": "file_ref", "path": "output/demo/missing.html"}]
    )
    assert ctx == {}


def test_enrich_user_message_appends_block(output_env):
    """验证增强用户消息会追加块。"""
    text = enrich_user_message_with_attachments(
        "请复用这份简历",
        [{"type": "file_ref", "path": output_env}],
    )
    assert "请复用这份简历" in text
    assert "【用户引用的简历文件】" in text
    assert "resume.html" in text
