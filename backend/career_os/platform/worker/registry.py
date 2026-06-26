import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class WorkerRegistryError:
    """WorkerRegistryError（WorkerRegistryError）的项目代码结构说明。

    该类封装当前模块中的一组相关状态或行为，供业务代码、测试代码或运行时流程复用。"""
    code: str
    message: str


class WorkerRegistry:
    """WorkerRegistry（工作者注册表）负责读取可用 Worker 配置。

    注册表来自 config/workers.registry.json，包含 worker_id、label、summary、
    when_to_use、outputs、skills、tools 等信息。Coordinator 用它构造 worker_index。
    """

    def __init__(self, registry_path: Path | None = None) -> None:
        """__init__（初始化对象）的函数说明。

        registry_path（参数）用于向该函数传入运行所需的数据。

        该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
        self._repo_root = self._find_repo_root()
        self._registry_path = registry_path or (
            self._repo_root / "config" / "workers.registry.json"
        )
        self._workers: list[dict[str, Any]] = []
        self._by_id: dict[str, dict[str, Any]] = {}
        self.reload()

    @staticmethod
    def _find_repo_root() -> Path:
        """_find_repo_root（内部函数 find repo root）的函数说明。

        该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
        current = Path(__file__).resolve()
        for parent in current.parents:
            if (parent / "config" / "workers.registry.json").exists():
                return parent
        return current.parents[4]

    def reload(self) -> None:
        """reload（reload）的函数说明。

        返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
        data = json.loads(self._registry_path.read_text(encoding="utf-8"))
        self._workers = data.get("workers", [])
        self._by_id = {w["worker_id"]: w for w in self._workers}

    def get_worker(self, worker_id: str) -> dict[str, Any] | None:
        """get_worker（get worker）的函数说明。

        worker_id（参数）用于向该函数传入运行所需的数据。

        返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
        return self._by_id.get(worker_id)

    def get_worker_index(self) -> list[dict[str, Any]]:
        """获取给 Coordinator 使用的 Worker 索引。

        返回值是精简后的 Worker 配置列表，包含 worker_id、summary、when_to_use、
        outputs、gates_can_emit、skills 和 tools，用于路由分析。
        """
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
        """list_worker_ids（list worker ids）的函数说明。

        返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
        return list(self._by_id.keys())
