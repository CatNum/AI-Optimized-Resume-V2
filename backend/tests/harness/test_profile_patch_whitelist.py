import importlib

import pytest

from career_os.harness.executor import Harness


@pytest.fixture
def harness(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import career_os.config as config_mod
    import career_os.platform.store.profile as profile_mod

    importlib.reload(config_mod)
    importlib.reload(profile_mod)
    return Harness()


def test_asset_cannot_patch_exploration(harness):
    err = harness.execute_tool(
        "asset",
        "profile_patch",
        {"path": "exploration.summary", "value": "x"},
    )
    assert err.code == "profile_patch_rejected"


def test_identity_can_patch_exploration(harness):
    result = harness.execute_tool(
        "identity",
        "profile_patch",
        {"path": "exploration.summary", "value": "探索摘要"},
    )
    assert result == {"ok": True, "path": "exploration.summary"}


def test_market_rejects_strategy_path(harness):
    err = harness.execute_tool(
        "market",
        "profile_patch",
        {"path": "strategy.path_options", "value": []},
    )
    assert err.code == "profile_patch_rejected"


def test_coordinator_profile_get(harness):
    harness.execute_tool(
        "identity",
        "profile_patch",
        {"path": "exploration.summary", "value": "test"},
    )
    result = harness.execute_tool("coordinator", "profile_get", {"paths": ["exploration.summary"]})
    assert result["exploration"]["summary"] == "test"
