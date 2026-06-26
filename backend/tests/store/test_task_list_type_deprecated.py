import importlib

import pytest


@pytest.fixture
def task_store(tmp_path, monkeypatch):
    """task_store（task store）的函数说明。

    tmp_path（参数）、monkeypatch（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import career_os.config as config_mod
    import career_os.platform.store.task as task_mod

    importlib.reload(config_mod)
    importlib.reload(task_mod)
    return task_mod.TaskStore()


def test_create_task_list_rejects_explore(task_store):
    """test_create_task_list_rejects_explore（测试 create task list rejects explore）的函数说明。

    task_store（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    err = task_store.create_task_list("sess_a", list_type="explore", status="ready")
    assert err.code == "list_type_deprecated"


def test_create_task_list_rejects_jd(task_store):
    """test_create_task_list_rejects_jd（测试 create task list rejects jd）的函数说明。

    task_store（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    err = task_store.create_task_list("sess_a", list_type="jd", status="ready")
    assert err.code == "list_type_deprecated"


def test_create_task_list_accepts_pipeline_and_plan(task_store):
    """test_create_task_list_accepts_pipeline_and_plan（测试 create task list accepts pipeline and plan）的函数说明。

    task_store（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    pipeline_id = task_store.create_task_list("sess_a", list_type="pipeline", status="ready")
    plan_id = task_store.create_task_list("sess_b", list_type="plan", status="ready")
    assert isinstance(pipeline_id, str)
    assert isinstance(plan_id, str)
