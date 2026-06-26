import importlib

import pytest

from career_os.agents.graphs.coordinator import run_coordinator_turn
from career_os.agents.graphs.workers.base import build_stub_worker_runner
from career_os.harness.executor import Harness
from career_os.platform.store.profile import ProfileStore
from tests.conftest import seed_jd_ready_profile


def test_gate_prompt_stops_delegate_chain_c3(jd_ready_profile):
    """test_gate_prompt_stops_delegate_chain_c3（测试 gate prompt stops delegate chain c3）的函数说明。

    jd_ready_profile（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    harness = Harness()

    def runner(worker_id, goal, session_state, context):
        """runner（runner）的函数说明。

        worker_id（参数）、goal（参数）、session_state（参数）、context（参数）用于向该函数传入运行所需的数据。

        返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
        if worker_id == "market":
            return {
                "worker_id": worker_id,
                "status": "completed",
                "structured_output": {
                    "user_visible_summary": "市场调研完成",
                    "gate_prompt": {
                        "name": "jd_continue_despite_not_recommended",
                        "prompt": "是否仍要继续？",
                    },
                },
            }
        return {
            "worker_id": worker_id,
            "status": "completed",
            "structured_output": {"user_visible_summary": "不应执行"},
        }

    state = run_coordinator_turn(
        harness,
        session_id="sess_c3",
        session_state={
            "session_id": "sess_c3",
            "list_type": "pipeline",
            "explore_gate_confirmed": True,
            "prior_results": {},
            "gates": {"flags": {}},
        },
        user_message="评估这个 JD",
        pending_workers=["market", "opportunity"],
        worker_runner=runner,
    )
    assert state["delegate_count"] == 1
    assert state["stop_delegate"] is True
    assert state["session_state"]["gates"]["pending"]["name"] == (
        "jd_continue_despite_not_recommended"
    )


def test_sequential_delegate_without_gate(jd_ready_profile):
    """test_sequential_delegate_without_gate（测试 sequential delegate without gate）的函数说明。

    jd_ready_profile（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
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
            "structured_output": {
                "user_visible_summary": f"{worker_id} done",
                "topics": [{"topic": "cloud", "summary": "growing"}],
            },
        }

    session_state = {
        "session_id": "sess_seq",
        "list_type": "pipeline",
        "explore_gate_confirmed": True,
        "prior_results": {},
        "gates": {"flags": {}},
    }
    state = run_coordinator_turn(
        harness,
        session_id="sess_seq",
        session_state=session_state,
        user_message="评估 JD",
        pending_workers=["market", "opportunity"],
        worker_runner=runner,
    )
    assert calls == ["market", "opportunity"]
    assert state["delegate_count"] == 2
    assert "market" in state["session_state"]["prior_results"]
    assert "opportunity" in state["session_state"]["prior_results"]


def test_worker_index_injected():
    """test_worker_index_injected（测试 worker index injected）的函数说明。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    harness = Harness()
    runner = build_stub_worker_runner({})
    state = run_coordinator_turn(
        harness,
        session_id="sess_idx",
        session_state={"prior_results": {}, "gates": {"flags": {}}},
        user_message="hello",
        pending_workers=[],
        worker_runner=runner,
    )
    assert len(state["worker_index"]) == 7
