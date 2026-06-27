import importlib.util
import json
from pathlib import Path


def _load_module():
    """加载测试所需模块或存储对象。"""
    script = Path(__file__).resolve().parents[2] / "scripts" / "migrate_profile_session_boundary.py"
    spec = importlib.util.spec_from_file_location("migrate_profile_session_boundary", script)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migrate_profile_into_single_session(tmp_path):
    """验证 migrate profile into single session 场景。"""
    data = tmp_path
    (data / "sessions" / "sess_1").mkdir(parents=True)
    (data / "sessions" / "sess_1" / "state.json").write_text(
        json.dumps({"session_id": "sess_1"}, ensure_ascii=False), encoding="utf-8"
    )
    (data / "profile.json").write_text(
        json.dumps(
            {
                "exploration": {
                    "completed_at": "2026-06-01T00:00:00Z",
                    "summary": "s",
                    "intake": {"submitted_at": "2026-06-01T00:00:00Z"},
                },
                "market": {"role_families": ["a"]},
                "strategy": {"path_options": [{"id": "x"}]},
                "career": {"jd_override": [{"k": "v"}]},
                "outputs_index": [{"path": "output/demo/a.html"}],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    mod = _load_module()
    result = mod.migrate(data, apply=True)
    assert result["changed"] is True
    state = json.loads((data / "sessions" / "sess_1" / "state.json").read_text(encoding="utf-8"))
    assert state["explore_completed_at"] == "2026-06-01T00:00:00Z"
    assert state["intake_status"]["submitted_at"] == "2026-06-01T00:00:00Z"
    assert state["jd_override"] == [{"k": "v"}]
    artifacts = json.loads(
        (data / "sessions" / "sess_1" / "artifacts.json").read_text(encoding="utf-8")
    )
    assert artifacts["market"]["role_families"] == ["a"]
    assert artifacts["strategy"]["path_options"] == [{"id": "x"}]
    assert artifacts["exploration"]["summary"] == "s"
    profile = json.loads((data / "profile.json").read_text(encoding="utf-8"))
    assert profile["career"]["jd_override"] == []
    assert profile["market"]["role_families"] == []
    assert profile["outputs_index"] == [{"path": "output/demo/a.html"}]


def test_migrate_to_orphan_when_multi_sessions(tmp_path):
    """验证 migrate to orphan when multi sessions 场景。"""
    data = tmp_path
    (data / "sessions" / "sess_a").mkdir(parents=True)
    (data / "sessions" / "sess_b").mkdir(parents=True)
    (data / "profile.json").write_text(
        json.dumps(
            {
                "exploration": {"summary": "s"},
                "market": {"role_families": ["a"]},
                "strategy": {"path_options": [{"id": "x"}]},
                "career": {"jd_override": [{"k": "v"}]},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    mod = _load_module()
    result = mod.migrate(data, apply=True)
    assert result["changed"] is True
    orphan = json.loads((data / "orphan_artifacts.json").read_text(encoding="utf-8"))
    assert orphan["session_scoped_from_profile"]["market"]["role_families"] == ["a"]
    profile = json.loads((data / "profile.json").read_text(encoding="utf-8"))
    assert profile["career"]["jd_override"] == []

