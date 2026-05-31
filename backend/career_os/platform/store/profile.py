import json
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any

from career_os.config import settings

_lock = threading.Lock()

# 空档案骨架：仅结构，无业务默认值；不复制 profile.example.json
EMPTY_PROFILE: dict[str, Any] = {
    "meta": {"version": 1, "updated_at": None},
    "basic": {},
    "skills": {"primary": [], "proficiency_notes": ""},
    "intent": {},
    "constraints": {},
    "exploration": {
        "completed_at": None,
        "inner_needs": "",
        "desires": "",
        "career_needs": "",
        "priorities_now": "",
        "current_problems": "",
        "summary": "",
    },
    "career": {
        "current_assessment": {},
        "next_hop": {},
        "horizon_3_5y": {},
        "selected_path_id": "",
        "jd_override": [],
    },
    "capability": {
        "skill_graph": {},
        "transfer_paths": [],
        "evidence_gaps": [],
        "portfolio_summary": "",
    },
    "market": {
        "role_families": [],
        "trend_notes": [],
        "opportunity_snapshots": [],
    },
    "strategy": {
        "path_options": [],
        "selected_strategy": {},
        "risk_notes": [],
        "last_reviewed_at": None,
    },
    "resume": {
        "source_path": "",
        "last_optimization_levels": [],
        "experience_bank": {"items": [], "narrative_summary": ""},
    },
    "preference_tags": {"selected": [], "custom": []},
    "outputs_index": [],
}


class ProfileStore:
    def __init__(self) -> None:
        self._data_dir = Path(settings.data_dir)
        self._profile_path = self._data_dir / "profile.json"

    def ensure_empty_profile(self) -> bool:
        """若 profile.json 不存在，写入空结构（无业务默认值）。"""
        self._data_dir.mkdir(parents=True, exist_ok=True)
        if self._profile_path.exists():
            return False
        self._save(deepcopy(EMPTY_PROFILE))
        return True

    def _load(self) -> dict[str, Any]:
        self.ensure_empty_profile()
        with self._profile_path.open(encoding="utf-8") as f:
            return json.load(f)

    def _save(self, data: dict[str, Any]) -> None:
        self._data_dir.mkdir(parents=True, exist_ok=True)
        with self._profile_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def get(self, paths: list[str]) -> dict[str, Any]:
        with _lock:
            data = self._load()
            result: dict[str, Any] = {}
            for path in paths:
                value = _get_by_path(data, path)
                _merge_path(result, path, value)
            return result

    def patch(self, patches: list[dict[str, Any]]) -> None:
        with _lock:
            data = self._load()
            for patch in patches:
                if patch.get("op") != "set":
                    continue
                _set_by_path(data, patch["path"], patch["value"])
            self._save(data)


def _get_by_path(data: dict[str, Any], path: str) -> Any:
    current: Any = data
    for key in path.split("."):
        if not isinstance(current, dict) or key not in current:
            return {}
        current = current[key]
    return current


def _set_by_path(data: dict[str, Any], path: str, value: Any) -> None:
    keys = path.split(".")
    current = data
    for key in keys[:-1]:
        if key not in current or not isinstance(current[key], dict):
            current[key] = {}
        current = current[key]
    current[keys[-1]] = value


def _merge_path(target: dict[str, Any], path: str, value: Any) -> None:
    keys = path.split(".")
    current = target
    for key in keys[:-1]:
        if key not in current:
            current[key] = {}
        current = current[key]
    current[keys[-1]] = value
