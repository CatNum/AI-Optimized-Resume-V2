from career_os.agents.graphs.coordinator import run_coordinator_turn
from career_os.agents.lc import coordinator_llm as coordinator_llm_mod
from career_os.harness.executor import Harness
from career_os.platform.worker.registry import WorkerRegistry


def test_analyze_workers_returns_workers_and_list_type(monkeypatch):
    monkeypatch.setattr(coordinator_llm_mod, "llm_enabled", lambda: True)
    monkeypatch.setattr(
        coordinator_llm_mod,
        "invoke_json",
        lambda system, user, role: {"workers": ["market", "opportunity"], "list_type": "jd"},
    )

    index = WorkerRegistry().get_worker_index()
    result = coordinator_llm_mod.analyze_workers("评估这个 JD", {"prior_results": {}}, index)

    assert result == {"workers": ["market", "opportunity"], "list_type": "jd"}


def test_coordinator_analyze_node_uses_llm_when_pending_empty(monkeypatch):
    monkeypatch.setattr(coordinator_llm_mod, "llm_enabled", lambda: True)
    monkeypatch.setattr(
        coordinator_llm_mod,
        "invoke_json",
        lambda system, user, role: {"workers": ["market", "opportunity"], "list_type": "jd"},
    )

    harness = Harness()
    calls: list[str] = []

    def runner(worker_id, goal, session_state, context):
        calls.append(worker_id)
        return {
            "worker_id": worker_id,
            "status": "completed",
            "structured_output": {"user_visible_summary": f"{worker_id} done"},
        }

    state = run_coordinator_turn(
        harness,
        session_id="sess_analyze_llm",
        session_state={"prior_results": {}, "gates": {"flags": {}}},
        user_message="帮我分析这份 JD",
        pending_workers=[],
        worker_runner=runner,
    )

    assert calls == ["market", "opportunity"]
    assert state["delegate_count"] == 2
    assert state["session_state"]["list_type"] == "jd"
