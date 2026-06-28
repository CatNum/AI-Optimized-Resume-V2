import importlib
import json

import pytest

from career_os.harness.pipeline_routing import enforce_pipeline_phase_rules
from career_os.platform.pipeline_template import instantiate_pipeline_for_session
from career_os.platform.store import task as task_mod


@pytest.fixture
def pipeline_env(tmp_path, monkeypatch, jd_ready_profile):
    """构造测试环境和基础状态。"""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import career_os.config as config_mod
    import career_os.platform.store.profile as profile_mod
    import career_os.platform.store.task as task_store_mod
    import career_os.harness.pipeline_intent_transition as intent_mod

    importlib.reload(config_mod)
    importlib.reload(profile_mod)
    importlib.reload(task_store_mod)
    importlib.reload(intent_mod)
    return tmp_path


def test_analyze_result_advances_phase_in_enforce(pipeline_env):
    """验证强制规则 phase 会根据分析结果推进 current_phase。"""
    session_id = "sess_chat_intent"
    list_id = instantiate_pipeline_for_session(session_id)
    task_mod.TaskStore().set_current_phase(list_id, "jd_analysis")
    state = {
        "list_type": "pipeline",
        "list_id": list_id,
        "session_id": session_id,
        "explore_gate_confirmed": True,
        "gates": {"flags": {"explore_gate_confirmed": True}},
        "prior_results": {"opportunity": {"user_visible_summary": "评估"}},
    }
    enforce_pipeline_phase_rules(
        {
            "workers": ["strategy"],
            "pipeline_phase": "resume_strategy",
            "list_type": "pipeline",
        },
        state,
        "如何按这份 JD 制定简历优化策略？",
    )
    meta = task_mod.TaskStore().get_list_meta(list_id)
    assert meta["current_phase"] == "resume_strategy"
