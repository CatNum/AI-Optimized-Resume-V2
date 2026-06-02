from career_os.harness.explore_intake import (
    enforce_explore_intake,
    explore_intake_submitted,
    is_explore_route,
)


def test_is_explore_route():
    assert is_explore_route(
        {"workers": ["identity"], "list_type": "pipeline", "pipeline_phase": "explore"}
    )
    assert not is_explore_route(
        {"workers": ["market"], "list_type": "pipeline", "pipeline_phase": "market"}
    )


def test_enforce_explore_intake_blocks_without_submission(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import importlib

    import career_os.config as config_mod
    import career_os.platform.store.profile as profile_mod

    importlib.reload(config_mod)
    importlib.reload(profile_mod)

    result = enforce_explore_intake(
        {
            "workers": ["identity", "capability"],
            "list_type": "pipeline",
            "pipeline_phase": "explore",
        },
        {"list_type": "pipeline"},
    )
    assert result["explore_intake_blocked"] is True
    assert result["workers"] == []
    assert result["list_type"] == "pipeline"


def test_enforce_explore_intake_repeat_gate_when_already_submitted(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import importlib

    import career_os.config as config_mod
    import career_os.platform.store.profile as profile_mod

    importlib.reload(config_mod)
    importlib.reload(profile_mod)

    original = {
        "workers": ["identity"],
        "list_type": "pipeline",
        "pipeline_phase": "explore",
    }
    session_state = {
        "list_type": "pipeline",
        "intake_status": {"submitted_at": "2026-05-31T00:00:00Z"},
    }
    result = enforce_explore_intake(original, session_state)
    assert result["explore_repeat_blocked"] is True
    assert result["workers"] == []
    assert explore_intake_submitted(session_state)


def test_enforce_explore_intake_allows_after_repeat_accepted_and_resubmit(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import importlib

    import career_os.config as config_mod
    import career_os.platform.store.profile as profile_mod

    importlib.reload(config_mod)
    importlib.reload(profile_mod)

    original = {
        "workers": ["identity"],
        "list_type": "pipeline",
        "pipeline_phase": "explore",
    }
    session_state = {
        "list_type": "pipeline",
        "gates": {
            "flags": {
                "explore_repeat_accepted": True,
                "explore_repeat_baseline_at": "2026-05-30T00:00:00Z",
            }
        },
        "intake_status": {"submitted_at": "2026-05-31T00:00:00Z"},
    }
    result = enforce_explore_intake(original, session_state)
    assert result["workers"] == original["workers"]
    assert result["list_type"] == "pipeline"
