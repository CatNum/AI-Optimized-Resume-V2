from career_os.agents.graphs.coordinator import run_coordinator_turn
from career_os.harness.executor import Harness


def test_synthesize_gate_clarify_pending():
    """验证 synthesize gate clarify pending 场景。"""
    harness = Harness()

    def runner(worker_id, goal, session_state, context):
        """构造测试用 Worker runner。"""
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


def test_chat_only_request_skips_gate_clarify():
    """验证 chat only request skips gate clarify 场景。"""
    harness = Harness()

    def runner(worker_id, goal, session_state, context):
        """构造测试用 Worker runner。"""
        return {"worker_id": worker_id, "status": "completed", "structured_output": {}}

    state = run_coordinator_turn(
        harness,
        session_id="sess_chat_only",
        session_state={
            "prior_results": {},
            "gates": {
                "pending": {
                    "name": "optimize_confirm",
                    "prompt": "是否确认优化？",
                }
            },
            "list_type": "pipeline",
        },
        user_message="进入随便聊聊状态，不分配任何工作，直接给出打招呼话术",
        pending_workers=[],
        worker_runner=runner,
    )
    draft = state.get("synthesis_draft") or ""
    assert "职业初探" in draft or "简历优化" in draft or "JD/岗位评估" in draft
    assert not state["session_state"].get("gate_clarify_pending")
    assert state["session_state"].get("chat_only_requested") is not True
