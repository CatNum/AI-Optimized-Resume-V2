import importlib

import pytest


@pytest.fixture
def task_store(tmp_path, monkeypatch):
    """构造测试辅助数据。"""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import career_os.config as config_mod
    import career_os.platform.store.task as task_mod

    importlib.reload(config_mod)
    importlib.reload(task_mod)
    return task_mod.TaskStore()


def test_create_task_list_rejects_explore(task_store):
    """验证创建任务列表时会拒绝 explore。"""
    err = task_store.create_task_list("sess_a", list_type="explore", status="ready")
    assert err.code == "list_type_deprecated"


def test_create_task_list_rejects_jd(task_store):
    """验证创建任务列表会拒绝 JD。"""
    err = task_store.create_task_list("sess_a", list_type="jd", status="ready")
    assert err.code == "list_type_deprecated"


def test_create_task_list_accepts_pipeline_and_plan(task_store):
    """验证创建任务列表接受 pipeline 和计划的处理符合预期。"""
    pipeline_id = task_store.create_task_list("sess_a", list_type="pipeline", status="ready")
    plan_id = task_store.create_task_list("sess_b", list_type="plan", status="ready")
    assert isinstance(pipeline_id, str)
    assert isinstance(plan_id, str)
