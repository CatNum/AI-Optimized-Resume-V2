import importlib

import pytest

from career_os.harness.pipeline_gates import jump_to_phase, validate_jump_target
from career_os.platform.pipeline_template import instantiate_pipeline_for_session


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import career_os.config as config_mod
    import career_os.platform.store.session as session_mod
    import career_os.platform.store.task as task_mod

    importlib.reload(config_mod)
    importlib.reload(session_mod)
    importlib.reload(task_mod)
    return session_mod.SessionStore(), task_mod.TaskStore()


def test_jump_resume_optimize_forbidden(env):
    session_store, _ = env
    session_id = session_store.create_session()
    state = session_store.get_state(session_id)
    err = validate_jump_target("resume_optimize", state)
    assert err is not None
    assert err.code == "jump_target_forbidden"


def test_jump_explore_allowed_without_gate(env):
    session_store, _task_store = env
    session_id = session_store.create_session()
    instantiate_pipeline_for_session(session_id)
    state = session_store.get_state(session_id)
    assert validate_jump_target("explore", state) is None


def test_jump_market_requires_explore_gate(env):
    session_store, task_store = env
    session_id = session_store.create_session()
    list_id = instantiate_pipeline_for_session(session_id)
    state = session_store.get_state(session_id)
    err = jump_to_phase(session_id, list_id, "market", state)
    assert hasattr(err, "code")
    assert err.code == "explore_gate_required"
