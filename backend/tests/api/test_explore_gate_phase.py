import importlib

import pytest

from career_os.harness.explore_closure import PHASE_SEGMENT_COMPLETE
from career_os.platform.pipeline_template import instantiate_pipeline_for_session
from tests.conftest import seed_explore_intake_profile


@pytest.fixture
def pipeline_session(tmp_path, monkeypatch):
    """构造测试环境和基础状态。"""
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
    """验证 explore complete advances to market 场景。"""
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


def test_explore_complete_question_does_not_advance_phase(pipeline_session, monkeypatch):
    """验证 explore complete question does not advance phase 场景。"""
    session_store, task_store, session_id, list_id = pipeline_session
    from career_os.api import chat as chat_mod

    importlib.reload(chat_mod)

    state = session_store.get_state(session_id)
    state["gates"] = {
        "pending": {"name": "explore_complete", "prompt": "确认完成初探？"},
        "flags": {},
    }
    state["explore_closure"] = {
        "gate_name": "explore_complete",
        "required_workers": ["identity", "capability"],
        "worker_done": {"identity": True, "capability": True},
        "gate_pending": True,
    }
    chat_mod._apply_pending_gate("素材线，也就是能力图谱线我们完成了探索？", state)
    session_store.update_state(session_id, state)

    meta = task_store.get_list_meta(list_id)
    assert meta is not None
    assert meta["current_phase"] == "explore"
    assert state["gates"]["pending"]["name"] == "explore_complete"
    assert state.get("explore_gate_confirmed") is not True
    assert not state["explore_closure"].get("completed")


def test_explore_complete_reject_keeps_explore_phase_open(pipeline_session):
    """验证 explore complete reject keeps explore phase open 场景。"""
    session_store, task_store, session_id, list_id = pipeline_session
    from career_os.api import chat as chat_mod

    importlib.reload(chat_mod)

    state = session_store.get_state(session_id)
    state["gates"] = {
        "pending": {"name": "explore_complete", "prompt": "确认完成初探？"},
        "flags": {},
    }
    state["explore_closure"] = {
        "gate_name": "explore_complete",
        "required_workers": ["identity", "capability"],
        "worker_done": {"identity": True, "capability": True},
        "gate_pending": True,
    }
    task_store.set_current_phase(list_id, "market")

    chat_mod._apply_pending_gate("还要继续聊聊", state)
    session_store.update_state(session_id, state)

    meta = task_store.get_list_meta(list_id)
    assert meta is not None
    assert meta["current_phase"] == "explore"
    assert state["gates"]["pending"] is None
    assert state.get("explore_gate_confirmed") is False
    assert state["explore_closure"]["gate_pending"] is False
    assert state["explore_closure"]["completed"] is False
    assert state["explore_closure"]["worker_done"] == {
        "identity": False,
        "capability": False,
    }


def test_jd_continue_gate_confirm_dispatches_opportunity(pipeline_session):
    """验证 jd continue gate confirm dispatches opportunity 场景。"""
    session_store, task_store, session_id, list_id = pipeline_session
    from career_os.api import chat as chat_mod

    importlib.reload(chat_mod)

    task_store.set_current_phase(list_id, "jd_analysis")
    state = session_store.get_state(session_id)
    state["explore_gate_confirmed"] = True
    state["gates"] = {
        "pending": {
            "name": "jd_continue_despite_not_recommended",
            "prompt": "当前 JD 不推荐，是否仍要继续？",
        },
        "flags": {"explore_gate_confirmed": True},
    }

    pending = chat_mod._apply_pending_gate("确认继续", state)

    meta = task_store.get_list_meta(list_id)
    assert meta is not None
    assert meta["current_phase"] == "jd_analysis"
    assert state["gates"]["pending"] is None
    assert pending == ["opportunity"]


def test_explore_repeat_accept_uses_global_intake_baseline(pipeline_session):
    """验证 explore repeat accept uses global intake baseline 场景。"""
    session_store, _task_store, session_id, _list_id = pipeline_session
    from career_os.api import chat as chat_mod
    from career_os.platform.store.profile import ProfileStore

    importlib.reload(chat_mod)

    ProfileStore().patch(
        [
            {
                "path": "exploration.intake",
                "value": {
                    "submitted_at": "2026-06-07T08:17:13.872776+00:00",
                    "resume_text": "张三简历",
                    "resolved_fields": {"years_of_experience": "3年"},
                    "pending_fields": [],
                },
                "op": "set",
            }
        ]
    )

    state = session_store.get_state(session_id)
    state["gates"] = {
        "pending": {"name": "explore_repeat", "prompt": "是否再次初探？"},
        "flags": {},
    }

    chat_mod._apply_pending_gate("需要再次初探", state)

    flags = (state.get("gates") or {}).get("flags") or {}
    assert flags["explore_repeat_baseline_at"] == "2026-06-07T08:17:13.872776+00:00"
    assert state["explore_intake_blocked"] is True


def test_explore_repeat_reject_advances_phase_from_prior(pipeline_session):
    """验证 explore repeat reject advances phase from prior 场景。"""
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
