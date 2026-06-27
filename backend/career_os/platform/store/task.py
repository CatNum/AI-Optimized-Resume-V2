import json
import logging
import secrets
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from career_os.config import settings
from career_os.platform.pipeline_constants import (
    MILESTONE_ID_TO_PHASE,
    PHASE_TO_MILESTONE_ID,
    PIPELINE_PHASES,
)

_lock = threading.Lock()
logger = logging.getLogger(__name__)


@dataclass
class TaskStoreError:
    """
    TaskStoreError（任务存储错误）表示任务列表读写或状态操作失败。
    """

    code: str  # 错误码
    message: str  # 错误消息


class TaskStore:
    """
    TaskStore（任务列表存储）负责读写 pipeline 任务列表。
    """

    def __init__(self) -> None:
        """初始化对象。"""
        self._data_dir = Path(settings.data_dir)
        self._tasks_dir = self._data_dir / "tasks"

    def _list_dir(self, list_id: str) -> Path:
        """列出dir。"""
        return self._tasks_dir / list_id

    def _meta_path(self, list_id: str) -> Path:
        """处理meta path。"""
        return self._list_dir(list_id) / "meta.json"

    def _task_path(self, list_id: str, task_id: str) -> Path:
        """处理task path。"""
        return self._list_dir(list_id) / f"{task_id}.json"

    _DEPRECATED_LIST_TYPES = frozenset({"explore", "jd"})  # 废弃列表类型集合

    def create_task_list(
        self,
        session_id: str,
        *,
        list_type: str,
        status: str = "active",
        current_phase: str | None = None,
    ) -> str | TaskStoreError:
        """创建task list。"""
        if list_type in self._DEPRECATED_LIST_TYPES:
            return TaskStoreError(
                "list_type_deprecated",
                f"list_type {list_type!r} is deprecated; use pipeline",
            )
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
            if list_type == "pipeline":
                meta["current_phase"] = current_phase or "explore"
            elif current_phase is not None:
                meta["current_phase"] = current_phase
            self._write_json(self._meta_path(list_id), meta)
        return list_id

    def get_list_meta(self, list_id: str) -> dict[str, Any] | None:
        """读取任务列表元数据。"""
        with _lock:
            meta_path = self._meta_path(list_id)
            if not meta_path.exists():
                return None
            return self._read_json(meta_path)

    def create_task(
        self,
        list_id: str,
        task_id: str,
        title: str,
        *,
        kind: str = "work",
        worker_id: str | None = None,
        parent_milestone_id: str | None = None,
        pipeline_phase: str | None = None,
        description: str | None = None,
        sort_order: int | None = None,
        blocked_by: str | None = None,
        requires_user_confirm: bool | None = None,
    ) -> dict[str, Any] | TaskStoreError:
        """创建task。"""
        with _lock:
            meta_path = self._meta_path(list_id)
            if not meta_path.exists():
                return TaskStoreError("list_not_found", f"List {list_id} not found")
            meta = self._read_json(meta_path)
            if parent_milestone_id:
                parent_path = self._task_path(list_id, parent_milestone_id)
                if not parent_path.exists():
                    return TaskStoreError(
                        "parent_not_found",
                        f"Parent milestone {parent_milestone_id} not found",
                    )
            task: dict[str, Any] = {
                "id": task_id,
                "title": title,
                "kind": kind,
                "status": "pending",
                "worker_id": worker_id,
            }
            if parent_milestone_id is not None:
                task["parent_milestone_id"] = parent_milestone_id
            if pipeline_phase is not None:
                task["pipeline_phase"] = pipeline_phase
            if description is not None:
                task["description"] = description
            if sort_order is not None:
                task["sort_order"] = sort_order
            if blocked_by is not None:
                task["blockedBy"] = blocked_by
            if requires_user_confirm is not None:
                task["requires_user_confirm"] = requires_user_confirm
            if meta.get("list_type") == "pipeline":
                task["list_type"] = "pipeline"
            self._write_json(self._task_path(list_id, task_id), task)
        return task

    def get_task(self, list_id: str, task_id: str) -> dict[str, Any] | None:
        """读取task。"""
        with _lock:
            task_path = self._task_path(list_id, task_id)
            if not task_path.exists():
                return None
            return self._read_json(task_path)

    def get_task_list(self, list_id: str) -> dict[str, Any] | None:
        """读取task list。"""
        with _lock:
            meta_path = self._meta_path(list_id)
            if not meta_path.exists():
                return None
            meta = self._read_json(meta_path)
            meta["tasks"] = self._list_tasks_unlocked(list_id)
            return meta

    def list_tasks(self, list_id: str) -> list[dict[str, Any]]:
        """列出tasks。"""
        with _lock:
            return self._list_tasks_unlocked(list_id)

    def _list_tasks_unlocked(self, list_id: str) -> list[dict[str, Any]]:
        """列出tasks unlocked。"""
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
        """领取task。"""
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
        """完成task。"""
        with _lock:
            task_path = self._task_path(list_id, task_id)
            if not task_path.exists():
                return TaskStoreError("task_not_found", f"Task {task_id} not found")
            task = self._read_json(task_path)
            meta = self._read_json(self._meta_path(list_id))
            if meta.get("list_type") == "pipeline" and (
                task.get("kind") == "milestone" or task_id.startswith("ms_")
            ):
                return TaskStoreError(
                    "milestone_complete_forbidden",
                    "Pipeline milestones cannot be completed",
                )
            err = self._ensure_mutable_list(list_id)
            if err:
                return err
            task_path.unlink()
            return None

    def patch_list_meta(self, list_id: str, fields: dict[str, Any]) -> TaskStoreError | None:
        """补丁更新list meta。"""
        with _lock:
            meta_path = self._meta_path(list_id)
            if not meta_path.exists():
                return TaskStoreError("list_not_found", f"List {list_id} not found")
            meta = self._read_json(meta_path)
            meta.update(fields)
            meta["updated_at"] = datetime.now(UTC).isoformat()
            self._write_json(meta_path, meta)
            return None

    def set_current_phase(self, list_id: str, phase: str) -> TaskStoreError | None:
        """设置current phase。"""
        if phase not in PIPELINE_PHASES:
            return TaskStoreError("invalid_phase", f"Unknown pipeline phase: {phase}")
        with _lock:
            meta_path = self._meta_path(list_id)
            if not meta_path.exists():
                return TaskStoreError("list_not_found", f"List {list_id} not found")
            meta = self._read_json(meta_path)
            if meta.get("list_type") != "pipeline":
                return TaskStoreError("not_pipeline", "List is not pipeline type")
            now = datetime.now(UTC).isoformat()
            meta["current_phase"] = phase
            meta["updated_at"] = now
            self._write_json(meta_path, meta)
            return None

    def clear_works_for_phase(self, list_id: str, phase: str) -> TaskStoreError | None:
        """清理works for phase。"""
        milestone_id = PHASE_TO_MILESTONE_ID.get(phase)
        if not milestone_id:
            return TaskStoreError("invalid_phase", f"Unknown pipeline phase: {phase}")
        with _lock:
            list_dir = self._list_dir(list_id)
            if not list_dir.exists():
                return TaskStoreError("list_not_found", f"List {list_id} not found")
            for path in list(list_dir.glob("*.json")):
                if path.name == "meta.json":
                    continue
                task = self._read_json(path)
                if task.get("kind") != "work":
                    continue
                if task.get("parent_milestone_id") == milestone_id:
                    path.unlink()
            return None

    def claim_first_work_for_phase(self, list_id: str, phase: str) -> dict[str, Any] | None:
        """领取first work for phase。"""
        milestone_id = PHASE_TO_MILESTONE_ID.get(phase)
        if not milestone_id:
            return None
        with _lock:
            err = self._ensure_mutable_list(list_id)
            if err:
                return None
            works = [
                t
                for t in self._list_tasks_unlocked(list_id)
                if t.get("kind") == "work"
                and t.get("parent_milestone_id") == milestone_id
                and t.get("status") == "pending"
            ]
            if not works:
                return None
            works.sort(key=lambda t: t.get("sort_order", 0))
            first = works[0]
            task_path = self._task_path(list_id, first["id"])
            first["status"] = "active"
            self._write_json(task_path, first)
            return first

    def list_tasks_tree(self, list_id: str) -> dict[str, Any] | None:
        """列出tasks tree。"""
        with _lock:
            meta_path = self._meta_path(list_id)
            if not meta_path.exists():
                return None
            meta = self._read_json(meta_path)
            if meta.get("list_type") != "pipeline":
                return None
            current_phase = meta.get("current_phase") or "explore"
            if meta.get("status") == "ready":
                current_phase = "explore"
            current_ms = PHASE_TO_MILESTONE_ID.get(current_phase, "ms_explore")
            all_tasks = self._list_tasks_unlocked(list_id)
            milestones = sorted(
                (t for t in all_tasks if t.get("kind") == "milestone"),
                key=lambda t: PIPELINE_PHASES.index(
                    t.get("pipeline_phase", "explore")
                )
                if t.get("pipeline_phase") in PIPELINE_PHASES
                else 99,
            )
            works_by_parent: dict[str, list[dict[str, Any]]] = {}
            for task in all_tasks:
                if task.get("kind") != "work":
                    continue
                parent = task.get("parent_milestone_id")
                if not parent:
                    continue
                works_by_parent.setdefault(parent, []).append(task)
            milestone_rows: list[dict[str, Any]] = []
            for ms in milestones:
                ms_id = ms["id"]
                works = works_by_parent.get(ms_id, [])
                if ms_id == current_ms:
                    works = sorted(works, key=lambda w: w.get("sort_order", 0))
                else:
                    works = []
                milestone_rows.append(
                    {
                        "task_id": ms_id,
                        "pipeline_phase": ms.get("pipeline_phase"),
                        "subject": ms.get("title"),
                        "works": works,
                    }
                )
            return {
                "list_id": list_id,
                "current_phase": current_phase,
                "milestones": milestone_rows,
            }

    def list_works_for_phase(self, list_id: str, phase: str) -> list[dict[str, Any]]:
        """列出works for phase。"""
        milestone_id = PHASE_TO_MILESTONE_ID.get(phase)
        if not milestone_id:
            return []
        with _lock:
            return [
                t
                for t in self._list_tasks_unlocked(list_id)
                if t.get("kind") == "work"
                and t.get("parent_milestone_id") == milestone_id
            ]

    def start_task_list(self, list_id: str) -> TaskStoreError | None:
        """启动task list。"""
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
        """废弃task list。"""
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
        """读取active list id for session。"""
        with _lock:
            self.normalize_multi_active_for_session_unlocked(session_id)
            actives = self._find_active_metas_for_session_unlocked(session_id)
            if not actives:
                ready_pipeline_ids: list[str] = []
                if self._tasks_dir.exists():
                    for list_dir in self._tasks_dir.iterdir():
                        if not list_dir.is_dir():
                            continue
                        meta_path = list_dir / "meta.json"
                        if not meta_path.exists():
                            continue
                        meta = self._read_json(meta_path)
                        if (
                            meta.get("session_id") == session_id
                            and meta.get("list_type") == "pipeline"
                            and meta.get("status") == "ready"
                        ):
                            ready_pipeline_ids.append(meta["list_id"])
                if not ready_pipeline_ids:
                    return None
                return ready_pipeline_ids[-1]
            if len(actives) == 1:
                return actives[0]["list_id"]
            newest = max(actives, key=lambda m: m.get("created_at") or "")
            return newest["list_id"]

    def normalize_multi_active_for_session(self, session_id: str) -> None:
        """规范化multi active for session。"""
        with _lock:
            self.normalize_multi_active_for_session_unlocked(session_id)

    def list_lists_for_session(self, session_id: str) -> list[dict[str, Any]]:
        """列出lists for session。"""
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
        """删除lists for session。"""
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
        """查找active metas for session unlocked。"""
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
        """规范化multi active for session unlocked。"""
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
        """确保mutable list。"""
        meta_path = self._meta_path(list_id)
        if not meta_path.exists():
            return TaskStoreError("list_not_found", f"List {list_id} not found")
        meta = self._read_json(meta_path)
        if meta.get("status") == "ready":
            return TaskStoreError("task_blocked", "claim/complete forbidden on ready list")
        return None

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        """读取json。"""
        with path.open(encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _write_json(path: Path, data: dict[str, Any]) -> None:
        """写入json。"""
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
