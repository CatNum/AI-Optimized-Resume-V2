from career_os.agents.graphs.coordinator import run_coordinator_turn
from career_os.harness.executor import Harness


def test_synthesize_gate_clarify_pending():
    """test_synthesize_gate_clarify_pending（测试 synthesize gate clarify pending）的函数说明。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    harness = Harness()

    def runner(worker_id, goal, session_state, context):
        """runner（runner）的函数说明。

        worker_id（参数）、goal（参数）、session_state（参数）、context（参数）用于向该函数传入运行所需的数据。

        返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
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
    """test_chat_only_request_skips_gate_clarify（测试 chat only request skips gate clarify）的函数说明。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    harness = Harness()

    def runner(worker_id, goal, session_state, context):
        """runner（runner）的函数说明。

        worker_id（参数）、goal（参数）、session_state（参数）、context（参数）用于向该函数传入运行所需的数据。

        返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
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
