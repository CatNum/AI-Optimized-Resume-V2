import importlib

import pytest

from career_os.harness.explore_closure import PHASE_IN_PROGRESS, init_explore_closure
from career_os.harness.session_activity import build_session_activity, explore_flow_active
from career_os.platform.store.profile import ProfileStore
from tests.conftest import seed_explore_intake_profile


@pytest.fixture(autouse=True)
def explore_intake_ready(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import career_os.config as config_mod
    import career_os.platform.store.profile as profile_mod

    importlib.reload(config_mod)
    importlib.reload(profile_mod)
    seed_explore_intake_profile(profile_mod.ProfileStore())


def test_build_session_activity_shows_explore_in_progress():
    state = {
        "list_type": "explore",
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
    state = {
        "list_type": "explore",
        "explore_closure": init_explore_closure(),
        "prior_results": {"identity": {"phase_status": PHASE_IN_PROGRESS}},
    }
    assert explore_flow_active(state) is True
