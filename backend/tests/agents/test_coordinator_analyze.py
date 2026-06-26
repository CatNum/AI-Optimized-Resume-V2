from career_os.agents.graphs.coordinator import run_coordinator_turn
from career_os.agents.lc import coordinator_llm as coordinator_llm_mod
from career_os.harness.executor import Harness
from career_os.platform.worker.registry import WorkerRegistry


def test_analyze_workers_returns_workers_and_pipeline(monkeypatch):
    """test_analyze_workers_returns_workers_and_pipeline（测试 analyze workers returns workers and pipeline）的函数说明。

    monkeypatch（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    monkeypatch.setattr(coordinator_llm_mod.lc_client, "llm_enabled", lambda: True)
    monkeypatch.setattr(coordinator_llm_mod, "check_jd_prerequisites", lambda session_state: (True, None))
    monkeypatch.setattr(
        coordinator_llm_mod.lc_client,
        "invoke_json",
        lambda system, user, role: {"workers": ["market", "opportunity"], "list_type": "jd"},
    )

    index = WorkerRegistry().get_worker_index()
    result = coordinator_llm_mod.analyze_workers(
        "评估这个 JD",
        {
            "prior_results": {},
            "list_type": "pipeline",
            "explore_gate_confirmed": True,
            "explore_closure": {"completed": True},
            "intake_status": {"submitted_at": "2026-05-31T00:00:00Z"},
        },
        index,
    )

    assert result is not None
    assert result["workers"] in (["market", "opportunity"], ["opportunity"])
    assert result["list_type"] == "pipeline"


def test_coordinator_analyze_node_uses_llm_when_pending_empty(jd_ready_profile, monkeypatch):
    """test_coordinator_analyze_node_uses_llm_when_pending_empty（测试 coordinator analyze node uses llm when pending empty）的函数说明。

    jd_ready_profile（参数）、monkeypatch（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    monkeypatch.setattr(coordinator_llm_mod.lc_client, "llm_enabled", lambda: True)
    monkeypatch.setattr(
        coordinator_llm_mod.lc_client,
        "invoke_json",
        lambda system, user, role: {"workers": ["market", "opportunity"], "list_type": "jd"},
    )

    harness = Harness()
    calls: list[str] = []

    def runner(worker_id, goal, session_state, context):
        """runner（runner）的函数说明。

        worker_id（参数）、goal（参数）、session_state（参数）、context（参数）用于向该函数传入运行所需的数据。

        返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
        calls.append(worker_id)
        return {
            "worker_id": worker_id,
            "status": "completed",
            "structured_output": {"user_visible_summary": f"{worker_id} done"},
        }

    state = run_coordinator_turn(
        harness,
        session_id="sess_analyze_llm",
        session_state={
            "prior_results": {},
            "gates": {"flags": {}},
            "list_type": "pipeline",
            "explore_gate_confirmed": True,
            "explore_closure": {"completed": True},
            "intake_status": {"submitted_at": "2026-05-31T00:00:00Z"},
        },
        user_message="帮我分析这份 JD",
        pending_workers=[],
        worker_runner=runner,
    )

    assert calls == []
    assert state["delegate_count"] == 0
    assert state["session_state"]["list_type"] == "pipeline"
