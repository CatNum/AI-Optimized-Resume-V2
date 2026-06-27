import importlib

import pytest

from career_os.harness.executor import Harness


@pytest.fixture
def harness(tmp_path, monkeypatch):
    """构造测试用 Harness。"""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import career_os.config as config_mod
    import career_os.platform.store.task as task_mod

    importlib.reload(config_mod)
    importlib.reload(task_mod)
    return Harness()


def test_coordinator_can_complete_task(harness):
    """验证 coordinator can complete task 场景。"""
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
    """验证 worker cannot complete task 场景。"""
    err = harness.execute_tool(
        "capability",
        "complete_task",
        {"list_id": "list_x", "task_id": "milestone_1"},
    )
    assert err.code == "tool_not_allowed"


def test_proposed_completions_do_not_auto_complete(harness):
    """验证 proposed completions do not auto complete 场景。"""
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
