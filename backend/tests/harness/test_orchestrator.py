from datetime import UTC, datetime, timedelta

import pytest

from career_os.harness.errors import HarnessError
from career_os.harness.orchestrator import ChatOrchestrator


@pytest.fixture
def orchestrator():
    return ChatOrchestrator()


def test_chat_in_progress(orchestrator):
    session_id = "sess_1"
    state = {"last_activity_at": datetime.now(UTC).isoformat()}
    meta = {"trimmed": False, "usage_ratio": 0.1}
    first = orchestrator.begin_chat(session_id, state, meta)
    assert first["session_id"] == session_id
    second = orchestrator.begin_chat(session_id, state, meta)
    assert isinstance(second, HarnessError)
    assert second.code == "chat_in_progress"
    orchestrator.end_chat(session_id)


def test_session_expired(orchestrator):
    old = (datetime.now(UTC) - timedelta(hours=25)).isoformat()
    state = {"last_activity_at": old}
    result = orchestrator.begin_chat("sess_exp", state, {})
    assert isinstance(result, HarnessError)
    assert result.code == "session_expired"


def test_recommend_new_session_near_limit(orchestrator):
    state = {"last_activity_at": datetime.now(UTC).isoformat()}
    meta = {
        "trimmed": False,
        "usage_ratio": 0.96,
        "message_count": 38,
        "max_messages": 40,
        "token_count": 100,
        "max_tokens": 12000,
    }
    result = orchestrator.begin_chat("sess_near", state, meta)
    assert result["recommend_new_session"] is True
    assert "history_notice" in result
    orchestrator.end_chat("sess_near")


def test_no_recommend_at_low_usage(orchestrator):
    state = {"last_activity_at": datetime.now(UTC).isoformat()}
    meta = {"trimmed": False, "usage_ratio": 0.1, "message_count": 4, "max_messages": 40}
    result = orchestrator.begin_chat("sess_low", state, meta)
    assert result["recommend_new_session"] is False
    orchestrator.end_chat("sess_low")


def test_recommend_new_session_on_trim(orchestrator):
    state = {"last_activity_at": datetime.now(UTC).isoformat()}
    meta = {"trimmed": True, "usage_ratio": 0.5}
    result = orchestrator.begin_chat("sess_trim", state, meta)
    assert result["recommend_new_session"] is False
    orchestrator.end_chat("sess_trim")
