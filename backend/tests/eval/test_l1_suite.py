import importlib

import pytest

from career_os.harness.executor import Harness
from career_os.harness.gate import match_gate_intent
from career_os.platform.store.session import SessionStore


@pytest.fixture
def harness(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import career_os.config as config_mod

    importlib.reload(config_mod)
    return Harness()


@pytest.mark.no_llm
def test_profile_patch_whitelist_rejects_asset(harness):
    err = harness.execute_tool(
        "asset",
        "profile_patch",
        {"path": "exploration.summary", "value": "x"},
    )
    assert err.code == "profile_patch_rejected"


@pytest.mark.no_llm
def test_jd_r1_blocks_opportunity(harness, jd_ready_profile):
    err = harness.delegate_worker(
        "coordinator",
        "opportunity",
        "eval",
        {"list_type": "jd", "prior_results": {}, "gates": {"flags": {}}},
    )
    assert err.code == "delegate_blocked"
    assert "JD-B1" in err.message


@pytest.mark.no_llm
def test_explore_gate_intent():
    result = match_gate_intent("确认完成初探")
    assert result["gate_name"] == "explore_complete"
    assert result["intent"] == "confirm"


@pytest.mark.no_llm
def test_load_chat_history_no_trim(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import career_os.config as config_mod
    import career_os.platform.store.session as session_mod

    importlib.reload(config_mod)
    importlib.reload(session_mod)
    store = session_mod.SessionStore()
    sid = store.create_session()
    for i in range(10):
        store.append_message(sid, "user" if i % 2 == 0 else "assistant", f"m{i}")
    loaded, meta = store.load_chat_history(sid)
    assert len(loaded) == 10
    assert "trimmed" not in meta


@pytest.mark.no_llm
def test_b3_worker_no_complete(harness):
    err = harness.execute_tool("identity", "complete_task", {"task_id": "m1"})
    assert err.code == "tool_not_allowed"
