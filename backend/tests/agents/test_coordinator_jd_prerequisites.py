import importlib

import pytest

from career_os.agents.graphs.coordinator import run_coordinator_turn
from career_os.agents.lc import coordinator_llm as coordinator_llm_mod
from career_os.harness.executor import Harness
from career_os.platform.store.profile import ProfileStore


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import career_os.config as config_mod
    import career_os.platform.store.profile as profile_mod
    import career_os.platform.prompt.loader as loader_mod

    importlib.reload(config_mod)
    importlib.reload(profile_mod)
    loader_mod.load_coordinator_prompt.cache_clear()
    yield


def _seed_jd_ready(profile: ProfileStore) -> None:
    profile.patch(
        [
            {"path": "basic.name", "value": "测试", "op": "set"},
            {"path": "exploration.completed_at", "value": "2026-05-31T00:00:00Z", "op": "set"},
        ]
    )


def test_jd_request_blocked_without_prerequisites(env, monkeypatch):
    harness = Harness()
    monkeypatch.setattr(coordinator_llm_mod.lc_client, "llm_enabled", lambda: True)
    monkeypatch.setattr(
        coordinator_llm_mod.lc_client,
        "invoke_json",
        lambda system, user, role: {"workers": ["market", "opportunity"], "list_type": "jd"},
    )

    calls: list[str] = []

    def runner(worker_id, goal, session_state, context):
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
        },
        user_message="帮我评估这份 JD",
        pending_workers=[],
        worker_runner=runner,
    )

    assert calls == ["market", "opportunity"]
    assert state["session_state"].get("list_type") == "pipeline"


def test_preset_queue_blocked_at_harness_delegate(env, monkeypatch):
    harness = Harness()

    def runner(worker_id, goal, session_state, context):
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
