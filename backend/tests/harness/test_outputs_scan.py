import importlib
from datetime import date

from career_os.platform.tool.handlers.outputs import merge_outputs_index, resolve_output_file
from career_os.platform.tool.handlers.resume_html import ensure_html_filename


def test_ensure_html_filename_appends_suffix():
    """验证 ensure html filename appends suffix 场景。"""
    assert ensure_html_filename("resume_进取_AI_Agent") == "resume_进取_AI_Agent.html"
    assert ensure_html_filename("resume.html") == "resume.html"


def _reload_output_modules(tmp_path, monkeypatch, *, output_subdir: str):
    """加载测试所需模块或存储对象。"""
    out = tmp_path / output_subdir
    monkeypatch.setenv("OUTPUT_DIR", str(out))
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    import career_os.config as config_mod
    import career_os.platform.store.output as output_mod
    import career_os.platform.tool.handlers.outputs as outputs_mod

    importlib.reload(config_mod)
    importlib.reload(output_mod)
    importlib.reload(outputs_mod)
    return output_mod, outputs_mod


def test_merge_outputs_index_includes_disk_files(tmp_path, monkeypatch):
    """验证 merge outputs index includes disk files 场景。"""
    output_mod, outputs_mod = _reload_output_modules(tmp_path, monkeypatch, output_subdir="output")

    day = date(2026, 6, 1)
    file_path = output_mod.OutputStore().write(
        "resume_进取_AI_Agent_后端开发",
        "<html><body>ok</body></html>",
        day=day,
    )
    path_str = outputs_mod.normalize_output_path(file_path)

    merged = merge_outputs_index([])
    assert len(merged) == 1
    assert merged[0]["path"] == path_str
    assert merged[0]["optimization_level"] == "进取"

    resolved = resolve_output_file(path_str)
    assert resolved is not None
    assert resolved.name == "resume_进取_AI_Agent_后端开发"


def test_normalize_output_path_idempotent_for_demo_env(tmp_path, monkeypatch):
    """验证 normalize output path idempotent for demo env 场景。"""
    output_mod, outputs_mod = _reload_output_modules(
        tmp_path, monkeypatch, output_subdir="output/demo"
    )
    day = date(2026, 6, 1)
    file_path = output_mod.OutputStore().write(
        "resume_进取.html",
        "<html><body>ok</body></html>",
        day=day,
    )
    once = outputs_mod.normalize_output_path(file_path)
    twice = outputs_mod.normalize_output_path(once)
    assert once == "output/demo/2026-06-01/resume_进取.html"
    assert twice == once
    assert outputs_mod.resolve_output_file(once) is not None


def test_resolve_doubled_canonical_prefix(tmp_path, monkeypatch):
    """验证 resolve doubled canonical prefix 场景。"""
    output_mod, outputs_mod = _reload_output_modules(
        tmp_path, monkeypatch, output_subdir="output/demo"
    )
    day = date(2026, 6, 1)
    output_mod.OutputStore().write(
        "resume_进取_AI_Agent_后端开发",
        "<html><body>ok</body></html>",
        day=day,
    )
    corrupted = "output/demo/output/demo/2026-06-01/resume_进取_AI_Agent_后端开发"
    fixed = outputs_mod.normalize_output_path(corrupted)
    assert fixed == "output/demo/2026-06-01/resume_进取_AI_Agent_后端开发"
    assert outputs_mod.resolve_output_file(corrupted) is not None


def test_validate_resume_html_rejects_plain_text():
    """验证 validate resume html rejects plain text 场景。"""
    import career_os.platform.tool.handlers.resume_html as resume_mod

    plain = "苑晓龙\nGo 后端工程师\nEXPERIENCE\n..."
    ok, reason = resume_mod.validate_resume_html_content(plain)
    assert not ok
    assert "HTML" in reason


def test_write_resume_html_rejects_invalid_content(tmp_path, monkeypatch):
    """验证 write resume html rejects invalid content 场景。"""
    _reload_output_modules(tmp_path, monkeypatch, output_subdir="output/demo")
    import career_os.platform.tool.handlers.resume_html as resume_mod

    result = resume_mod.write_resume_html(
        "resume",
        {"html": "纯文本简历\n无标签", "optimization_level": "保守"},
    )
    assert hasattr(result, "code")
    assert result.code == "invalid_html"


def test_write_resume_html_uses_prd_filename_template(tmp_path, monkeypatch):
    """验证 write resume html uses prd filename template 场景。"""
    _reload_output_modules(tmp_path, monkeypatch, output_subdir="output/demo")
    import career_os.platform.tool.handlers.resume_html as resume_mod

    result = resume_mod.write_resume_html(
        "resume",
        {
            "html": "<html><body>ok</body></html>",
            "optimization_level": "标准",
            "filename_tags": ["Go后端", "AIAgent"],
            "filename": "resume_标准.html",
        },
    )
    assert not hasattr(result, "code")
    path = result["path"]
    assert path.endswith("-标准.html")
    assert "Go后端-AIAgent" in path


def test_write_resume_html_auto_derives_tags_from_role_and_stack(tmp_path, monkeypatch):
    """验证 write resume html auto derives tags from role and stack 场景。"""
    _reload_output_modules(tmp_path, monkeypatch, output_subdir="output/demo")
    import career_os.platform.tool.handlers.resume_html as resume_mod

    result = resume_mod.write_resume_html(
        "resume",
        {
            "html": "<html><body>ok</body></html>",
            "optimization_level": "进取",
            "target_role": "Agent开发工程师跨端方向",
            "tech_stack_tags": ["Golang", "K8s", "LangGraph"],
        },
    )
    assert not hasattr(result, "code")
    assert result["filename_tags"] == ["Agent开发工程师跨端方向", "Golang", "K8s"]
    path = result["path"]
    assert path.endswith("-进取.html")
    assert "Agent开发工程师跨端方向-Golang-K8s" in path
