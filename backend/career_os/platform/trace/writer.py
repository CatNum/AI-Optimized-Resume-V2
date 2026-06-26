import json
import threading
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from career_os.config import settings
from career_os.platform.trace.labels import annotate_trace_record

_lock = threading.Lock()


class TraceWriter:
    """TraceWriter（TraceWriter）的项目代码结构说明。

    该类封装当前模块中的一组相关状态或行为，供业务代码、测试代码或运行时流程复用。"""
    def __init__(self, logs_dir: Path | None = None) -> None:
        """__init__（初始化对象）的函数说明。

        logs_dir（参数）用于向该函数传入运行所需的数据。

        该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
        self._logs_dir = Path(logs_dir or settings.data_dir) / "logs" / "traces"
        self._logs_dir.mkdir(parents=True, exist_ok=True)

    def _path_for_today(self) -> Path:
        """_path_for_today（内部函数 path for today）的函数说明。

        该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
        day = datetime.now(UTC).strftime("%Y-%m-%d")
        return self._logs_dir / f"{day}.jsonl"

    def emit(
        self,
        event: str,
        *,
        session_id: str | None = None,
        run_id: str | None = None,
        worker_id: str | None = None,
        tool_name: str | None = None,
        actor: str | None = None,
        status: str = "ok",
        latency_ms: int | None = None,
        detail: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """emit（emit）的函数说明。

        event（参数）、session_id（参数）、run_id（参数）、worker_id（参数）、tool_name（参数）、actor（参数）、status（参数）、latency_ms（参数） 等用于向该函数传入运行所需的数据。

        返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
        record = annotate_trace_record(
            {
                "ts": datetime.now(UTC).isoformat(),
                "event": event,
                "run_id": run_id or f"run_{uuid.uuid4().hex[:12]}",
                "session_id": session_id,
                "worker_id": worker_id,
                "tool_name": tool_name,
                "actor": actor,
                "status": status,
                "latency_ms": latency_ms,
                "detail": detail or {},
            }
        )
        with _lock:
            with self._path_for_today().open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record

    def read_events(self, day: str | None = None) -> list[dict[str, Any]]:
        """read_events（read events）的函数说明。

        day（参数）用于向该函数传入运行所需的数据。

        返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
        target = self._logs_dir / f"{day or datetime.now(UTC).strftime('%Y-%m-%d')}.jsonl"
        if not target.exists():
            return []
        events: list[dict[str, Any]] = []
        with target.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    events.append(json.loads(line))
        return events


def timed_emit(
    writer: TraceWriter,
    event: str,
    *,
    session_id: str | None = None,
    actor: str | None = None,
    tool_name: str | None = None,
    worker_id: str | None = None,
    detail: dict[str, Any] | None = None,
) -> Callable[[], None]:
    """timed_emit（timed emit）的函数说明。

    writer（参数）、event（参数）、session_id（参数）、actor（参数）、tool_name（参数）、worker_id（参数）、detail（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    started = time.perf_counter()

    def finalize(status: str = "ok") -> None:
        """finalize（finalize）的函数说明。

        status（参数）用于向该函数传入运行所需的数据。

        返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
        latency_ms = int((time.perf_counter() - started) * 1000)
        writer.emit(
            event,
            session_id=session_id,
            actor=actor,
            tool_name=tool_name,
            worker_id=worker_id,
            status=status,
            latency_ms=latency_ms,
            detail=detail,
        )

    return finalize
