#!/usr/bin/env python3
"""One-time migration: move session-scoped fields out of profile.json."""

from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from career_os.config import settings


SESSION_SCOPED_PROFILE_FIELDS = {
    "exploration": (
        "completed_at",
        "inner_needs",
        "desires",
        "career_needs",
        "priorities_now",
        "current_problems",
        "summary",
        "intake",
        "intake_baseline",
    ),
    "market": ("role_families", "trend_notes", "opportunity_snapshots"),
    "strategy": ("path_options", "selected_strategy", "risk_notes", "last_reviewed_at"),
}


def _read_json(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    """_read_json（内部函数 read json）的函数说明。

    path（参数）、default（参数）用于向该函数传入运行所需的数据。

    该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
    if not path.exists():
        return deepcopy(default or {})
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
    """_write_json（内部函数 write json）的函数说明。

    path（参数）、data（参数）用于向该函数传入运行所需的数据。

    该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _session_dirs(data_dir: Path) -> list[Path]:
    """_session_dirs（内部函数 session dirs）的函数说明。

    data_dir（参数）用于向该函数传入运行所需的数据。

    该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
    root = data_dir / "sessions"
    if not root.exists():
        return []
    return sorted([p for p in root.iterdir() if p.is_dir() and p.name.startswith("sess_")])


def _choose_target_session(data_dir: Path) -> str | None:
    """_choose_target_session（内部函数 choose target session）的函数说明。

    data_dir（参数）用于向该函数传入运行所需的数据。

    该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
    sessions = _session_dirs(data_dir)
    if len(sessions) == 1:
        return sessions[0].name
    return None


def migrate(data_dir: Path, *, apply: bool) -> dict[str, Any]:
    """migrate（migrate）的函数说明。

    data_dir（参数）、apply（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    profile_path = data_dir / "profile.json"
    profile = _read_json(profile_path, default={})
    if not profile:
        return {"changed": False, "reason": "profile_missing"}

    target_session = _choose_target_session(data_dir)
    orphan: dict[str, Any] = {"session_scoped_from_profile": {}, "note": "ambiguous_session_target"}
    state: dict[str, Any] = {}
    artifacts: dict[str, Any] = {}

    if target_session:
        state = _read_json(
            data_dir / "sessions" / target_session / "state.json",
            default={"session_id": target_session},
        )
        artifacts = _read_json(
            data_dir / "sessions" / target_session / "artifacts.json",
            default={
                "version": 1,
                "session_id": target_session,
                "exploration": {},
                "market": {},
                "opportunity": {},
                "strategy": {},
                "resume_outputs": [],
            },
        )

    changes: dict[str, Any] = {
        "target_session": target_session,
        "migrated_fields": [],
        "profile_cleanups": [],
    }

    exploration = dict(profile.get("exploration") or {})
    exploration_payload = {}
    for key in SESSION_SCOPED_PROFILE_FIELDS["exploration"]:
        if key in exploration and exploration.get(key) not in (None, "", {}, []):
            exploration_payload[key] = exploration.get(key)
            changes["migrated_fields"].append(f"exploration.{key}")
            exploration.pop(key, None)
            changes["profile_cleanups"].append(f"exploration.{key}")
    profile["exploration"] = exploration

    market_payload = {}
    market = dict(profile.get("market") or {})
    for key in SESSION_SCOPED_PROFILE_FIELDS["market"]:
        if key in market and market.get(key) not in (None, "", {}, []):
            market_payload[key] = market.get(key)
            changes["migrated_fields"].append(f"market.{key}")
            market[key] = [] if isinstance(market.get(key), list) else {}
            changes["profile_cleanups"].append(f"market.{key}")
    profile["market"] = market

    strategy_payload = {}
    strategy = dict(profile.get("strategy") or {})
    for key in SESSION_SCOPED_PROFILE_FIELDS["strategy"]:
        if key in strategy and strategy.get(key) not in (None, "", {}, []):
            strategy_payload[key] = strategy.get(key)
            changes["migrated_fields"].append(f"strategy.{key}")
            if key == "last_reviewed_at":
                strategy[key] = None
            else:
                strategy[key] = [] if isinstance(strategy.get(key), list) else {}
            changes["profile_cleanups"].append(f"strategy.{key}")
    profile["strategy"] = strategy

    career = dict(profile.get("career") or {})
    jd_override = career.get("jd_override") or []
    if jd_override:
        changes["migrated_fields"].append("career.jd_override")
        changes["profile_cleanups"].append("career.jd_override")
        career["jd_override"] = []
    profile["career"] = career

    if target_session:
        if exploration_payload:
            artifacts_explore = dict(artifacts.get("exploration") or {})
            if isinstance(exploration_payload.get("intake"), dict):
                state["intake_status"] = exploration_payload["intake"]
                artifacts_explore["intake"] = exploration_payload["intake"]
            for key in (
                "inner_needs",
                "desires",
                "career_needs",
                "priorities_now",
                "current_problems",
                "summary",
                "intake_baseline",
            ):
                if key in exploration_payload:
                    artifacts_explore[key] = exploration_payload[key]
            if exploration_payload.get("completed_at"):
                state["explore_completed_at"] = exploration_payload["completed_at"]
            artifacts["exploration"] = artifacts_explore
        if market_payload:
            artifacts["market"] = {**(artifacts.get("market") or {}), **market_payload}
        if strategy_payload:
            artifacts["strategy"] = {**(artifacts.get("strategy") or {}), **strategy_payload}
        if jd_override:
            state["jd_override"] = jd_override
    else:
        orphan["session_scoped_from_profile"]["exploration"] = exploration_payload
        orphan["session_scoped_from_profile"]["market"] = market_payload
        orphan["session_scoped_from_profile"]["strategy"] = strategy_payload
        orphan["session_scoped_from_profile"]["jd_override"] = jd_override

    changed = bool(changes["migrated_fields"])
    changes["changed"] = changed
    if not apply or not changed:
        return changes

    _write_json(profile_path, profile)
    if target_session:
        _write_json(data_dir / "sessions" / target_session / "state.json", state)
        _write_json(data_dir / "sessions" / target_session / "artifacts.json", artifacts)
    else:
        _write_json(data_dir / "orphan_artifacts.json", orphan)
    return changes


def main() -> int:
    """main（main）的函数说明。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    parser = argparse.ArgumentParser(description="Migrate profile/session boundary")
    parser.add_argument("--data-dir", default=settings.data_dir, help="Data root directory")
    parser.add_argument("--dry-run", action="store_true", help="Print changes only")
    parser.add_argument("--apply", action="store_true", help="Write changes")
    args = parser.parse_args()
    if not args.dry_run and not args.apply:
        parser.error("Specify --dry-run or --apply")
    data_dir = Path(args.data_dir).resolve()
    result = migrate(data_dir, apply=args.apply and not args.dry_run)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

