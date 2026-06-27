import importlib
import json
from datetime import UTC, datetime, timedelta

import pytest

from career_os.platform.pipeline_template import instantiate_pipeline_for_session
from tests.conftest import seed_explore_intake_profile


@pytest.fixture
def isolated_stores(tmp_path, monkeypatch):
    """构造测试环境和基础状态。"""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import career_os.config as config_mod
    import career_os.platform.store.profile as profile_mod
    import career_os.platform.pipeline_template as pipeline_mod
    import career_os.platform.store.session as session_mod
    import career_os.platform.store.task as task_mod

    importlib.reload(config_mod)
    importlib.reload(profile_mod)
    importlib.reload(session_mod)
    importlib.reload(task_mod)
    importlib.reload(pipeline_mod)
    return pipeline_mod, profile_mod, session_mod, task_mod


def test_instantiate_pipeline_creates_five_milestone_files(
    isolated_stores, tmp_path, monkeypatch
):
    """验证 instantiate pipeline creates five milestone files 场景。"""
    pipeline_mod, profile_mod, session_mod, _task_mod = isolated_stores
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    session_id = session_mod.SessionStore().create_session()
    list_id = pipeline_mod.instantiate_pipeline_for_session(session_id)
    assert isinstance(list_id, str)
    assert list_id.startswith("list_")
    meta = json.loads((tmp_path / "tasks" / list_id / "meta.json").read_text())
    assert meta["list_type"] == "pipeline"
    assert meta["current_phase"] == "explore"
    assert meta["session_id"] == session_id
    ms_files = [p for p in (tmp_path / "tasks" / list_id).glob("ms_*.json")]
    assert len(ms_files) == 5


def test_instantiate_pipeline_remains_in_explore_when_profile_is_fresh(
    isolated_stores, tmp_path, monkeypatch
):
    """验证 instantiate pipeline remains in explore when profile is fresh 场景。"""
    pipeline_mod, profile_mod, session_mod, _task_mod = isolated_stores
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    profile = seed_explore_intake_profile(profile_mod.ProfileStore())
    raw = profile.get(["meta", "basic", "skills", "intent", "constraints", "exploration", "career", "capability", "market", "strategy", "resume", "preference_tags", "outputs_index"])
    exploration = dict(raw.get("exploration") or {})
    exploration["completed_at"] = (datetime.now(UTC) - timedelta(days=7)).isoformat()
    raw["exploration"] = exploration
    profile._profile_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")

    session_id = session_mod.SessionStore().create_session()
    list_id = pipeline_mod.instantiate_pipeline_for_session(session_id)
    assert isinstance(list_id, str)
    meta = json.loads((tmp_path / "tasks" / list_id / "meta.json").read_text())
    assert meta["current_phase"] == "explore"
    state = session_mod.SessionStore().get_state(session_id)
    assert state["explore_gate_confirmed"] is True
    assert state["explore_completed_at"] == exploration["completed_at"]
    assert state["explore_closure"]["completed"] is True
