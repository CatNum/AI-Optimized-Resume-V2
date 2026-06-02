import importlib

import pytest

from career_os.harness.explore_closure import PHASE_SEGMENT_COMPLETE
from career_os.platform.pipeline_template import instantiate_pipeline_for_session
from tests.conftest import seed_explore_intake_profile


@pytest.fixture
def pipeline_session(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import career_os.config as config_mod
    import career_os.platform.store.profile as profile_mod
    import career_os.platform.store.session as session_mod
    import career_os.platform.store.task as task_mod

    importlib.reload(config_mod)
    importlib.reload(profile_mod)
    importlib.reload(session_mod)
    importlib.reload(task_mod)
    seed_explore_intake_profile(profile_mod.ProfileStore())

    session_store = session_mod.SessionStore()
    task_store = task_mod.TaskStore()
    session_id = session_store.create_session()
    list_id = instantiate_pipeline_for_session(session_id)
    assert isinstance(list_id, str)
    state = session_store.get_state(session_id)
    state["list_id"] = list_id
    state["list_type"] = "pipeline"
    session_store.update_state(session_id, state)
    return session_store, task_store, session_id, list_id


def test_explore_complete_advances_to_market(pipeline_session, monkeypatch):
    session_store, task_store, session_id, list_id = pipeline_session
    from career_os.api import chat as chat_mod

    importlib.reload(chat_mod)

    monkeypatch.setattr(
        chat_mod,
        "match_gate_intent",
        lambda message, pending, **kwargs: {
            "matched": True,
            "intent": "confirm",
            "gate_name": pending.get("name"),
            "source": "test",
        },
    )

    state = session_store.get_state(session_id)
    state["gates"] = {
        "pending": {"name": "explore_complete", "prompt": "确认完成初探？"},
        "flags": {},
    }
    chat_mod._apply_pending_gate("确认完成初探", state)
    session_store.update_state(session_id, state)

    meta = task_store.get_list_meta(list_id)
    assert meta is not None
    assert meta["current_phase"] == "market"
    assert state["explore_closure"]["completed"] is True
    assert state.get("explore_gate_confirmed") is True


def test_explore_repeat_reject_advances_phase_from_prior(pipeline_session):
    session_store, task_store, session_id, list_id = pipeline_session
    from career_os.api import chat as chat_mod

    importlib.reload(chat_mod)

    state = session_store.get_state(session_id)
    state["prior_results"] = {
        "market": {"phase_status": PHASE_SEGMENT_COMPLETE},
        "opportunity": {"phase_status": PHASE_SEGMENT_COMPLETE},
    }
    state["gates"] = {
        "pending": {"name": "explore_repeat", "prompt": "是否再次初探？"},
        "flags": {},
    }
    chat_mod._apply_pending_gate("不用了", state)
    session_store.update_state(session_id, state)

    meta = task_store.get_list_meta(list_id)
    assert meta is not None
    assert meta["current_phase"] == "jd_analysis"
    assert state["explore_closure"]["completed"] is True
    flags = (state.get("gates") or {}).get("flags") or {}
    assert flags.get("explore_repeat_declined") is True
