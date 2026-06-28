import importlib
import json
from pathlib import Path

import pytest

from career_os.harness.explore_closure import PHASE_SEGMENT_COMPLETE
from career_os.harness.executor import Harness
from career_os.harness.session_activity import explore_flow_active
from tests.conftest import seed_jd_ready_profile


@pytest.fixture(autouse=True)
def _pin_settings_data_dir(tmp_path, monkeypatch):
    """构造测试辅助数据。"""
    import career_os.config as config_mod

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config_mod.settings, "data_dir", str(tmp_path))


@pytest.fixture
def pipeline_ctx(tmp_path, monkeypatch):
    """构造测试环境和基础状态。"""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import career_os.config as config_mod
    import career_os.platform.pipeline_template as pipeline_mod
    import career_os.platform.store.profile as profile_mod
    import career_os.platform.store.session as session_mod
    import career_os.platform.store.task as task_mod
    import career_os.harness.pipeline_phase_transition as phase_mod
    import career_os.agents.graphs.coordinator as coordinator_mod

    importlib.reload(config_mod)
    monkeypatch.setattr(config_mod.settings, "data_dir", str(tmp_path))
    importlib.reload(profile_mod)
    importlib.reload(session_mod)
    importlib.reload(task_mod)
    importlib.reload(pipeline_mod)
    seed_jd_ready_profile(profile_mod.ProfileStore())
    importlib.reload(phase_mod)
    importlib.reload(coordinator_mod)

    session_id = session_mod.SessionStore().create_session()
    list_id = pipeline_mod.instantiate_pipeline_for_session(session_id)
    assert isinstance(list_id, str)
    return session_id, list_id, task_mod, coordinator_mod


def test_explore_flow_inactive_fixture_draft_not_forced(pipeline_ctx):
    """验证 explore pipeline 未激活时不会强制生成 fixture 草稿。"""
    session_id, list_id, task_mod, _ = pipeline_ctx
    task_mod.TaskStore().set_current_phase(list_id, "jd_analysis")
    session_state = {
        "session_id": session_id,
        "list_id": list_id,
        "list_type": "pipeline",
        "explore_gate_confirmed": True,
        "explore_closure": {"completed": True, "worker_done": {}},
        "gates": {"flags": {"explore_repeat_declined": True}},
        "prior_results": {
            "market": {"phase_status": PHASE_SEGMENT_COMPLETE},
            "opportunity": {"phase_status": PHASE_SEGMENT_COMPLETE},
        },
    }
    assert explore_flow_active(session_state) is False


def test_market_segment_complete_advances_current_phase(pipeline_ctx, tmp_path):
    """验证市场分段完成会推进 current_phase。"""
    session_id, list_id, task_mod, coordinator_mod = pipeline_ctx
    harness = Harness()

    def runner(worker_id, goal, session_state, context):
        """构造测试用 Worker 调度器。"""
        return {
            "worker_id": worker_id,
            "status": "completed",
            "structured_output": {
                "user_visible_summary": "市场完成",
                "phase_status": PHASE_SEGMENT_COMPLETE,
            },
        }

    state = coordinator_mod.run_coordinator_turn(
        harness,
        session_id=session_id,
        session_state={
            "session_id": session_id,
            "list_id": list_id,
            "list_type": "pipeline",
            "explore_gate_confirmed": True,
            "prior_results": {},
            "gates": {"flags": {}},
        },
        user_message="做市场分析",
        pending_workers=["market"],
        worker_runner=runner,
    )
    assert state["session_state"].get("pipeline_phase") == "market"
    meta_path = Path(tmp_path) / "tasks" / list_id / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["current_phase"] == "market"


def test_synthesize_not_explore_draft_when_gate_confirmed(pipeline_ctx):
    """验证 gate 已确认时汇总 phase 不会生成 explore 草稿。"""
    session_id, list_id, task_mod, coordinator_mod = pipeline_ctx
    task_mod.TaskStore().set_current_phase(list_id, "jd_analysis")
    harness = Harness()
    session_state = {
        "session_id": session_id,
        "list_id": list_id,
        "list_type": "pipeline",
        "explore_gate_confirmed": True,
        "gates": {"flags": {"explore_repeat_declined": True}},
        "explore_closure": {"completed": True},
        "prior_results": {
            "identity": {"user_visible_summary": "已有初探摘要"},
            "market": {"phase_status": PHASE_SEGMENT_COMPLETE},
        },
    }
    assert explore_flow_active(session_state) is False
    state = coordinator_mod.run_coordinator_turn(
        harness,
        session_id=session_id,
        session_state=session_state,
        user_message="推进下一步",
        pending_workers=[],
        worker_runner=lambda *a, **k: {},
    )
    text = state.get("synthesis_text") or state.get("synthesis_draft") or ""
    assert "仍在进行职业初探" not in text
