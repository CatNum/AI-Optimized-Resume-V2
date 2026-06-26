import importlib

import pytest

from career_os.agents.graphs.coordinator import run_coordinator_turn
from career_os.agents.lc import coordinator_llm as coordinator_llm_mod
from career_os.harness.executor import Harness
from career_os.platform.store.profile import ProfileStore


@pytest.fixture
def env(tmp_path, monkeypatch):
    """env（env）的函数说明。

    tmp_path（参数）、monkeypatch（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import career_os.config as config_mod
    import career_os.platform.store.profile as profile_mod
    import career_os.platform.prompt.loader as loader_mod

    importlib.reload(config_mod)
    importlib.reload(profile_mod)
    loader_mod.load_coordinator_prompt.cache_clear()
    yield


def _seed_jd_ready(profile: ProfileStore) -> None:
    """_seed_jd_ready（内部函数 seed jd ready）的函数说明。

    profile（参数）用于向该函数传入运行所需的数据。

    该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
    profile.patch([{"path": "basic.name", "value": "测试", "op": "set"}])


def test_jd_request_blocked_without_prerequisites(env, monkeypatch):
    """test_jd_request_blocked_without_prerequisites（测试 jd request blocked without prerequisites）的函数说明。

    env（参数）、monkeypatch（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    harness = Harness()
    monkeypatch.setattr(coordinator_llm_mod.lc_client, "llm_enabled", lambda: True)
    monkeypatch.setattr(
        coordinator_llm_mod.lc_client,
        "invoke_json",
        lambda system, user, role: {"workers": ["market", "opportunity"], "list_type": "jd"},
    )

    calls: list[str] = []

    def runner(worker_id, goal, session_state, context):
        """runner（runner）的函数说明。

        worker_id（参数）、goal（参数）、session_state（参数）、context（参数）用于向该函数传入运行所需的数据。

        返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
        calls.append(worker_id)
        return {"worker_id": worker_id, "status": "completed", "structured_output": {}}

    state = run_coordinator_turn(
        harness,
        session_id="sess_jd_block",
        session_state={"prior_results": {}, "gates": {"flags": {}}},
        user_message="帮我评估这份 JD",
        pending_workers=[],
        worker_runner=runner,
    )

    assert calls == []
    draft = state.get("synthesis_draft") or ""
    assert "建档" in draft or "初探" in draft


def test_jd_request_allowed_when_prerequisites_met(env, monkeypatch):
    """test_jd_request_allowed_when_prerequisites_met（测试 jd request allowed when prerequisites met）的函数说明。

    env（参数）、monkeypatch（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    _seed_jd_ready(ProfileStore())
    harness = Harness()
    monkeypatch.setattr(coordinator_llm_mod.lc_client, "llm_enabled", lambda: True)
    monkeypatch.setattr(
        coordinator_llm_mod.lc_client,
        "invoke_json",
        lambda system, user, role: {"workers": ["market", "opportunity"], "list_type": "jd"},
    )

    calls: list[str] = []

    def runner(worker_id, goal, session_state, context):
        """runner（runner）的函数说明。

        worker_id（参数）、goal（参数）、session_state（参数）、context（参数）用于向该函数传入运行所需的数据。

        返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
        calls.append(worker_id)
        return {
            "worker_id": worker_id,
            "status": "completed",
            "structured_output": {"user_visible_summary": "ok"},
        }

    state = run_coordinator_turn(
        harness,
        session_id="sess_jd_ok",
        session_state={
            "prior_results": {},
            "gates": {"flags": {}},
            "list_type": "pipeline",
            "explore_gate_confirmed": True,
            "explore_closure": {"completed": True},
            "intake_status": {"submitted_at": "2026-05-31T00:00:00Z"},
        },
        user_message="帮我评估这份 JD",
        pending_workers=[],
        worker_runner=runner,
    )

    assert calls == []
    assert state["session_state"].get("list_type") == "pipeline"


def test_preset_queue_blocked_at_harness_delegate(env, monkeypatch):
    """test_preset_queue_blocked_at_harness_delegate（测试 preset queue blocked at harness delegate）的函数说明。

    env（参数）、monkeypatch（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    harness = Harness()

    def runner(worker_id, goal, session_state, context):
        """runner（runner）的函数说明。

        worker_id（参数）、goal（参数）、session_state（参数）、context（参数）用于向该函数传入运行所需的数据。

        返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
        return {"worker_id": worker_id, "status": "completed", "structured_output": {}}

    state = run_coordinator_turn(
        harness,
        session_id="sess_preset_block",
        session_state={"prior_results": {}, "gates": {"flags": {}}},
        user_message="评估 JD",
        pending_workers=["market", "opportunity"],
        worker_runner=runner,
    )

    assert state["delegate_count"] == 0
    assert state["session_state"].get("jd_prerequisite_blocked") is True
    draft = state.get("synthesis_draft") or ""
    assert "建档" in draft or "初探" in draft
