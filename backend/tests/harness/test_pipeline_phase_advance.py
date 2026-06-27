import importlib

import pytest

from career_os.harness.pipeline_phase_advance import (
    maybe_advance_phase_from_analyze,
    resolve_analyze_target_phase,
)
from career_os.harness.pipeline_routing import enforce_pipeline_phase_rules, get_current_phase
from career_os.platform.pipeline_template import instantiate_pipeline_for_session
from career_os.platform.store import task as task_mod


@pytest.fixture
def pipeline_env(tmp_path, monkeypatch, jd_ready_profile):
    """构造测试环境和基础状态。"""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import career_os.config as config_mod
    import career_os.platform.store.profile as profile_mod
    import career_os.platform.store.task as task_store_mod
    import career_os.harness.pipeline_routing as routing_mod

    importlib.reload(config_mod)
    importlib.reload(profile_mod)
    importlib.reload(task_store_mod)
    importlib.reload(routing_mod)
    return tmp_path


def test_resolve_target_phase_from_workers():
    """验证 resolve target phase from workers 场景。"""
    state = {"list_type": "pipeline", "list_id": "list_x"}
    target = resolve_analyze_target_phase(
        {"workers": ["strategy"], "pipeline_phase": "jd_analysis"},
        state,
    )
    assert target == "resume_strategy"


def test_analyze_advance_jd_to_strategy(pipeline_env):
    """验证 analyze advance jd to strategy 场景。"""
    session_id = "sess_adv01"
    list_id = instantiate_pipeline_for_session(session_id)
    task_mod.TaskStore().set_current_phase(list_id, "jd_analysis")
    state = {
        "list_type": "pipeline",
        "list_id": list_id,
        "explore_gate_confirmed": True,
        "gates": {"flags": {}},
        "prior_results": {"market": {}, "opportunity": {}},
    }
    result = {
        "workers": ["strategy"],
        "pipeline_phase": "resume_strategy",
        "list_type": "pipeline",
    }
    out = enforce_pipeline_phase_rules(
        result, state, "我做的是 职业规划 Agent"
    )
    assert get_current_phase(state) == "resume_strategy"
    assert out.get("workers") == ["strategy"]


def test_analyze_advance_infers_phase_when_only_workers(pipeline_env):
    """验证 analyze advance infers phase when only workers 场景。"""
    session_id = "sess_adv02"
    list_id = instantiate_pipeline_for_session(session_id)
    task_mod.TaskStore().set_current_phase(list_id, "jd_analysis")
    state = {
        "list_type": "pipeline",
        "list_id": list_id,
        "explore_gate_confirmed": True,
        "gates": {"flags": {}},
        "prior_results": {"opportunity": {}},
    }
    phase = maybe_advance_phase_from_analyze(
        {"workers": ["strategy"]},
        state,
        "帮我写简历策略",
    )
    assert phase == "resume_strategy"
    assert task_mod.TaskStore().get_list_meta(list_id)["current_phase"] == "resume_strategy"


def test_analyze_does_not_auto_advance_ready_pipeline(pipeline_env):
    """验证 analyze does not auto advance ready pipeline 场景。"""
    session_id = "sess_adv03"
    list_id = instantiate_pipeline_for_session(session_id)
    state = {
        "list_type": "pipeline",
        "list_id": list_id,
        "explore_gate_confirmed": True,
        "gates": {"flags": {}},
        "prior_results": {"market": {}},
    }
    phase = maybe_advance_phase_from_analyze(
        {"workers": ["market"], "pipeline_phase": "market"},
        state,
        "帮我看看这个岗位",
    )
    assert phase == "explore"
    assert task_mod.TaskStore().get_list_meta(list_id)["current_phase"] == "explore"
