import importlib

import pytest

from career_os.harness.executor import Harness
from career_os.platform.trace.writer import TraceWriter


@pytest.fixture
def traced_harness(tmp_path, monkeypatch):
    """构造测试用 Harness。"""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import career_os.config as config_mod
    import career_os.platform.store.profile as profile_mod

    importlib.reload(config_mod)
    importlib.reload(profile_mod)
    writer = TraceWriter(logs_dir=tmp_path / "logs" / "traces")
    return Harness(trace_writer=writer), writer


def test_execute_tool_writes_tool_call_event(traced_harness):
    """验证执行工具会写入工具调用事件。"""
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
    event = next(e for e in events if e["event"] == "tool.call")
    assert "_zh" in event
    assert "档案补丁 (profile_patch)" in event["_zh"]["tool_name"]
    assert "身份智能体 (identity)" in event["_zh"]["actor"]
    assert "工具调用 (tool.call)" in event["_zh"]["event"]


def test_trace_zh_summary_for_skill_load(traced_harness):
    """验证 trace 中文摘要针对 Skill 加载的处理符合预期。"""
    _, writer = traced_harness
    writer.emit(
        "skill.load",
        actor="identity",
        tool_name="career-inner-exploration",
        status="ok",
        detail={"mode": "exploration_first", "hash": "abc123"},
    )
    events = writer.read_events()
    event = events[0]
    zh = event["_zh"]
    assert "Skill 加载" in zh["summary"]
    assert "身份智能体 (identity)" in zh["actor"]
    assert "职业初探 Skill (career-inner-exploration)" in zh["tool_name"]
    assert "初探-首次 (exploration_first)" in zh["detail"]["Skill 模式"]


def test_delegate_worker_writes_agent_run_start(traced_harness, jd_ready_profile):
    """验证委派 Worker 会写入智能体运行启动。"""
    harness, writer = traced_harness
    harness.delegate_worker(
        "coordinator",
        "market",
        "research market",
        {
            "list_type": "pipeline",
            "explore_gate_confirmed": True,
            "explore_closure": {"completed": True},
            "prior_results": {},
            "gates": {"flags": {}},
        },
        session_id="sess_delegate",
    )
    events = writer.read_events()
    assert any(
        event["event"] == "agent.run.start" and event["worker_id"] == "market"
        for event in events
    )
