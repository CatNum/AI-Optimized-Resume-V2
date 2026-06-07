from career_os.agents.graphs.coordinator import run_coordinator_turn
from career_os.harness.explore_closure import PHASE_IN_PROGRESS, init_explore_closure
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


def test_current_session_intake_continues_explore_even_when_repeat_flag_stale(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import importlib

    import career_os.config as config_mod
    import career_os.platform.store.profile as profile_mod

    importlib.reload(config_mod)
    importlib.reload(profile_mod)

    harness = Harness()
    calls: list[str] = []
    submitted_at = "2026-06-07T07:46:23Z"

    def runner(worker_id, goal, session_state, context):
        calls.append(worker_id)
        return {
            "worker_id": worker_id,
            "status": "completed",
            "structured_output": {
                "user_visible_summary": "先聊聊你转向 AI Agent 开发最看重的动机是什么？",
                "phase_status": PHASE_IN_PROGRESS,
            },
        }

    state = run_coordinator_turn(
        harness,
        session_id="sess_current_intake",
        session_state={
            "session_id": "sess_current_intake",
            "prior_results": {},
            "gates": {
                "flags": {
                    "explore_repeat_accepted": True,
                    "explore_repeat_baseline_at": submitted_at,
                }
            },
            "list_type": "pipeline",
            "explore_intake_blocked": True,
            "intake_status": {"submitted_at": submitted_at, "pending_fields": []},
            "explore_closure": init_explore_closure(),
        },
        user_message="深入初探",
        pending_workers=[],
        worker_runner=runner,
    )

    assert calls == ["identity"]
    assert state["session_state"].get("explore_intake_blocked") is None
    assert state["session_state"]["explore_closure"]["worker_done"]["identity"] is False
