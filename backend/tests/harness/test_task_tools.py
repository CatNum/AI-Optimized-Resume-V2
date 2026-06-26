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
    import career_os.platform.store.session as session_mod
    import career_os.platform.store.task as task_mod

    importlib.reload(config_mod)
    importlib.reload(session_mod)
    importlib.reload(task_mod)
    return Harness()


@pytest.fixture
def session_id(harness, tmp_path, monkeypatch):
    """session_id（session id）的函数说明。

    harness（参数）、tmp_path（参数）、monkeypatch（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import career_os.config as config_mod
    import career_os.platform.store.session as session_mod

    importlib.reload(config_mod)
    importlib.reload(session_mod)
    return SessionStore().create_session()


def test_start_task_list_tool_registered(harness):
    """test_start_task_list_tool_registered（测试 start task list tool registered）的函数说明。

    harness（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    assert harness.tools.is_allowed("coordinator", "start_task_list")
    assert harness.tools.is_allowed("coordinator", "abandon_task_list")


def test_create_task_list_updates_state_list_id(harness, session_id):
    """test_create_task_list_updates_state_list_id（测试 create task list updates state list id）的函数说明。

    harness（参数）、session_id（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    result = harness.execute_tool(
        "coordinator",
        "create_task_list",
        {"session_id": session_id, "list_type": "pipeline", "status": "active"},
        session_id=session_id,
    )
    assert "list_id" in result
    assert SessionStore().get_state(session_id)["list_id"] == result["list_id"]


def test_list_tasks_defaults_to_state_list_id(harness, session_id):
    """test_list_tasks_defaults_to_state_list_id（测试 list tasks defaults to state list id）的函数说明。

    harness（参数）、session_id（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    created = harness.execute_tool(
        "coordinator",
        "create_task_list",
        {"session_id": session_id, "list_type": "pipeline", "status": "active"},
        session_id=session_id,
    )
    harness.execute_tool(
        "coordinator",
        "create_task",
        {
            "list_id": created["list_id"],
            "task_id": "identity",
            "kind": "milestone",
            "subject": "内心探索",
        },
        session_id=session_id,
    )
    listed = harness.execute_tool(
        "coordinator",
        "list_tasks",
        {},
        session_id=session_id,
    )
    assert len(listed["tasks"]) == 1
