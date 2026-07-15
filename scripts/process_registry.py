#!/usr/bin/env python3
"""登记并按进程身份安全关闭单个 Career OS demo 的本地进程。"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import psutil


def _write_atomic(path: Path, payload: dict[str, Any]) -> None:
    """通过同目录临时文件原子写入进程登记。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temp.open("w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2, sort_keys=True)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def record(runtime_dir: Path, name: str, pid: int, demo: str, marker: str) -> None:
    """记录 pid（进程编号）、启动时间、可执行文件和命令标识。"""
    process = psutil.Process(pid)
    _write_atomic(
        runtime_dir / f"{name}.json",
        {
            "schema_version": 1,
            "name": name,
            "pid": pid,
            "process_started_at": process.create_time(),
            "executable_path": str(Path(process.exe()).resolve()),
            "command_marker": marker,
            "recorded_command": " ".join(process.cmdline()),
            "demo": demo,
            "recorded_at": time.time(),
        },
    )


def _read_records(runtime_dir: Path) -> list[tuple[Path, dict[str, Any]]]:
    """读取 runtime 中已知 JSON 登记；损坏文件保留并跳过。"""
    records: list[tuple[Path, dict[str, Any]]] = []
    if not runtime_dir.exists():
        return records
    for path in sorted(runtime_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            records.append((path, payload))
    return records


def _matches(record: dict[str, Any], demo: str, demo_data_dir: Path) -> psutil.Process | None:
    """复核 demo、PID、启动时间、可执行路径和命令标识，防止 PID 重用误杀。"""
    pid = record.get("pid")
    started_at = record.get("process_started_at")
    executable = record.get("executable_path")
    if not isinstance(pid, int) or not isinstance(started_at, (int, float)):
        return None
    if record.get("demo") is not None:
        if record.get("demo") != demo:
            return None
    elif record.get("demo_data_root") != str(demo_data_dir.resolve()):
        return None
    try:
        process = psutil.Process(pid)
        if abs(process.create_time() - float(started_at)) > 0.001:
            return None
        if executable and str(Path(process.exe()).resolve()) != str(Path(executable).resolve()):
            return None
        marker = record.get("command_marker")
        if isinstance(marker, str) and marker and marker not in " ".join(process.cmdline()):
            return None
        return process
    except (psutil.Error, OSError, ValueError):
        return None


def cleanup(runtime_dir: Path, demo: str, demo_data_dir: Path) -> int:
    """先 TERM 身份匹配进程，等待十秒后仅 KILL 仍是同一身份的进程树。"""
    records = _read_records(runtime_dir)
    matched: list[tuple[Path, dict[str, Any], psutil.Process]] = []
    force_targets: dict[int, tuple[float, str | None]] = {}
    for path, payload in records:
        process = _matches(payload, demo, demo_data_dir)
        if process is None:
            if not psutil.pid_exists(int(payload.get("pid") or -1)):
                path.unlink(missing_ok=True)
            continue
        matched.append((path, payload, process))
        try:
            descendants = process.children(recursive=True)
        except (psutil.Error, OSError):
            descendants = []
        for target in [process, *descendants]:
            try:
                force_targets[target.pid] = (
                    target.create_time(),
                    str(Path(target.exe()).resolve()),
                )
            except (psutil.Error, OSError):
                continue

    for _path, _payload, process in matched:
        try:
            process.send_signal(signal.SIGTERM)
        except psutil.Error:
            pass

    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        if not any(psutil.pid_exists(pid) for pid in force_targets):
            break
        time.sleep(0.1)

    for pid, (started_at, executable) in force_targets.items():
        try:
            process = psutil.Process(pid)
            if abs(process.create_time() - started_at) > 0.001:
                continue
            if executable and str(Path(process.exe()).resolve()) != executable:
                continue
            process.kill()
        except (psutil.Error, OSError):
            continue

    for path, payload, _process in matched:
        if _matches(payload, demo, demo_data_dir) is None:
            path.unlink(missing_ok=True)
    return len(matched)


def main() -> int:
    """解析 record 或 cleanup 子命令。"""
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    record_parser = subparsers.add_parser("record")
    record_parser.add_argument("runtime_dir", type=Path)
    record_parser.add_argument("name")
    record_parser.add_argument("pid", type=int)
    record_parser.add_argument("demo")
    record_parser.add_argument("marker")
    cleanup_parser = subparsers.add_parser("cleanup")
    cleanup_parser.add_argument("runtime_dir", type=Path)
    cleanup_parser.add_argument("demo")
    cleanup_parser.add_argument("demo_data_dir", type=Path)
    args = parser.parse_args()
    if args.command == "record":
        record(args.runtime_dir, args.name, args.pid, args.demo, args.marker)
        return 0
    count = cleanup(args.runtime_dir, args.demo, args.demo_data_dir)
    print(f">>> 已请求关闭 {count} 个身份匹配的登记进程")
    return 0


if __name__ == "__main__":
    sys.exit(main())
