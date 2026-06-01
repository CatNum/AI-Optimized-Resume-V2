import importlib

from career_os.harness.jd_change import apply_jd_fingerprint_change, jd_fingerprint
from career_os.harness.pipeline_gates import set_explore_gate_confirmed
from career_os.platform.pipeline_template import instantiate_pipeline_for_session


def test_jd_fingerprint_change(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import career_os.config as config_mod
    import career_os.platform.store.session as session_mod
    import career_os.platform.store.task as task_mod

    importlib.reload(config_mod)
    importlib.reload(session_mod)
    importlib.reload(task_mod)

    session_id = session_mod.SessionStore().create_session()
    list_id = instantiate_pipeline_for_session(session_id)
    assert isinstance(list_id, str)
    state = session_mod.SessionStore().get_state(session_id)
    set_explore_gate_confirmed(state, True)
    task_mod.TaskStore().set_current_phase(list_id, "resume_strategy")

    fp1 = jd_fingerprint("JD-A content")
    fp2 = jd_fingerprint("JD-B content")
    assert fp1 != fp2

    r1 = apply_jd_fingerprint_change(session_id, list_id, fp1, state)
    assert isinstance(r1, dict)
    meta = task_mod.TaskStore().get_list_meta(list_id)
    assert meta["related_jd_fingerprint"] == fp1
    assert meta["current_phase"] == "jd_analysis"

    r2 = apply_jd_fingerprint_change(session_id, list_id, fp2, state)
    assert isinstance(r2, dict)
    assert not r2.get("unchanged")
