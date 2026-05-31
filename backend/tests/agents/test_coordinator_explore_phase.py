from typing import Any

import importlib

import pytest

from career_os.agents.graphs.coordinator import run_coordinator_turn
from career_os.agents.lc import coordinator_llm as coordinator_llm_mod
from career_os.agents.lc.coordinator_llm import chat_only_synthesis_draft
from career_os.harness.explore_closure import (
    PHASE_IN_PROGRESS,
    PHASE_SEGMENT_COMPLETE,
    init_explore_closure,
)
from career_os.harness.executor import Harness
from career_os.platform.store.profile import ProfileStore
from tests.conftest import explore_repeat_cleared_gates, seed_explore_intake_profile


@pytest.fixture(autouse=True)
def explore_intake_ready(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import career_os.config as config_mod
    import career_os.platform.store.profile as profile_mod

    importlib.reload(config_mod)
    importlib.reload(profile_mod)
    seed_explore_intake_profile(profile_mod.ProfileStore())


def _next_explore_phase_status(worker_id: str, session_state: dict) -> str:
    prior = (session_state.get("prior_results") or {}).get(worker_id) or {}
    if prior.get("phase_status") == PHASE_IN_PROGRESS:
        return PHASE_SEGMENT_COMPLETE
    return PHASE_IN_PROGRESS


def _explore_runner(worker_id, goal, session_state, context):
    phase_status = _next_explore_phase_status(worker_id, session_state)
    if worker_id == "identity":
        if phase_status == PHASE_IN_PROGRESS:
            return {
                "worker_id": worker_id,
                "status": "completed",
                "structured_output": {
                    "user_visible_summary": (
                        "抛开简历和 JD，如果接下来一年只允许你解决一件和职业相关的事，"
                        "你会选什么？为什么是它而不是别的？"
                    ),
                    "exploration_draft": {"summary": "待补充"},
                    "phase_status": PHASE_IN_PROGRESS,
                    "guidance_options": [
                        {"id": "A", "label": "技术深度", "hint": "做深核心栈"},
                        {"id": "B", "label": "带团队", "hint": "向 Tech Lead 过渡"},
                    ],
                },
            }
        return {
            "worker_id": worker_id,
            "status": "completed",
            "structured_output": {
                "user_visible_summary": "identity done",
                "exploration_draft": {"summary": "ok"},
                "phase_status": PHASE_SEGMENT_COMPLETE,
            },
        }
    if phase_status == PHASE_IN_PROGRESS:
        return {
            "worker_id": worker_id,
            "status": "completed",
            "structured_output": {
                "user_visible_summary": (
                    "你觉得哪一段项目或工作，最值得单独拿出来讲一讲？"
                ),
                "bank_delta_summary": "待补充",
                "phase_status": PHASE_IN_PROGRESS,
                "guidance_options": [
                    {"id": "A", "label": "数据治理平台", "hint": "平台化或数据流动相关"},
                    {"id": "B", "label": "安全产品后端", "hint": "BAS 或攻防仿真场景"},
                ],
            },
        }
    return {
        "worker_id": worker_id,
        "status": "completed",
        "structured_output": {
            "user_visible_summary": "capability done",
            "bank_delta_summary": "delta",
            "phase_status": PHASE_SEGMENT_COMPLETE,
        },
    }


def test_explore_in_progress_stops_delegate_chain():
    harness = Harness()
    calls: list[str] = []

    def runner(worker_id, goal, session_state, context):
        calls.append(worker_id)
        return _explore_runner(worker_id, goal, session_state, context)

    state = run_coordinator_turn(
        harness,
        session_id="sess_phase",
        session_state={
            "session_id": "sess_phase",
            "list_type": "explore",
            "prior_results": {},
            "gates": explore_repeat_cleared_gates(),
            "explore_closure": init_explore_closure(),
        },
        user_message="帮我理清职业方向",
        pending_workers=["identity", "capability"],
        worker_runner=runner,
    )

    assert calls == ["identity"]
    assert state["stop_delegate"] is True
    assert state["session_state"]["explore_closure"]["worker_done"]["identity"] is False
    assert state["session_state"].get("gates", {}).get("pending") is None


def test_explore_segment_complete_can_chain_next_worker():
    harness = Harness()
    calls: list[str] = []

    def runner(worker_id, goal, session_state, context):
        calls.append(worker_id)
        if worker_id == "identity":
            return {
                "worker_id": worker_id,
                "status": "completed",
                "structured_output": {
                    "user_visible_summary": "identity done",
                    "exploration_draft": {"summary": "ok"},
                    "phase_status": PHASE_SEGMENT_COMPLETE,
                },
            }
        return _explore_runner(worker_id, goal, session_state, context)

    state = run_coordinator_turn(
        harness,
        session_id="sess_chain",
        session_state={
            "session_id": "sess_chain",
            "list_type": "explore",
            "prior_results": {},
            "gates": explore_repeat_cleared_gates(),
            "explore_closure": init_explore_closure(),
        },
        user_message="继续",
        pending_workers=["identity", "capability"],
        worker_runner=runner,
    )

    assert calls == ["identity", "capability"]
    assert state["session_state"]["explore_closure"]["worker_done"]["identity"] is True
    assert state["session_state"]["explore_closure"]["worker_done"]["capability"] is False
    assert state["stop_delegate"] is True


def test_explore_continuation_when_llm_returns_empty_workers(monkeypatch):
    monkeypatch.setattr(coordinator_llm_mod, "llm_enabled", lambda: True)
    monkeypatch.setattr(
        coordinator_llm_mod,
        "invoke_json",
        lambda system, user, role: {"workers": []},
    )

    harness = Harness()
    calls: list[str] = []

    def runner(worker_id, goal, session_state, context):
        calls.append(worker_id)
        return {
            "worker_id": worker_id,
            "status": "completed",
            "structured_output": {
                "user_visible_summary": (
                    "「和职业有关的事」指的是你接下来一年最想推进的方向，"
                    "我可以举几个例子供你参考…"
                ),
                "exploration_draft": {"summary": "待补充"},
                "phase_status": PHASE_IN_PROGRESS,
            },
        }

    state = run_coordinator_turn(
        harness,
        session_id="sess_cont",
        session_state={
            "session_id": "sess_cont",
            "list_type": "explore",
            "prior_results": {
                "identity": {
                    "phase_status": PHASE_IN_PROGRESS,
                    "user_visible_summary": "一年只允许你解决一件和职业相关的事，你会选什么？",
                }
            },
            "gates": explore_repeat_cleared_gates(),
            "explore_closure": init_explore_closure(),
        },
        user_message="你能给我一些选项吗，你说的和职业有关的事指的是什么？",
        pending_workers=[],
        worker_runner=runner,
    )

    assert calls == ["identity"]
    assert state.get("synthesis_draft") != chat_only_synthesis_draft()
    assert "和职业有关的事" in (state.get("synthesis_draft") or "")


def test_identity_first_question_offers_options_without_listing_them():
    harness = Harness()

    state = run_coordinator_turn(
        harness,
        session_id="sess_offer",
        session_state={
            "session_id": "sess_offer",
            "list_type": "explore",
            "prior_results": {},
            "gates": explore_repeat_cleared_gates(),
            "explore_closure": init_explore_closure(),
        },
        user_message="帮我理清职业方向",
        pending_workers=["identity"],
        worker_runner=_explore_runner,
    )

    draft = state.get("synthesis_draft") or ""
    guidance = state["session_state"].get("explore_guidance") or {}
    assert guidance.get("options")
    assert guidance.get("revealed") is False
    assert "给我一些选项" in draft
    assert "A." not in draft


def test_capability_first_question_offers_options_without_listing_them():
    harness = Harness()
    calls: list[str] = []

    def runner(worker_id, goal, session_state, context):
        calls.append(worker_id)
        return _explore_runner(worker_id, goal, session_state, context)

    state = run_coordinator_turn(
        harness,
        session_id="sess_cap_offer",
        session_state={
            "session_id": "sess_cap_offer",
            "list_type": "explore",
            "prior_results": {
                "identity": {"phase_status": PHASE_SEGMENT_COMPLETE},
            },
            "gates": explore_repeat_cleared_gates(),
            "explore_closure": {
                **init_explore_closure(),
                "worker_done": {"identity": True, "capability": False},
            },
        },
        user_message="继续补充经历",
        pending_workers=["capability"],
        worker_runner=runner,
    )

    draft = state.get("synthesis_draft") or ""
    guidance = state["session_state"].get("explore_guidance") or {}
    assert calls == ["capability"]
    assert guidance.get("worker_id") == "capability"
    assert guidance.get("options")
    assert guidance.get("revealed") is False
    assert "给我一些选项" in draft
    assert "A." not in draft


def test_explore_guidance_reveal_skips_worker_when_options_pending(monkeypatch):
    monkeypatch.setattr(coordinator_llm_mod, "llm_enabled", lambda: True)
    monkeypatch.setattr(
        coordinator_llm_mod,
        "invoke_json",
        lambda system, user, role: {"workers": []},
    )

    harness = Harness()
    calls: list[str] = []

    def runner(worker_id, goal, session_state, context):
        calls.append(worker_id)
        return {
            "worker_id": worker_id,
            "status": "completed",
            "structured_output": {
                "user_visible_summary": "不应走到这里",
                "exploration_draft": {"summary": "x"},
                "phase_status": PHASE_IN_PROGRESS,
            },
        }

    state = run_coordinator_turn(
        harness,
        session_id="sess_reveal",
        session_state={
            "session_id": "sess_reveal",
            "list_type": "explore",
            "prior_results": {
                "identity": {
                    "phase_status": PHASE_IN_PROGRESS,
                    "user_visible_summary": "一年只允许你解决一件职业相关的事，你会选什么？",
                }
            },
            "explore_guidance": {
                "worker_id": "identity",
                "question": "一年只允许你解决一件职业相关的事，你会选什么？",
                "options": [
                    {"id": "A", "label": "技术深度", "hint": "做深核心栈"},
                    {"id": "B", "label": "业务视角", "hint": "补产品 sense"},
                ],
                "revealed": False,
            },
            "gates": explore_repeat_cleared_gates(),
            "explore_closure": init_explore_closure(),
        },
        user_message="你能给我一些选项吗？",
        pending_workers=[],
        worker_runner=runner,
    )

    assert calls == []
    draft = state.get("synthesis_draft") or ""
    assert "A. 技术深度" in draft
    assert state["session_state"]["explore_guidance"]["revealed"] is True
