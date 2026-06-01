from career_os.agents.graphs.coordinator import run_coordinator_turn
from career_os.harness.executor import Harness


def test_synthesize_gate_clarify_pending():
    harness = Harness()

    def runner(worker_id, goal, session_state, context):
        return {"worker_id": worker_id, "status": "completed", "structured_output": {}}

    state = run_coordinator_turn(
        harness,
        session_id="sess_clarify",
        session_state={
            "prior_results": {},
            "gates": {
                "pending": {
                    "name": "explore_repeat",
                    "prompt": "您已完成初探，是否需要再次进行？",
                }
            },
            "gate_clarify_pending": True,
            "list_type": "pipeline",
        },
        user_message="随便说说",
        pending_workers=[],
        worker_runner=runner,
    )
    draft = state.get("synthesis_draft") or ""
    assert "再次进行" in draft or "初探" in draft
    assert "没完全理解" in draft
    assert "请回复" in draft
    assert not state["session_state"].get("gate_clarify_pending")
