import importlib

import pytest

from career_os.platform.pipeline_template import instantiate_pipeline_for_session


@pytest.fixture
def stores(tmp_path, monkeypatch):
    """构造测试环境和基础状态。"""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import career_os.config as config_mod
    import career_os.platform.store.session as session_mod
    import career_os.platform.store.task as task_mod

    importlib.reload(config_mod)
    importlib.reload(session_mod)
    importlib.reload(task_mod)
    return task_mod.TaskStore(), session_mod.SessionStore()


def test_complete_task_rejects_pipeline_milestone(stores):
    """验证 complete task rejects pipeline milestone 场景。"""
    task_store, session_store = stores
    session_id = session_store.create_session()
    list_id = instantiate_pipeline_for_session(session_id)
    assert isinstance(list_id, str)
    err = task_store.complete_task(list_id, "ms_explore")
    assert err is not None
    assert err.code == "milestone_complete_forbidden"


def test_clear_works_and_tree(stores):
    """验证 clear works and tree 场景。"""
    task_store, session_store = stores
    session_id = session_store.create_session()
    list_id = instantiate_pipeline_for_session(session_id)
    assert isinstance(list_id, str)
    task_store.create_task(
        list_id,
        "work_a",
        "子任务",
        kind="work",
        parent_milestone_id="ms_explore",
        pipeline_phase="explore",
        sort_order=1,
    )
    task_store.clear_works_for_phase(list_id, "explore")
    assert task_store.list_works_for_phase(list_id, "explore") == []
    tree = task_store.list_tasks_tree(list_id)
    assert tree is not None
    assert len(tree["milestones"]) == 5
    assert tree["current_phase"] == "explore"
