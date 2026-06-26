import importlib

import pytest

from career_os.harness.executor import Harness


@pytest.fixture
def harness(tmp_path, monkeypatch):
    """harness（harness）的函数说明。

    tmp_path（参数）、monkeypatch（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import career_os.config as config_mod
    import career_os.platform.store.task as task_mod

    importlib.reload(config_mod)
    importlib.reload(task_mod)
    return Harness()


def test_coordinator_can_complete_task(harness):
    """test_coordinator_can_complete_task（测试 coordinator can complete task）的函数说明。

    harness（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    created = harness.execute_tool(
        "coordinator",
        "create_task_list",
        {"session_id": "sess_1", "list_type": "pipeline", "status": "active"},
    )
    list_id = created["list_id"]
    harness.execute_tool(
        "coordinator",
        "create_task",
        {
            "list_id": list_id,
            "task_id": "milestone_1",
            "subject": "初探",
            "kind": "milestone",
        },
    )
    result = harness.execute_tool(
        "coordinator",
        "complete_task",
        {"list_id": list_id, "task_id": "milestone_1"},
    )
    assert result["ok"] is True


def test_worker_cannot_complete_task(harness):
    """test_worker_cannot_complete_task（测试 worker cannot complete task）的函数说明。

    harness（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    err = harness.execute_tool(
        "capability",
        "complete_task",
        {"list_id": "list_x", "task_id": "milestone_1"},
    )
    assert err.code == "tool_not_allowed"


def test_proposed_completions_do_not_auto_complete(harness):
    """test_proposed_completions_do_not_auto_complete（测试 proposed completions do not auto complete）的函数说明。

    harness（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    created = harness.execute_tool(
        "coordinator",
        "create_task_list",
        {"session_id": "sess_1", "list_type": "pipeline", "status": "active"},
    )
    list_id = created["list_id"]
    harness.execute_tool(
        "coordinator",
        "create_task",
        {
            "list_id": list_id,
            "task_id": "milestone_1",
            "subject": "初探",
        },
    )
    result = harness.execute_tool(
        "coordinator",
        "apply_proposed_task_completions",
        {"proposed_task_completions": [{"task_id": "milestone_1"}]},
    )
    assert result["completed"] == []
    tasks = harness.execute_tool(
        "coordinator", "list_tasks", {"list_id": list_id}
    )
    assert len(tasks["tasks"]) == 1
