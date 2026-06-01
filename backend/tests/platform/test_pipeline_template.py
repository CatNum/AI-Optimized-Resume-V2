import importlib
import json

import pytest

from career_os.platform.pipeline_template import instantiate_pipeline_for_session


@pytest.fixture
def isolated_stores(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import career_os.config as config_mod
    import career_os.platform.pipeline_template as pipeline_mod
    import career_os.platform.store.session as session_mod
    import career_os.platform.store.task as task_mod

    importlib.reload(config_mod)
    importlib.reload(session_mod)
    importlib.reload(task_mod)
    importlib.reload(pipeline_mod)
    return pipeline_mod, session_mod, task_mod


def test_instantiate_pipeline_creates_five_milestone_files(
    isolated_stores, tmp_path, monkeypatch
):
    pipeline_mod, session_mod, _task_mod = isolated_stores
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
