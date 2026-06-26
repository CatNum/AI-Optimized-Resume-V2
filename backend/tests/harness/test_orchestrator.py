from datetime import UTC, datetime

import pytest

from career_os.harness.errors import HarnessError
from career_os.harness.orchestrator import ChatOrchestrator


@pytest.fixture
def orchestrator():
    """orchestrator（orchestrator）的函数说明。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    return ChatOrchestrator()


def test_chat_in_progress(orchestrator):
    """test_chat_in_progress（测试 chat in progress）的函数说明。

    orchestrator（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    session_id = "sess_1"
    state = {"last_activity_at": datetime.now(UTC).isoformat()}
    meta = {"usage_ratio": 0.1, "over_limit": False}
    first = orchestrator.begin_chat(session_id, state, meta)
    assert first["session_id"] == session_id
    second = orchestrator.begin_chat(session_id, state, meta)
    assert isinstance(second, HarnessError)
    assert second.code == "chat_in_progress"
    orchestrator.end_chat(session_id)


def test_idle_session_can_begin_chat(orchestrator):
    """test_idle_session_can_begin_chat（测试 idle session can begin chat）的函数说明。

    orchestrator（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    old = "2026-06-01T10:28:43.542993+00:00"
    state = {"last_activity_at": old}
    result = orchestrator.begin_chat("sess_old", state, {})
    assert result["session_id"] == "sess_old"
    orchestrator.end_chat("sess_old")


def test_recommend_new_session_near_limit(orchestrator):
    """test_recommend_new_session_near_limit（测试 recommend new session near limit）的函数说明。

    orchestrator（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    state = {"last_activity_at": datetime.now(UTC).isoformat()}
    meta = {
        "usage_ratio": 0.96,
        "total_count": 38,
        "token_count": 100,
        "max_tokens": 12000,
        "over_limit": False,
    }
    result = orchestrator.begin_chat("sess_near", state, meta)
    assert result["recommend_new_session"] is True
    assert "history_notice" in result
    orchestrator.end_chat("sess_near")


def test_no_recommend_at_low_usage(orchestrator):
    """test_no_recommend_at_low_usage（测试 no recommend at low usage）的函数说明。

    orchestrator（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    state = {"last_activity_at": datetime.now(UTC).isoformat()}
    meta = {"usage_ratio": 0.1, "total_count": 4, "over_limit": False}
    result = orchestrator.begin_chat("sess_low", state, meta)
    assert result["recommend_new_session"] is False
    orchestrator.end_chat("sess_low")


def test_recommend_new_session_on_over_limit(orchestrator):
    """test_recommend_new_session_on_over_limit（测试 recommend new session on over limit）的函数说明。

    orchestrator（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    state = {"last_activity_at": datetime.now(UTC).isoformat()}
    meta = {"over_limit": True, "usage_ratio": 0.5}
    result = orchestrator.begin_chat("sess_over", state, meta)
    assert result["recommend_new_session"] is True
    orchestrator.end_chat("sess_over")
