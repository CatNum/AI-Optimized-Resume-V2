import importlib

import pytest

from career_os.harness.executor import Harness
from career_os.harness.gate import match_gate_intent
from career_os.platform.store.session import SessionStore


@pytest.fixture
def harness(tmp_path, monkeypatch):
    """harness（harness）的函数说明。

    tmp_path（参数）、monkeypatch（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import career_os.config as config_mod

    importlib.reload(config_mod)
    return Harness()


@pytest.mark.no_llm
def test_profile_patch_whitelist_rejects_asset(harness):
    """test_profile_patch_whitelist_rejects_asset（测试 profile patch whitelist rejects asset）的函数说明。

    harness（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    err = harness.execute_tool(
        "asset",
        "profile_patch",
        {"path": "exploration.summary", "value": "x"},
    )
    assert err.code == "profile_patch_rejected"


@pytest.mark.no_llm
def test_jd_r1_blocks_opportunity(harness, jd_ready_profile):
    """test_jd_r1_blocks_opportunity（测试 jd r1 blocks opportunity）的函数说明。

    harness（参数）、jd_ready_profile（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    err = harness.delegate_worker(
        "coordinator",
        "opportunity",
        "eval",
        {"list_type": "jd", "prior_results": {}, "gates": {"flags": {}}},
    )
    assert err.code == "delegate_blocked"
    assert "JD-R1" in err.message


@pytest.mark.no_llm
def test_explore_gate_intent():
    """test_explore_gate_intent（测试 explore gate intent）的函数说明。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    result = match_gate_intent("确认完成初探")
    assert result["gate_name"] == "explore_complete"
    assert result["intent"] == "confirm"


@pytest.mark.no_llm
def test_load_chat_history_no_trim(tmp_path, monkeypatch):
    """test_load_chat_history_no_trim（测试 load chat history no trim）的函数说明。

    tmp_path（参数）、monkeypatch（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
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
    """test_b3_worker_no_complete（测试 b3 worker no complete）的函数说明。

    harness（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    err = harness.execute_tool("identity", "complete_task", {"task_id": "m1"})
    assert err.code == "tool_not_allowed"
