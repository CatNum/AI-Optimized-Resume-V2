from career_os.agents.graphs.coordinator import run_coordinator_turn
from career_os.agents.lc import coordinator_llm as coordinator_llm_mod
from career_os.agents.lc.coordinator_llm import (
    analyze_workers,
    fallback_analyze_workers,
    is_small_talk,
    normalize_analyze_result,
)
from career_os.harness.executor import Harness
from career_os.platform.worker.registry import WorkerRegistry
from tests.conftest import explore_repeat_cleared_gates


def test_is_small_talk():
    assert is_small_talk("你好")
    assert is_small_talk("  你好吗！ ")
    assert not is_small_talk("请评估这个 JD")


def test_normalize_filters_market_on_explore_phase():
    allowed = {"identity", "capability", "market", "opportunity"}
    result = normalize_analyze_result(
        {
            "workers": ["market", "opportunity"],
            "list_type": "pipeline",
            "pipeline_phase": "explore",
        },
        allowed,
        {"list_type": "pipeline"},
    )
    assert result["workers"] == []
    assert result.get("list_type") == "pipeline"


def test_fallback_greeting_returns_empty_workers():
    result = fallback_analyze_workers("你好", {"prior_results": {}, "list_type": "pipeline"})
    assert result == {"workers": []}


def test_fallback_explore_returns_pipeline_phase(
    monkeypatch, tmp_path, explore_intake_profile
):
    result = fallback_analyze_workers(
        "帮我理清职业方向",
        {
            "prior_results": {},
            "list_type": "pipeline",
            "gates": explore_repeat_cleared_gates(),
        },
    )
    assert result is not None
    assert result.get("list_type") == "pipeline"
    assert result.get("pipeline_phase") == "explore"
    assert "identity" in result.get("workers") or "capability" in result.get("workers")


def test_analyze_workers_sanitizes_llm_mismatch(monkeypatch, explore_intake_profile):
    monkeypatch.setattr(coordinator_llm_mod.lc_client, "llm_enabled", lambda: True)
    monkeypatch.setattr(
        coordinator_llm_mod.lc_client,
        "invoke_json",
        lambda system, user, role: {
            "workers": ["market", "opportunity"],
            "list_type": "explore",
        },
    )
    index = WorkerRegistry().get_worker_index()
    result = analyze_workers(
        "你好",
        {"prior_results": {}, "list_type": "pipeline", "gates": explore_repeat_cleared_gates()},
        index,
    )
    assert result == {"workers": []}


def test_coordinator_hello_does_not_delegate(monkeypatch):
    monkeypatch.setattr(coordinator_llm_mod.lc_client, "llm_enabled", lambda: True)
    monkeypatch.setattr(
        coordinator_llm_mod.lc_client,
        "invoke_json",
        lambda system, user, role: {"workers": ["market"], "list_type": "explore"},
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
        session_id="sess_hello",
        session_state={"prior_results": {}, "gates": {"flags": {}}, "list_type": "pipeline"},
        user_message="你好",
        pending_workers=[],
        worker_runner=runner,
    )

    assert calls == []
    assert state["delegate_count"] == 0
    draft = state.get("synthesis_draft") or ""
    assert "引导" in draft
    assert "职业" in draft


def test_coordinator_jd_still_delegates(jd_ready_profile, monkeypatch):
    monkeypatch.setattr(coordinator_llm_mod.lc_client, "llm_enabled", lambda: True)
    monkeypatch.setattr(
        coordinator_llm_mod.lc_client,
        "invoke_json",
        lambda system, user, role: {
            "workers": ["market", "opportunity"],
            "list_type": "jd",
        },
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
        session_id="sess_jd",
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
    assert state["session_state"]["list_type"] == "pipeline"
