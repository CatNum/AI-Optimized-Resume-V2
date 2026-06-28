import importlib

import pytest

from career_os.harness.executor import Harness
from career_os.platform.store.session import SessionStore


@pytest.fixture
def harness(tmp_path, monkeypatch):
    """构造测试用 Harness。"""
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
    """构造测试环境和基础状态。"""
    return SessionStore().create_session()


def test_asset_cannot_patch_exploration(harness, session_id):
    """验证 asset Worker 不能更新 exploration。"""
    err = harness.execute_tool(
        "asset",
        "profile_patch",
        {"path": "exploration.summary", "value": "x", "session_id": session_id},
    )
    assert err.code == "profile_patch_rejected"


def test_identity_can_patch_exploration(harness, session_id):
    """验证 identity Worker 可以更新 exploration。"""
    result = harness.execute_tool(
        "identity",
        "profile_patch",
        {"path": "exploration.summary", "value": "探索摘要", "session_id": session_id},
    )
    assert result["ok"] is True
    assert result["path"] == "exploration.summary"


def test_market_rejects_strategy_path(harness, session_id):
    """验证 market Worker 会拒绝 strategy Worker 路径。"""
    err = harness.execute_tool(
        "market",
        "profile_patch",
        {"path": "strategy.path_options", "value": [], "session_id": session_id},
    )
    assert err.code == "profile_patch_rejected"


def test_coordinator_profile_get(harness, session_id):
    """验证 Coordinator 获取 profile 的处理符合预期。"""
    harness.execute_tool(
        "identity",
        "profile_patch",
        {"path": "exploration.summary", "value": "test", "session_id": session_id},
    )
    result = SessionStore().get_artifacts(session_id)
    assert result["exploration"]["summary"] == "test"
