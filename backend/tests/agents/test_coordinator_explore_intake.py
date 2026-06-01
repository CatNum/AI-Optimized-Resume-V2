from career_os.agents.graphs.coordinator import run_coordinator_turn
from career_os.harness.executor import Harness


def test_explore_intake_blocked_skips_delegate(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import importlib

    import career_os.config as config_mod
    import career_os.platform.store.profile as profile_mod

    importlib.reload(config_mod)
    importlib.reload(profile_mod)

    harness = Harness()
    calls: list[str] = []

    def runner(worker_id, goal, session_state, context):
        calls.append(worker_id)
        return {"worker_id": worker_id, "status": "completed", "structured_output": {}}

    state = run_coordinator_turn(
        harness,
        session_id="sess_intake",
        session_state={
            "prior_results": {},
            "gates": {"flags": {}},
            "list_type": "pipeline",
        },
        user_message="帮我理清职业方向",
        pending_workers=["identity", "capability"],
        worker_runner=runner,
    )

    assert calls == []
    assert state["session_state"].get("explore_intake_blocked") is True
    draft = state.get("synthesis_draft") or ""
    assert "初探信息表" in draft or "简历" in draft
