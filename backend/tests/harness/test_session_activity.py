import importlib

import pytest

from career_os.harness.explore_closure import PHASE_IN_PROGRESS, init_explore_closure
from career_os.harness.session_activity import build_session_activity, explore_flow_active
from tests.conftest import seed_explore_intake_profile


@pytest.fixture(autouse=True)
def explore_intake_ready(tmp_path, monkeypatch):
    """构造测试辅助数据。"""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import career_os.config as config_mod
    import career_os.platform.store.profile as profile_mod

    importlib.reload(config_mod)
    importlib.reload(profile_mod)
    seed_explore_intake_profile(profile_mod.ProfileStore())


def test_build_session_activity_shows_explore_in_progress():
    """验证 build session activity shows explore in progress 场景。"""
    state = {
        "list_type": "pipeline",
        "explore_closure": init_explore_closure(),
        "prior_results": {"identity": {"phase_status": PHASE_IN_PROGRESS}},
    }
    activity = build_session_activity(state)

    assert activity["headline"] == "当前：职业初探 · 内心探索进行中"
    assert activity["items"][0] == {
        "id": "identity",
        "title": "内心探索",
        "status": "in_progress",
    }
    assert activity["items"][1]["status"] == "pending"


def test_explore_flow_active_when_identity_in_progress():
    """验证 explore flow active when identity in progress 场景。"""
    state = {
        "list_type": "pipeline",
        "explore_closure": init_explore_closure(),
        "prior_results": {"identity": {"phase_status": PHASE_IN_PROGRESS}},
    }
    assert explore_flow_active(state) is True


def test_build_session_activity_hides_intake_for_fresh_profile(monkeypatch):
    """验证 build session activity hides intake for fresh profile 场景。"""
    import career_os.platform.store.profile as profile_mod
    import career_os.platform.store.session as session_mod
    import career_os.platform.pipeline_template as pipeline_mod

    profile = profile_mod.ProfileStore()
    raw = profile.get(["meta", "basic", "skills", "intent", "constraints", "exploration", "career", "capability", "market", "strategy", "resume", "preference_tags", "outputs_index"])
    raw.setdefault("exploration", {})["completed_at"] = "2026-05-31T00:00:00Z"
    profile._profile_path.write_text(  # noqa: SLF001 - test-only fixture
        __import__("json").dumps(raw, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    session_id = session_mod.SessionStore().create_session()
    pipeline_mod.instantiate_pipeline_for_session(session_id)
    state = session_mod.SessionStore().get_state(session_id)
    activity = build_session_activity(state)

    assert all(item["id"] != "explore_intake" for item in activity["items"])
