import importlib

import pytest

from career_os.harness.executor import Harness
from career_os.platform.trace.writer import TraceWriter


@pytest.fixture
def traced_harness(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import career_os.config as config_mod
    import career_os.platform.store.profile as profile_mod

    importlib.reload(config_mod)
    importlib.reload(profile_mod)
    writer = TraceWriter(logs_dir=tmp_path / "logs" / "traces")
    return Harness(trace_writer=writer), writer


def test_execute_tool_writes_tool_call_event(traced_harness):
    harness, writer = traced_harness
    harness.execute_tool(
        "identity",
        "profile_patch",
        {"path": "exploration.summary", "value": "trace test", "op": "set"},
        session_id="sess_trace",
    )
    events = writer.read_events()
    assert any(
        event["event"] == "tool.call"
        and event["tool_name"] == "profile_patch"
        and event["actor"] == "identity"
        for event in events
    )


def test_delegate_worker_writes_agent_run_start(traced_harness):
    harness, writer = traced_harness
    harness.delegate_worker(
        "coordinator",
        "market",
        "research market",
        {"list_type": "jd", "prior_results": {}, "gates": {"flags": {}}},
        session_id="sess_delegate",
    )
    events = writer.read_events()
    assert any(
        event["event"] == "agent.run.start" and event["worker_id"] == "market"
        for event in events
    )
