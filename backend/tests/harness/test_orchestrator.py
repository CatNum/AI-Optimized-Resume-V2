from datetime import UTC, datetime

import pytest

from career_os.harness.errors import HarnessError
from career_os.harness.orchestrator import ChatOrchestrator


@pytest.fixture
def orchestrator():
    """构造测试辅助数据。"""
    return ChatOrchestrator()


def test_chat_in_progress(orchestrator):
    """验证 chat in progress 场景。"""
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
    """验证 idle session can begin chat 场景。"""
    old = "2026-06-01T10:28:43.542993+00:00"
    state = {"last_activity_at": old}
    result = orchestrator.begin_chat("sess_old", state, {})
    assert result["session_id"] == "sess_old"
    orchestrator.end_chat("sess_old")


def test_recommend_new_session_near_limit(orchestrator):
    """验证 recommend new session near limit 场景。"""
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
    """验证 no recommend at low usage 场景。"""
    state = {"last_activity_at": datetime.now(UTC).isoformat()}
    meta = {"usage_ratio": 0.1, "total_count": 4, "over_limit": False}
    result = orchestrator.begin_chat("sess_low", state, meta)
    assert result["recommend_new_session"] is False
    orchestrator.end_chat("sess_low")


def test_recommend_new_session_on_over_limit(orchestrator):
    """验证 recommend new session on over limit 场景。"""
    state = {"last_activity_at": datetime.now(UTC).isoformat()}
    meta = {"over_limit": True, "usage_ratio": 0.5}
    result = orchestrator.begin_chat("sess_over", state, meta)
    assert result["recommend_new_session"] is True
    orchestrator.end_chat("sess_over")
