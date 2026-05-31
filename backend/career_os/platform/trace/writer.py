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
    def __init__(self, logs_dir: Path | None = None) -> None:
        self._logs_dir = Path(logs_dir or settings.data_dir) / "logs" / "traces"
        self._logs_dir.mkdir(parents=True, exist_ok=True)

    def _path_for_today(self) -> Path:
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
    started = time.perf_counter()

    def finalize(status: str = "ok") -> None:
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
