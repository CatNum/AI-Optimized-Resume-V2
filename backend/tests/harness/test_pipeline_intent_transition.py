import importlib
import json

import pytest

import career_os.harness.micro_classifier as classifier_mod
from career_os.harness.pipeline_jd_context import has_jd_context
from career_os.harness.pipeline_intent_transition import (
    apply_intent_phase_transition,
    resolve_intent_phase_transition,
)
from career_os.harness.pipeline_phase_transition import phase_after_worker_segment_complete
from career_os.harness.explore_closure import PHASE_SEGMENT_COMPLETE
from career_os.harness.pipeline_routing import get_current_phase, pipeline_fallback_workers
from career_os.platform.pipeline_template import instantiate_pipeline_for_session
from career_os.platform.store import task as task_mod


@pytest.fixture
def pipeline_env(tmp_path, monkeypatch, jd_ready_profile):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import career_os.config as config_mod
    import career_os.platform.store.profile as profile_mod
    import career_os.platform.store.task as task_store_mod
    import career_os.harness.pipeline_routing as routing_mod
    import career_os.harness.pipeline_intent_transition as intent_mod

    importlib.reload(config_mod)
    importlib.reload(profile_mod)
    importlib.reload(task_store_mod)
    importlib.reload(routing_mod)
    importlib.reload(intent_mod)
    return tmp_path


def _session_state(list_id: str, phase: str, **extra) -> dict:
    state = {
        "list_type": "pipeline",
        "list_id": list_id,
        "explore_gate_confirmed": True,
        "gates": {"flags": {"explore_gate_confirmed": True}},
        "prior_results": {
            "market": {"user_visible_summary": "市场"},
            "opportunity": {
                "recommendation": "not_recommended",
                "user_visible_summary": "JD 评估",
            },
        },
        **extra,
    }
    task_mod.TaskStore().set_current_phase(list_id, phase)
    return state


def _mock_classifier(monkeypatch, target_phase: str):
    monkeypatch.setattr(classifier_mod, "llm_enabled", lambda: True)
    monkeypatch.setattr(
        classifier_mod,
        "invoke_json",
        lambda system, user, role, temperature=0.1: {
            "target_phase": target_phase,
            "confidence": 0.95,
            "reason": f"test:{target_phase}",
        },
    )


def test_has_jd_context_from_prior(pipeline_env):
    state = {"list_id": "list_x", "prior_results": {"opportunity": {}}}
    assert has_jd_context(state, "你好")


def test_jd_analysis_to_resume_strategy_b(pipeline_env):
    session_id = "sess_intent01"
    list_id = instantiate_pipeline_for_session(session_id)
    state = _session_state(list_id, "jd_analysis")
    msg = "告诉我如何按照这个 jd 进行简历优化，简历优化策略是什么？"
    resolved = resolve_intent_phase_transition(msg, state)
    assert resolved["to_phase"] == "resume_strategy"
    assert resolved["rule_id"] == "intent_resume_strategy"

    result = apply_intent_phase_transition(msg, state)
    assert result["applied"] is True
    meta = task_mod.TaskStore().get_list_meta(list_id)
    assert meta["current_phase"] == "resume_strategy"
    assert state["intent_suggested_workers"] == ["strategy"]


def test_no_intent_when_gate_pending(pipeline_env):
    session_id = "sess_intent02"
    list_id = instantiate_pipeline_for_session(session_id)
    state = _session_state(
        list_id,
        "jd_analysis",
        gates={"pending": {"name": "jd_continue_despite_not_recommended", "prompt": "?"}, "flags": {}},
    )
    resolved = resolve_intent_phase_transition("继续", state)
    assert resolved["to_phase"] is None


def test_chat_only_intent_does_not_transition(pipeline_env):
    session_id = "sess_intent_chat_only"
    list_id = instantiate_pipeline_for_session(session_id)
    state = _session_state(
        list_id,
        "jd_analysis",
        gates={"flags": {"explore_gate_confirmed": True}},
    )
    resolved = resolve_intent_phase_transition(
        "进入随便聊聊状态，不分配任何工作", state
    )
    assert resolved["to_phase"] is None


def test_intent_suggested_workers_fallback(pipeline_env):
    session_id = "sess_intent03"
    list_id = instantiate_pipeline_for_session(session_id)
    state = _session_state(list_id, "resume_strategy")
    state["intent_suggested_workers"] = ["strategy"]
    fb = pipeline_fallback_workers("帮我制定策略", state)
    assert fb is not None
    assert fb.get("workers") == ["strategy"]
    assert "intent_suggested_workers" not in state


def test_phase_after_strategy_complete():
    assert (
        phase_after_worker_segment_complete(
            "strategy", {"phase_status": PHASE_SEGMENT_COMPLETE}
        )
        == "resume_strategy"
    )


def test_match_rule_ids_strategy_message():
    from career_os.harness.micro_classifier_rules import match_pipeline_intent_rule_ids

    ids = match_pipeline_intent_rule_ids("简历优化策略是什么")
    assert "intent_resume_strategy" in ids


def test_declare_career_agent_project_advances_phase(pipeline_env):
    session_id = "sess_intent05"
    list_id = instantiate_pipeline_for_session(session_id)
    state = _session_state(list_id, "jd_analysis")
    msg = "我做的是 职业规划 Agent"
    result = apply_intent_phase_transition(msg, state)
    assert result["applied"] is True
    assert result["to_phase"] == "resume_strategy"
    assert result["rule_id"] == "intent_declare_agent_project"


def test_build_phase_draft_resume_strategy_no_chat_only(pipeline_env):
    from career_os.agents.lc.coordinator_llm import build_phase_synthesis_draft

    session_id = "sess_intent04"
    list_id = instantiate_pipeline_for_session(session_id)
    state = _session_state(list_id, "resume_strategy")
    draft = build_phase_synthesis_draft("我在做职业规划类 Agent", state)
    assert "resume_strategy" in draft
    assert "禁止复读" in draft
    assert "寒暄" not in draft


def test_nl_jump_to_explore_from_market(pipeline_env, monkeypatch):
    _mock_classifier(monkeypatch, "explore")
    session_id = "sess_jump_explore"
    list_id = instantiate_pipeline_for_session(session_id)
    state = _session_state(list_id, "market")

    msg = "转换到初探流程，继续聊身份与价值观"
    resolved = resolve_intent_phase_transition(msg, state)
    assert resolved["to_phase"] == "explore"
    assert resolved["source"] == "classifier"

    result = apply_intent_phase_transition(msg, state)
    assert result["applied"] is True
    meta = task_mod.TaskStore().get_list_meta(list_id)
    assert meta["current_phase"] == "explore"
    assert state["intent_suggested_workers"] == ["identity", "capability"]


def test_nl_jump_to_market_from_jd_analysis(pipeline_env, monkeypatch):
    _mock_classifier(monkeypatch, "market")
    session_id = "sess_jump_market"
    list_id = instantiate_pipeline_for_session(session_id)
    state = _session_state(list_id, "jd_analysis")

    msg = "把关注重点切到外部机会，继续往前看"
    resolved = resolve_intent_phase_transition(msg, state)
    assert resolved["to_phase"] == "market"
    assert resolved["source"] == "classifier"

    result = apply_intent_phase_transition(msg, state)
    assert result["applied"] is True
    meta = task_mod.TaskStore().get_list_meta(list_id)
    assert meta["current_phase"] == "market"
    assert state["intent_suggested_workers"] == ["market"]


def test_nl_jump_to_explore_ignores_explore_gate(pipeline_env, monkeypatch):
    _mock_classifier(monkeypatch, "explore")
    session_id = "sess_jump_explore_no_gate"
    list_id = instantiate_pipeline_for_session(session_id)
    state = _session_state(
        list_id,
        "market",
        explore_gate_confirmed=False,
        explore_closure={"completed": False},
        gates={"flags": {}},
    )

    result = apply_intent_phase_transition("转换到初探流程", state)
    assert result["applied"] is True
    meta = task_mod.TaskStore().get_list_meta(list_id)
    assert meta["current_phase"] == "explore"


def test_nl_jump_to_market_requires_explore_complete(pipeline_env, monkeypatch):
    _mock_classifier(monkeypatch, "market")
    session_id = "sess_jump_market_blocked"
    list_id = instantiate_pipeline_for_session(session_id)
    state = _session_state(
        list_id,
        "jd_analysis",
        explore_gate_confirmed=False,
        explore_closure={"completed": False},
        gates={"flags": {}},
    )

    result = apply_intent_phase_transition("把关注重点切到外部机会，继续往前看", state)
    assert result["applied"] is False
    assert result.get("error_code") == "explore_gate_required"
    meta = task_mod.TaskStore().get_list_meta(list_id)
    assert meta["current_phase"] == "jd_analysis"


def test_nl_jump_blocks_gate_pending(pipeline_env, monkeypatch):
    _mock_classifier(monkeypatch, "explore")
    session_id = "sess_jump_gate"
    list_id = instantiate_pipeline_for_session(session_id)
    state = _session_state(
        list_id,
        "market",
        gates={"pending": {"name": "explore_complete", "prompt": "?"}, "flags": {}},
    )

    resolved = resolve_intent_phase_transition("转换到初探流程", state)
    assert resolved["to_phase"] is None


def test_vague_followup_does_not_transition_to_any_jump_phase(pipeline_env, monkeypatch):
    _mock_classifier(monkeypatch, "market")
    session_id = "sess_jump_vague"
    list_id = instantiate_pipeline_for_session(session_id)
    state = _session_state(list_id, "market")

    resolved = resolve_intent_phase_transition("继续聊聊", state)
    assert resolved["to_phase"] is None
