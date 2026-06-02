import json

from career_os.agents.lc.coordinator_llm import (
    build_synthesis_messages,
    chat_only_synthesis_draft,
)
from career_os.harness.explore_closure import PHASE_SEGMENT_COMPLETE


def test_build_synthesis_includes_pipeline_phase(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import importlib

    import career_os.config as config_mod
    import career_os.platform.pipeline_template as pipeline_mod
    import career_os.platform.store.session as session_mod
    import career_os.platform.store.task as task_mod

    importlib.reload(config_mod)
    monkeypatch.setattr(config_mod.settings, "data_dir", str(tmp_path))
    importlib.reload(session_mod)
    importlib.reload(task_mod)
    importlib.reload(pipeline_mod)

    session_id = session_mod.SessionStore().create_session()
    list_id = pipeline_mod.instantiate_pipeline_for_session(session_id)
    assert isinstance(list_id, str)
    task_mod.TaskStore().set_current_phase(list_id, "jd_analysis")

    session_state = {
        "list_type": "pipeline",
        "list_id": list_id,
        "explore_gate_confirmed": True,
        "prior_results": {
            "market": {"phase_status": PHASE_SEGMENT_COMPLETE},
        },
        "gates": {"flags": {}},
    }
    _, user = build_synthesis_messages(
        "我们当前在什么阶段？",
        chat_only_synthesis_draft(session_state),
        session_state,
        None,
    )
    payload = json.loads(user)
    assert payload["pipeline"]["current_phase"] == "jd_analysis"
    assert payload["session_activity"]["headline"] is not None
    assert "JD" in payload["session_activity"]["headline"]


def test_chat_only_draft_mentions_jd_when_phase_migrated(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import importlib

    import career_os.config as config_mod
    import career_os.platform.pipeline_template as pipeline_mod
    import career_os.platform.store.session as session_mod
    import career_os.platform.store.task as task_mod

    importlib.reload(config_mod)
    monkeypatch.setattr(config_mod.settings, "data_dir", str(tmp_path))
    importlib.reload(session_mod)
    importlib.reload(task_mod)
    importlib.reload(pipeline_mod)

    session_id = session_mod.SessionStore().create_session()
    list_id = pipeline_mod.instantiate_pipeline_for_session(session_id)
    assert isinstance(list_id, str)
    task_mod.TaskStore().set_current_phase(list_id, "jd_analysis")

    session_state = {
        "list_type": "pipeline",
        "list_id": list_id,
        "explore_gate_confirmed": True,
        "explore_closure": {"completed": True},
        "gates": {"flags": {"explore_repeat_declined": True}},
        "prior_results": {
            "market": {"user_visible_summary": "市场"},
            "opportunity": {"user_visible_summary": "JD"},
        },
    }
    draft = chat_only_synthesis_draft(session_state)
    assert "jd_analysis" in draft
    assert "不得声称仍在职业初探" in draft
