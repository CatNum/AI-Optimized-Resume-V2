import importlib

import pytest

from career_os.agents.graphs.coordinator import run_coordinator_turn
from career_os.agents.lc import coordinator_llm as coordinator_llm_mod
from career_os.harness.executor import Harness
from career_os.platform.trace.writer import TraceWriter


@pytest.fixture
def traced_harness(tmp_path, monkeypatch):
    """traced_harness（traced harness）的函数说明。

    tmp_path（参数）、monkeypatch（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import career_os.config as config_mod
    import career_os.platform.store.profile as profile_mod
    from tests.conftest import seed_jd_ready_profile

    importlib.reload(config_mod)
    importlib.reload(profile_mod)
    seed_jd_ready_profile(profile_mod.ProfileStore())
    writer = TraceWriter(logs_dir=tmp_path / "logs" / "traces")
    return Harness(trace_writer=writer), writer


def test_coordinator_analyze_emits_trace(traced_harness, monkeypatch):
    """test_coordinator_analyze_emits_trace（测试 coordinator analyze emits trace）的函数说明。

    traced_harness（参数）、monkeypatch（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    harness, writer = traced_harness
    monkeypatch.setattr(coordinator_llm_mod.lc_client, "llm_enabled", lambda: True)
    monkeypatch.setattr(coordinator_llm_mod, "check_jd_prerequisites", lambda session_state: (True, None))
    monkeypatch.setattr(
        coordinator_llm_mod.lc_client,
        "invoke_json",
        lambda system, user, role: {"workers": ["market", "opportunity"], "list_type": "jd"},
    )

    def runner(worker_id, goal, session_state, context):
        """runner（runner）的函数说明。

        worker_id（参数）、goal（参数）、session_state（参数）、context（参数）用于向该函数传入运行所需的数据。

        返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
        return {
            "worker_id": worker_id,
            "status": "completed",
            "structured_output": {"user_visible_summary": f"{worker_id} done"},
        }

    run_coordinator_turn(
        harness,
        session_id="sess_coord_trace",
        session_state={
            "prior_results": {},
            "gates": {"flags": {}},
            "list_type": "pipeline",
            "explore_gate_confirmed": True,
        },
        user_message="帮我分析这份 JD",
        pending_workers=[],
        worker_runner=runner,
    )

    analyze_events = [e for e in writer.read_events() if e["event"] == "coordinator.analyze"]
    assert analyze_events
    first = analyze_events[0]
    assert first["detail"]["source"] == "llm"
    assert first["detail"]["workers"] in (["market", "opportunity"], ["opportunity"])
    assert first["detail"]["list_type"] == "pipeline"
    assert "_zh" in first
    assert "LLM 分析 (llm)" in first["_zh"]["detail"]["选型来源"]
    assert "岗位/机会智能体" in first["_zh"]["detail"]["派工队列"]

    queue_events = [e for e in analyze_events if e["detail"]["source"] == "queue"]
    assert isinstance(queue_events, list)
    if queue_events:
        assert queue_events[0]["detail"]["workers"] == ["opportunity"]


def test_coordinator_preset_workers_emits_trace(traced_harness):
    """test_coordinator_preset_workers_emits_trace（测试 coordinator preset workers emits trace）的函数说明。

    traced_harness（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    harness, writer = traced_harness

    def runner(worker_id, goal, session_state, context):
        """runner（runner）的函数说明。

        worker_id（参数）、goal（参数）、session_state（参数）、context（参数）用于向该函数传入运行所需的数据。

        返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
        return {
            "worker_id": worker_id,
            "status": "completed",
            "structured_output": {"user_visible_summary": "done"},
        }

    run_coordinator_turn(
        harness,
        session_id="sess_preset",
        session_state={"prior_results": {}, "gates": {"flags": {"optimize_confirmed": True}}},
        user_message="确认优化",
        pending_workers=["resume", "asset"],
        worker_runner=runner,
    )

    preset = next(
        e for e in writer.read_events() if e.get("event") == "coordinator.analyze"
    )
    assert preset["detail"]["source"] == "preset"
    assert preset["detail"]["workers"] == ["resume", "asset"]
