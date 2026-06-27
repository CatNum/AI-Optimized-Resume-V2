#!/usr/bin/env python3
"""一次性迁移：对齐 pipeline meta.current_phase、explore_closure 和 state。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# 允许从仓库根目录或 backend/ 目录运行。
_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from career_os.config import settings
from career_os.harness.pipeline_phase_transition import (
    prior_worker_segment_complete,
)
from career_os.platform.pipeline_constants import PIPELINE_PHASES

PHASE_ORDER = list(PIPELINE_PHASES)


def _phase_rank(phase: str) -> int:
    """处理phase rank。"""
    try:
        return PHASE_ORDER.index(phase)
    except ValueError:
        return -1


def _prior_worker_legacy_complete(prior_results: dict[str, Any], worker_id: str) -> bool:
    """迁移兼容：旧 prior_results 可能没有 phase_status，但包含 user_visible_summary。"""
    if prior_worker_segment_complete(prior_results, worker_id):
        return True
    blob = (prior_results or {}).get(worker_id)
    return isinstance(blob, dict) and bool(str(blob.get("user_visible_summary") or "").strip())


def infer_phase_after_repeat_decline_legacy(prior_results: dict[str, Any]) -> str:
    """推断phase after repeat decline legacy。"""
    if _prior_worker_legacy_complete(prior_results, "opportunity"):
        return "jd_analysis"
    return "market"


def infer_target_phase(
    meta: dict[str, Any], state: dict[str, Any] | None
) -> tuple[str, bool]:
    """返回 (target_phase, explore_closure_completed)。"""
    state = state or {}
    prior = state.get("prior_results") or {}
    flags = (state.get("gates") or {}).get("flags") or {}
    current = meta.get("current_phase") or "explore"

    closure_completed = bool((state.get("explore_closure") or {}).get("completed"))
    gate_confirmed = bool(
        state.get("explore_gate_confirmed") or flags.get("explore_gate_confirmed")
    )

    if flags.get("explore_repeat_declined") or closure_completed or gate_confirmed:
        target = infer_phase_after_repeat_decline_legacy(prior)
        return target, True

    if prior_worker_segment_complete(prior, "opportunity"):
        return "jd_analysis", closure_completed
    if prior_worker_segment_complete(prior, "market"):
        return "market", closure_completed

    return current, closure_completed


def migrate_list(
    list_dir: Path, *, data_dir: Path, apply: bool
) -> dict[str, Any] | None:
    """迁移list。"""
    meta_path = list_dir / "meta.json"
    if not meta_path.exists():
        return None
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if meta.get("list_type") != "pipeline":
        return None

    session_id = meta.get("session_id")
    state: dict[str, Any] | None = None
    state_path: Path | None = None
    if session_id:
        state_path = data_dir / "sessions" / session_id / "state.json"
        if state_path.exists():
            state = json.loads(state_path.read_text(encoding="utf-8"))

    target_phase, closure_done = infer_target_phase(meta, state)
    current_phase = meta.get("current_phase") or "explore"
    changes: dict[str, Any] = {"list_id": meta.get("list_id"), "from_phase": current_phase}

    if _phase_rank(target_phase) > _phase_rank(current_phase):
        changes["to_phase"] = target_phase
    elif target_phase != current_phase and current_phase == "explore":
        changes["to_phase"] = target_phase

    state_patch: dict[str, Any] = {}
    if state and closure_done:
        closure = dict(state.get("explore_closure") or {})
        if not closure.get("completed"):
            state_patch["explore_closure.completed"] = True
        flags = (state.get("gates") or {}).get("flags") or {}
        if not state.get("explore_gate_confirmed") and (
            flags.get("explore_repeat_declined") or flags.get("explore_gate_confirmed")
        ):
            state_patch["explore_gate_confirmed"] = True

    if not changes.get("to_phase") and not state_patch:
        return None

    changes["state_patch"] = state_patch
    if not apply:
        return changes

    if changes.get("to_phase"):
        meta["current_phase"] = changes["to_phase"]
        meta_path.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    if state_path and state_patch and state is not None:
        if state_patch.get("explore_closure.completed"):
            closure = dict(state.get("explore_closure") or {})
            closure["completed"] = True
            closure["gate_pending"] = False
            state["explore_closure"] = closure
        if state_patch.get("explore_gate_confirmed"):
            state["explore_gate_confirmed"] = True
            gates = dict(state.get("gates") or {})
            flags = dict(gates.get("flags") or {})
            flags["explore_gate_confirmed"] = True
            gates["flags"] = flags
            state["gates"] = gates
        state_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    return changes


def main() -> int:
    """执行脚本入口。"""
    parser = argparse.ArgumentParser(description="Migrate pipeline current_phase state")
    parser.add_argument(
        "--data-dir",
        default=settings.data_dir,
        help="Data root, e.g. ./data/demo for make dev demo (default: settings.data_dir)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print changes only")
    parser.add_argument("--apply", action="store_true", help="Write changes to disk")
    args = parser.parse_args()
    if not args.dry_run and not args.apply:
        parser.error("Specify --dry-run or --apply")

    data_dir = Path(args.data_dir).resolve()
    tasks_root = data_dir / "tasks"
    if not tasks_root.exists():
        print(f"No tasks dir: {tasks_root}")
        print("提示: demo 环境请使用 --data-dir ./data/demo（与 make dev demo 的 DATA_DIR 一致）")
        return 0

    count = 0
    for list_dir in sorted(tasks_root.iterdir()):
        if not list_dir.is_dir() or list_dir.name.startswith("_"):
            continue
        result = migrate_list(
            list_dir, data_dir=data_dir, apply=args.apply and not args.dry_run
        )
        if result:
            count += 1
            print(json.dumps(result, ensure_ascii=False))

    mode = "dry-run" if args.dry_run else "apply"
    print(f"{mode}: {count} list(s) updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
