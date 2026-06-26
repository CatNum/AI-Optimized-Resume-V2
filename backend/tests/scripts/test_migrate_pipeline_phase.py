import importlib
import importlib.util
import json
from pathlib import Path

from career_os.harness.explore_closure import PHASE_SEGMENT_COMPLETE


def _load_migrate_module():
    """_load_migrate_module（内部函数 load migrate module）的函数说明。

    该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "migrate_pipeline_phase.py"
    spec = importlib.util.spec_from_file_location("migrate_pipeline_phase", script_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migrate_advances_explore_with_jd_prior(tmp_path, monkeypatch):
    """test_migrate_advances_explore_with_jd_prior（测试 migrate advances explore with jd prior）的函数说明。

    tmp_path（参数）、monkeypatch（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import career_os.config as config_mod

    importlib.reload(config_mod)

    data = tmp_path
    list_id = "list_mig01"
    session_id = "sess_mig01"
    list_dir = data / "tasks" / list_id
    list_dir.mkdir(parents=True)
    (data / "sessions" / session_id).mkdir(parents=True)

    meta = {
        "list_id": list_id,
        "list_type": "pipeline",
        "session_id": session_id,
        "current_phase": "explore",
    }
    (list_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

    state = {
        "explore_gate_confirmed": True,
        "gates": {
            "flags": {
                "explore_gate_confirmed": True,
                "explore_repeat_declined": True,
            }
        },
        "explore_closure": {
            "worker_done": {"identity": False, "capability": False},
            "completed": False,
        },
        "prior_results": {
            "market": {"phase_status": PHASE_SEGMENT_COMPLETE},
            "opportunity": {"phase_status": PHASE_SEGMENT_COMPLETE},
        },
    }
    (data / "sessions" / session_id / "state.json").write_text(
        json.dumps(state), encoding="utf-8"
    )

    migrate_mod = _load_migrate_module()
    change = migrate_mod.migrate_list(list_dir, data_dir=data, apply=True)
    assert change is not None
    assert change.get("to_phase") == "jd_analysis"

    meta_after = json.loads((list_dir / "meta.json").read_text(encoding="utf-8"))
    assert meta_after["current_phase"] == "jd_analysis"
    state_after = json.loads(
        (data / "sessions" / session_id / "state.json").read_text(encoding="utf-8")
    )
    assert state_after["explore_closure"]["completed"] is True
