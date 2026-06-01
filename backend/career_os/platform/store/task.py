import json
import logging
import secrets
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from career_os.config import settings

_lock = threading.Lock()
logger = logging.getLogger(__name__)


@dataclass
class TaskStoreError:
    code: str
    message: str


class TaskStore:
    def __init__(self) -> None:
        self._data_dir = Path(settings.data_dir)
        self._tasks_dir = self._data_dir / "tasks"

    def _list_dir(self, list_id: str) -> Path:
        return self._tasks_dir / list_id

    def _meta_path(self, list_id: str) -> Path:
        return self._list_dir(list_id) / "meta.json"

    def _task_path(self, list_id: str, task_id: str) -> Path:
        return self._list_dir(list_id) / f"{task_id}.json"

    def create_task_list(
        self, session_id: str, *, list_type: str, status: str = "active"
    ) -> str | TaskStoreError:
        if status == "active":
            existing = self._find_active_metas_for_session_unlocked(session_id)
            if existing:
                return TaskStoreError(
                    "active_list_conflict_same_session",
                    "Session already has an active task list",
                )
        list_id = f"list_{secrets.token_hex(6)}"
        now = datetime.now(UTC).isoformat()
        with _lock:
            list_dir = self._list_dir(list_id)
            list_dir.mkdir(parents=True, exist_ok=True)
            meta = {
                "list_id": list_id,
                "session_id": session_id,
                "list_type": list_type,
                "status": status,
                "created_at": now,
                "updated_at": now,
            }
            self._write_json(self._meta_path(list_id), meta)
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

    def start_task_list(self, list_id: str) -> TaskStoreError | None:
        with _lock:
            meta_path = self._meta_path(list_id)
            if not meta_path.exists():
                return TaskStoreError("list_not_found", f"List {list_id} not found")
            meta = self._read_json(meta_path)
            if meta.get("status") != "ready":
                return TaskStoreError("list_not_ready", "List is not ready to start")
            session_id = meta.get("session_id")
            if not session_id:
                return TaskStoreError("list_not_found", f"List {list_id} not found")
            for other in self._find_active_metas_for_session_unlocked(session_id):
                if other.get("list_id") != list_id:
                    return TaskStoreError(
                        "active_list_conflict_same_session",
                        "Session already has an active task list",
                    )
            now = datetime.now(UTC).isoformat()
            meta["status"] = "active"
            meta["updated_at"] = now
            self._write_json(meta_path, meta)
            return None

    def abandon_task_list(self, list_id: str) -> TaskStoreError | None:
        with _lock:
            list_dir = self._list_dir(list_id)
            if not list_dir.exists():
                return TaskStoreError("list_not_found", f"List {list_id} not found")
            for path in list_dir.iterdir():
                if path.is_file():
                    path.unlink()
            list_dir.rmdir()
            return None

    def get_active_list_id_for_session(self, session_id: str) -> str | None:
        with _lock:
            self.normalize_multi_active_for_session_unlocked(session_id)
            actives = self._find_active_metas_for_session_unlocked(session_id)
            if not actives:
                return None
            if len(actives) == 1:
                return actives[0]["list_id"]
            newest = max(actives, key=lambda m: m.get("created_at") or "")
            return newest["list_id"]

    def normalize_multi_active_for_session(self, session_id: str) -> None:
        with _lock:
            self.normalize_multi_active_for_session_unlocked(session_id)

    def list_lists_for_session(self, session_id: str) -> list[dict[str, Any]]:
        with _lock:
            self.normalize_multi_active_for_session_unlocked(session_id)
            if not self._tasks_dir.exists():
                return []
            metas: list[dict[str, Any]] = []
            for list_dir in self._tasks_dir.iterdir():
                if not list_dir.is_dir():
                    continue
                meta_path = list_dir / "meta.json"
                if not meta_path.exists():
                    continue
                meta = self._read_json(meta_path)
                if meta.get("session_id") != session_id:
                    continue
                metas.append(meta)
            active = [m for m in metas if m.get("status") == "active"]
            ready = sorted(
                (m for m in metas if m.get("status") == "ready"),
                key=lambda m: m.get("updated_at") or m.get("created_at") or "",
                reverse=True,
            )
            other = [m for m in metas if m.get("status") not in ("active", "ready")]
            sorted_metas = active + ready + other
            return [
                {
                    "list_id": meta["list_id"],
                    "list_type": meta.get("list_type"),
                    "status": meta.get("status"),
                    "tasks": self._list_tasks_unlocked(meta["list_id"]),
                }
                for meta in sorted_metas
            ]

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

    def _find_active_metas_for_session_unlocked(
        self, session_id: str
    ) -> list[dict[str, Any]]:
        if not self._tasks_dir.exists():
            return []
        actives: list[dict[str, Any]] = []
        for list_dir in self._tasks_dir.iterdir():
            if not list_dir.is_dir():
                continue
            meta_path = list_dir / "meta.json"
            if not meta_path.exists():
                continue
            meta = self._read_json(meta_path)
            if meta.get("session_id") != session_id:
                continue
            if meta.get("status") == "active":
                actives.append(meta)
        return actives

    def normalize_multi_active_for_session_unlocked(self, session_id: str) -> None:
        actives = self._find_active_metas_for_session_unlocked(session_id)
        if len(actives) <= 1:
            return
        sorted_actives = sorted(
            actives, key=lambda m: m.get("created_at") or "", reverse=True
        )
        kept = sorted_actives[0]
        demoted = [m["list_id"] for m in sorted_actives[1:]]
        now = datetime.now(UTC).isoformat()
        for meta in sorted_actives[1:]:
            meta_path = self._meta_path(meta["list_id"])
            meta["status"] = "ready"
            meta["updated_at"] = now
            self._write_json(meta_path, meta)
        logger.warning(
            "normalized multi-active session=%s kept=%s demoted=%s",
            session_id,
            kept["list_id"],
            demoted,
        )

    def _ensure_mutable_list(self, list_id: str) -> TaskStoreError | None:
        meta_path = self._meta_path(list_id)
        if not meta_path.exists():
            return TaskStoreError("list_not_found", f"List {list_id} not found")
        meta = self._read_json(meta_path)
        if meta.get("status") == "ready":
            return TaskStoreError("task_blocked", "claim/complete forbidden on ready list")
        return None

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        with path.open(encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _write_json(path: Path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
