import json
import secrets
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from career_os.config import settings

_lock = threading.Lock()


@dataclass
class TaskStoreError:
    code: str
    message: str


class TaskStore:
    def __init__(self) -> None:
        self._data_dir = Path(settings.data_dir)
        self._tasks_dir = self._data_dir / "tasks"
        self._active_path = self._tasks_dir / "_active.json"

    def _list_dir(self, list_id: str) -> Path:
        return self._tasks_dir / list_id

    def _meta_path(self, list_id: str) -> Path:
        return self._list_dir(list_id) / "meta.json"

    def _task_path(self, list_id: str, task_id: str) -> Path:
        return self._list_dir(list_id) / f"{task_id}.json"

    def create_task_list(
        self, session_id: str, list_type: str = "active", status: str = "active"
    ) -> str:
        list_id = f"list_{secrets.token_hex(6)}"
        with _lock:
            list_dir = self._list_dir(list_id)
            list_dir.mkdir(parents=True, exist_ok=True)
            meta = {
                "list_id": list_id,
                "session_id": session_id,
                "list_type": list_type,
                "status": status,
                "created_at": datetime.now(UTC).isoformat(),
            }
            self._write_json(self._meta_path(list_id), meta)
            if status == "active":
                self._set_active_unlocked(session_id, list_id)
        return list_id

    def create_task(
        self,
        list_id: str,
        task_id: str,
        title: str,
        *,
        kind: str = "work",
        worker_id: str | None = None,
    ) -> dict[str, Any]:
        task = {
            "id": task_id,
            "title": title,
            "kind": kind,
            "status": "pending",
            "worker_id": worker_id,
        }
        with _lock:
            self._write_json(self._task_path(list_id, task_id), task)
        return task

    def get_task_list(self, list_id: str) -> dict[str, Any] | None:
        with _lock:
            meta_path = self._meta_path(list_id)
            if not meta_path.exists():
                return None
            meta = self._read_json(meta_path)
            meta["tasks"] = self._list_tasks_unlocked(list_id)
            return meta

    def list_tasks(self, list_id: str) -> list[dict[str, Any]]:
        with _lock:
            return self._list_tasks_unlocked(list_id)

    def _list_tasks_unlocked(self, list_id: str) -> list[dict[str, Any]]:
        list_dir = self._list_dir(list_id)
        if not list_dir.exists():
            return []
        tasks: list[dict[str, Any]] = []
        for path in sorted(list_dir.glob("*.json")):
            if path.name == "meta.json":
                continue
            tasks.append(self._read_json(path))
        return tasks

    def claim_task(self, list_id: str, task_id: str) -> TaskStoreError | dict[str, Any]:
        with _lock:
            err = self._ensure_mutable_list(list_id)
            if err:
                return err
            task_path = self._task_path(list_id, task_id)
            if not task_path.exists():
                return TaskStoreError("task_not_found", f"Task {task_id} not found")
            task = self._read_json(task_path)
            task["status"] = "active"
            self._write_json(task_path, task)
            return task

    def complete_task(self, list_id: str, task_id: str) -> TaskStoreError | None:
        with _lock:
            err = self._ensure_mutable_list(list_id)
            if err:
                return err
            task_path = self._task_path(list_id, task_id)
            if not task_path.exists():
                return TaskStoreError("task_not_found", f"Task {task_id} not found")
            task_path.unlink()
            return None

    def delete_lists_for_session(self, session_id: str) -> None:
        with _lock:
            if not self._tasks_dir.exists():
                return
            for list_dir in self._tasks_dir.iterdir():
                if not list_dir.is_dir():
                    continue
                meta_path = list_dir / "meta.json"
                if not meta_path.exists():
                    continue
                meta = self._read_json(meta_path)
                if meta.get("session_id") != session_id:
                    continue
                for path in list_dir.iterdir():
                    if path.is_file():
                        path.unlink()
                list_dir.rmdir()
            active = self._read_active_unlocked()
            if active.get("session_id") == session_id:
                self._write_json(self._active_path, {})

    def _ensure_mutable_list(self, list_id: str) -> TaskStoreError | None:
        meta_path = self._meta_path(list_id)
        if not meta_path.exists():
            return TaskStoreError("list_not_found", f"List {list_id} not found")
        meta = self._read_json(meta_path)
        if meta.get("status") == "ready":
            return TaskStoreError("task_blocked", "claim/complete forbidden on ready list")
        return None

    def _set_active_unlocked(self, session_id: str, list_id: str) -> None:
        self._tasks_dir.mkdir(parents=True, exist_ok=True)
        self._write_json(
            self._active_path,
            {"session_id": session_id, "list_id": list_id},
        )

    def _read_active_unlocked(self) -> dict[str, Any]:
        if not self._active_path.exists():
            return {}
        return self._read_json(self._active_path)

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        with path.open(encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _write_json(path: Path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
