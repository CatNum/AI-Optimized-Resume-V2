import importlib

import pytest

from career_os.harness.executor import Harness
from career_os.platform.store.session import SessionStore


@pytest.fixture
def harness(tmp_path, monkeypatch):
    """harness（harness）的函数说明。

    tmp_path（参数）、monkeypatch（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import career_os.config as config_mod
    import career_os.platform.store.profile as profile_mod
    import career_os.platform.store.session as session_mod

    importlib.reload(config_mod)
    importlib.reload(profile_mod)
    importlib.reload(session_mod)
    return Harness()


@pytest.fixture
def session_id():
    """session_id（session id）的函数说明。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    return SessionStore().create_session()


def test_asset_cannot_patch_exploration(harness, session_id):
    """test_asset_cannot_patch_exploration（测试 asset cannot patch exploration）的函数说明。

    harness（参数）、session_id（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    err = harness.execute_tool(
        "asset",
        "profile_patch",
        {"path": "exploration.summary", "value": "x", "session_id": session_id},
    )
    assert err.code == "profile_patch_rejected"


def test_identity_can_patch_exploration(harness, session_id):
    """test_identity_can_patch_exploration（测试 identity can patch exploration）的函数说明。

    harness（参数）、session_id（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    result = harness.execute_tool(
        "identity",
        "profile_patch",
        {"path": "exploration.summary", "value": "探索摘要", "session_id": session_id},
    )
    assert result["ok"] is True
    assert result["path"] == "exploration.summary"


def test_market_rejects_strategy_path(harness, session_id):
    """test_market_rejects_strategy_path（测试 market rejects strategy path）的函数说明。

    harness（参数）、session_id（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    err = harness.execute_tool(
        "market",
        "profile_patch",
        {"path": "strategy.path_options", "value": [], "session_id": session_id},
    )
    assert err.code == "profile_patch_rejected"


def test_coordinator_profile_get(harness, session_id):
    """test_coordinator_profile_get（测试 coordinator profile get）的函数说明。

    harness（参数）、session_id（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    harness.execute_tool(
        "identity",
        "profile_patch",
        {"path": "exploration.summary", "value": "test", "session_id": session_id},
    )
    result = SessionStore().get_artifacts(session_id)
    assert result["exploration"]["summary"] == "test"
