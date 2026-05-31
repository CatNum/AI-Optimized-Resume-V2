from career_os.harness.explore_intake import (
    enforce_explore_intake,
    explore_intake_submitted,
    is_explore_route,
)
from career_os.platform.store.profile import ProfileStore


def test_is_explore_route():
    assert is_explore_route({"workers": ["identity"], "list_type": "explore"})
    assert not is_explore_route({"workers": ["market"], "list_type": "jd"})


def test_enforce_explore_intake_blocks_without_submission(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import importlib

    import career_os.config as config_mod
    import career_os.platform.store.profile as profile_mod

    importlib.reload(config_mod)
    importlib.reload(profile_mod)

    result = enforce_explore_intake(
        {"workers": ["identity", "capability"], "list_type": "explore"},
        {},
    )
    assert result["explore_intake_blocked"] is True
    assert result["workers"] == []


def test_enforce_explore_intake_allows_after_submission(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import importlib

    import career_os.config as config_mod
    import career_os.platform.store.profile as profile_mod

    importlib.reload(config_mod)
    importlib.reload(profile_mod)

    ProfileStore().patch(
        [
            {
                "path": "exploration.intake.submitted_at",
                "value": "2026-05-31T00:00:00Z",
                "op": "set",
            }
        ]
    )
    original = {"workers": ["identity"], "list_type": "explore"}
    result = enforce_explore_intake(original, {})
    assert result == original
    assert explore_intake_submitted()
