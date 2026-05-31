import importlib

import pytest


@pytest.fixture
def task_store(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import career_os.config as config_mod
    import career_os.platform.store.task as task_mod

    importlib.reload(config_mod)
    importlib.reload(task_mod)
    return task_mod.TaskStore()


def test_create_task_list_writes_files(task_store, tmp_path):
    list_id = task_store.create_task_list("sess_test", list_type="jd")
    list_dir = tmp_path / "tasks" / list_id
    assert (list_dir / "meta.json").exists()
    meta = task_store.get_task_list(list_id)
    assert meta["session_id"] == "sess_test"
    assert meta["list_type"] == "jd"


def test_complete_task_deletes_file(task_store, tmp_path):
    list_id = task_store.create_task_list("sess_test")
    task_store.create_task(list_id, "milestone_1", "JD 录入")
    task_path = tmp_path / "tasks" / list_id / "milestone_1.json"
    assert task_path.exists()

    err = task_store.complete_task(list_id, "milestone_1")
    assert err is None
    assert not task_path.exists()


def test_ready_list_blocks_claim_and_complete(task_store):
    list_id = task_store.create_task_list("sess_test", status="ready")
    task_store.create_task(list_id, "milestone_1", "Plan step")

    claim_err = task_store.claim_task(list_id, "milestone_1")
    assert claim_err.code == "task_blocked"

    complete_err = task_store.complete_task(list_id, "milestone_1")
    assert complete_err.code == "task_blocked"


def test_delete_lists_for_session(task_store, tmp_path):
    list_id = task_store.create_task_list("sess_a")
    task_store.create_task(list_id, "milestone_1", "Step")
    other_id = task_store.create_task_list("sess_b")
    task_store.create_task(other_id, "milestone_1", "Other")

    task_store.delete_lists_for_session("sess_a")

    assert not (tmp_path / "tasks" / list_id).exists()
    assert (tmp_path / "tasks" / other_id).exists()
