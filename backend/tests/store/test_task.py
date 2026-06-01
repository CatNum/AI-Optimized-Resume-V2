import importlib
import json

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
    list_id = task_store.create_task_list("sess_test", list_type="plan")
    assert isinstance(list_id, str)
    list_dir = tmp_path / "tasks" / list_id
    assert (list_dir / "meta.json").exists()
    meta = task_store.get_task_list(list_id)
    assert meta["session_id"] == "sess_test"
    assert meta["list_type"] == "plan"


def test_create_task_list_writes_created_and_updated_at(task_store):
    list_id = task_store.create_task_list("sess_test", list_type="pipeline", status="ready")
    assert isinstance(list_id, str)
    meta = task_store.get_task_list(list_id)
    assert meta["created_at"]
    assert meta["updated_at"] == meta["created_at"]


def test_complete_task_deletes_file(task_store, tmp_path):
    list_id = task_store.create_task_list("sess_test", list_type="plan")
    task_store.create_task(list_id, "milestone_1", "JD 录入")
    task_path = tmp_path / "tasks" / list_id / "milestone_1.json"
    assert task_path.exists()

    err = task_store.complete_task(list_id, "milestone_1")
    assert err is None
    assert not task_path.exists()


def test_ready_list_blocks_claim_and_complete(task_store):
    list_id = task_store.create_task_list("sess_test", list_type="plan", status="ready")
    task_store.create_task(list_id, "milestone_1", "Plan step")

    claim_err = task_store.claim_task(list_id, "milestone_1")
    assert claim_err.code == "task_blocked"

    complete_err = task_store.complete_task(list_id, "milestone_1")
    assert complete_err.code == "task_blocked"


def test_create_second_active_same_session_returns_error(task_store):
    assert isinstance(
        task_store.create_task_list("sess_a", list_type="plan", status="active"), str
    )
    err = task_store.create_task_list("sess_a", list_type="plan", status="active")
    assert getattr(err, "code", None) == "active_list_conflict_same_session"


def test_cross_session_parallel_active_ok(task_store):
    a = task_store.create_task_list("sess_a", list_type="pipeline", status="active")
    b = task_store.create_task_list("sess_b", list_type="pipeline", status="active")
    assert isinstance(a, str) and isinstance(b, str)


def test_start_task_list_ready_to_active(task_store):
    list_id = task_store.create_task_list("sess_a", list_type="pipeline", status="ready")
    assert isinstance(list_id, str)
    assert task_store.start_task_list(list_id) is None
    meta = task_store.get_task_list(list_id)
    assert meta["status"] == "active"
    assert meta["updated_at"] >= meta["created_at"]


def test_start_task_list_rejects_non_ready(task_store):
    list_id = task_store.create_task_list("sess_a", list_type="pipeline", status="active")
    err = task_store.start_task_list(list_id)
    assert err.code == "list_not_ready"


def test_start_task_list_rejects_when_other_active(task_store):
    assert isinstance(
        task_store.create_task_list("sess_a", list_type="pipeline", status="active"), str
    )
    ready_id = task_store.create_task_list("sess_a", list_type="plan", status="ready")
    err = task_store.start_task_list(ready_id)
    assert err.code == "active_list_conflict_same_session"


def test_abandon_task_list_deletes_files(task_store, tmp_path):
    list_id = task_store.create_task_list("sess_a", list_type="pipeline", status="ready")
    task_store.create_task(list_id, "identity", "内心探索", kind="milestone")
    assert task_store.abandon_task_list(list_id) is None
    assert not (tmp_path / "tasks" / list_id).exists()


def test_normalize_multi_active_keeps_newest(task_store, tmp_path, caplog):
    id_old = task_store.create_task_list("sess_a", list_type="pipeline", status="active")
    assert isinstance(id_old, str)
    id_new = task_store.create_task_list("sess_a", list_type="plan", status="ready")
    assert isinstance(id_new, str)
    for list_id, created_at in ((id_old, "2026-01-01T00:00:00+00:00"), (id_new, "2026-06-01T00:00:00+00:00")):
        meta_path = tmp_path / "tasks" / list_id / "meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["status"] = "active"
        meta["created_at"] = created_at
        meta_path.write_text(json.dumps(meta), encoding="utf-8")

    task_store.normalize_multi_active_for_session("sess_a")
    rows = task_store.list_lists_for_session("sess_a")
    actives = [r for r in rows if r["status"] == "active"]
    assert len(actives) == 1
    assert actives[0]["list_id"] == id_new


def test_list_lists_for_session_orders_active_then_ready(task_store):
    active = task_store.create_task_list("sess_a", list_type="pipeline", status="active")
    ready = task_store.create_task_list("sess_a", list_type="plan", status="ready")
    rows = task_store.list_lists_for_session("sess_a")
    assert len(rows) == 2
    assert rows[0]["list_id"] == active
    assert rows[1]["list_id"] == ready


def test_list_lists_for_session_ready_sorted_by_updated_at(task_store, tmp_path):
    older = task_store.create_task_list("sess_a", list_type="plan", status="ready")
    newer = task_store.create_task_list("sess_a", list_type="plan", status="ready")
    older_meta_path = tmp_path / "tasks" / older / "meta.json"
    newer_meta_path = tmp_path / "tasks" / newer / "meta.json"
    older_meta = json.loads(older_meta_path.read_text(encoding="utf-8"))
    newer_meta = json.loads(newer_meta_path.read_text(encoding="utf-8"))
    older_meta["updated_at"] = "2026-01-01T00:00:00+00:00"
    newer_meta["updated_at"] = "2026-06-01T00:00:00+00:00"
    older_meta_path.write_text(json.dumps(older_meta), encoding="utf-8")
    newer_meta_path.write_text(json.dumps(newer_meta), encoding="utf-8")

    rows = task_store.list_lists_for_session("sess_a")
    assert [r["list_id"] for r in rows] == [newer, older]


def test_list_lists_for_session_filters_other_sessions(task_store):
    task_store.create_task_list("sess_a", list_type="pipeline", status="active")
    task_store.create_task_list("sess_b", list_type="pipeline", status="active")
    rows = task_store.list_lists_for_session("sess_a")
    assert len(rows) == 1


def test_delete_lists_for_session(task_store, tmp_path):
    list_id = task_store.create_task_list("sess_a", list_type="plan")
    task_store.create_task(list_id, "milestone_1", "Step")
    other_id = task_store.create_task_list("sess_b", list_type="plan")
    task_store.create_task(other_id, "milestone_1", "Other")

    task_store.delete_lists_for_session("sess_a")

    assert not (tmp_path / "tasks" / list_id).exists()
    assert (tmp_path / "tasks" / other_id).exists()


def test_get_active_list_id_for_session(task_store):
    list_id = task_store.create_task_list("sess_a", list_type="pipeline", status="active")
    assert isinstance(list_id, str)
    assert task_store.get_active_list_id_for_session("sess_a") == list_id
    assert task_store.get_active_list_id_for_session("sess_b") is None
