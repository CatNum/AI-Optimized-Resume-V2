import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class WorkerRegistryError:
    """
    WorkerRegistryError（Worker 注册表错误）表示 Worker 配置读取失败。
    """

    code: str  # 错误码
    message: str  # 错误消息


class WorkerRegistry:
    """
    WorkerRegistry（工作者注册表）负责读取可用 Worker 配置。
    """

    def __init__(self, registry_path: Path | None = None) -> None:
        """初始化对象。"""
        self._repo_root = self._find_repo_root()
        self._registry_path = registry_path or (
            self._repo_root / "config" / "workers.registry.json"
        )
        self._workers: list[dict[str, Any]] = []
        self._by_id: dict[str, dict[str, Any]] = {}
        self.reload()

    @staticmethod
    def _find_repo_root() -> Path:
        """查找repo root。"""
        current = Path(__file__).resolve()
        for parent in current.parents:
            if (parent / "config" / "workers.registry.json").exists():
                return parent
        return current.parents[4]

    def reload(self) -> None:
        """处理reload。"""
        data = json.loads(self._registry_path.read_text(encoding="utf-8"))
        self._workers = data.get("workers", [])
        self._by_id = {w["worker_id"]: w for w in self._workers}

    def get_worker(self, worker_id: str) -> dict[str, Any] | None:
        """读取worker。"""
        return self._by_id.get(worker_id)

    def get_worker_index(self) -> list[dict[str, Any]]:
        """获取给 Coordinator 使用的 Worker 索引。"""
        index: list[dict[str, Any]] = []
        for worker in self._workers:
            index.append(
                {
                    "worker_id": worker["worker_id"],
                    "label": worker.get("label", ""),
                    "summary": worker.get("summary", ""),
                    "when_to_use": worker.get("when_to_use", []),
                    "outputs": worker.get("outputs", []),
                    "gates_can_emit": worker.get("gates_can_emit", []),
                    "skills": worker.get("skills", []),
                    "tools": worker.get("tools", []),
                }
            )
        return index

    def list_worker_ids(self) -> list[str]:
        """列出worker ids。"""
        return list(self._by_id.keys())
