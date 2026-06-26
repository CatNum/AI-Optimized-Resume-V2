import json
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any

from career_os.config import settings

_lock = threading.Lock()
_FORBIDDEN_PREFIXES = ("market.", "strategy.", "career.jd_override")
_ALLOWED_EXPLORATION_FIELDS = {
    "completed_at",
    "inner_needs",
    "desires",
    "career_needs",
    "priorities_now",
    "current_problems",
    "summary",
    "intake_baseline",
    "intake",
}
_ALLOWED_PREFIXES = (
    "basic.",
    "skills.",
    "intent.",
    "constraints.",
    "capability.",
    "resume.source_",
    "resume.experience_bank.",
    "preference_tags.",
)

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
        "intake": {
            "submitted_at": None,
        },
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
    """ProfileStore（用户画像存储）负责读写 profile.json。

    profile.json 保存 basic、intent、exploration、resume、market、strategy 等长期档案。
    该类提供按路径读取和受限 patch 写入能力，避免 Worker 随意改写敏感区域。
    """

    def __init__(self) -> None:
        """__init__（初始化对象）的函数说明。

        该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
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
        """_load（内部函数 load）的函数说明。

        该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
        self.ensure_empty_profile()
        with self._profile_path.open(encoding="utf-8") as f:
            return json.load(f)

    def _save(self, data: dict[str, Any]) -> None:
        """_save（内部函数 save）的函数说明。

        data（参数）用于向该函数传入运行所需的数据。

        该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
        self._data_dir.mkdir(parents=True, exist_ok=True)
        with self._profile_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def get(self, paths: list[str]) -> dict[str, Any]:
        """按路径读取用户画像片段。

        paths（路径列表）是 profile.json 中要读取的顶层或点分路径。
        返回值是只包含请求路径的 dict，用于给 Agent/Worker 提供最小必要档案。
        """
        with _lock:
            data = self._load()
            result: dict[str, Any] = {}
            for path in paths:
                value = _get_by_path(data, path)
                _merge_path(result, path, value)
            return result

    def patch(self, patches: list[dict[str, Any]]) -> None:
        """按补丁写入用户画像。

        patches（补丁列表）每项包含 path、value、op；当前只处理 op=set。
        该方法会先校验路径权限，再写回 profile.json。
        """
        with _lock:
            data = self._load()
            for patch in patches:
                if patch.get("op") != "set":
                    continue
                path = str(patch["path"])
                value = patch["value"]
                _validate_patch_path(path, value)
                _set_by_path(data, path, value)
            self._save(data)


def _validate_patch_path(path: str, value: Any) -> None:
    """_validate_patch_path（内部函数 validate patch path）的函数说明。

    path（参数）、value（参数）用于向该函数传入运行所需的数据。

    该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
    if path == "outputs_index":
        _validate_outputs_index(value)
        return
    if path == "exploration.intake" or path in {
        f"exploration.{field}" for field in _ALLOWED_EXPLORATION_FIELDS
    }:
        return
    if path.startswith(_FORBIDDEN_PREFIXES):
        raise ValueError(f"profile_path_forbidden:{path}")
    if path.startswith(_ALLOWED_PREFIXES):
        return
    # Allow exact roots for limited updates.
    if path in {"basic", "skills", "intent", "constraints", "capability", "preference_tags"}:
        return
    if path in {"resume.source_text", "resume.source_path"}:
        return
    if path.startswith("resume.experience_bank"):
        return
    raise ValueError(f"profile_path_forbidden:{path}")


def _validate_outputs_index(value: Any) -> None:
    """_validate_outputs_index（内部函数 validate outputs index）的函数说明。

    value（参数）用于向该函数传入运行所需的数据。

    该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
    if not isinstance(value, list):
        raise ValueError("profile_path_forbidden:outputs_index")
    for idx, item in enumerate(value):
        if not isinstance(item, dict):
            raise ValueError(f"profile_path_forbidden:outputs_index[{idx}]")
        if not str(item.get("session_id") or "").strip():
            raise ValueError(f"profile_path_forbidden:outputs_index[{idx}].session_id")


def _get_by_path(data: dict[str, Any], path: str) -> Any:
    """_get_by_path（内部函数 get by path）的函数说明。

    data（参数）、path（参数）用于向该函数传入运行所需的数据。

    该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
    current: Any = data
    for key in path.split("."):
        if not isinstance(current, dict) or key not in current:
            return {}
        current = current[key]
    return current


def _set_by_path(data: dict[str, Any], path: str, value: Any) -> None:
    """_set_by_path（内部函数 set by path）的函数说明。

    data（参数）、path（参数）、value（参数）用于向该函数传入运行所需的数据。

    该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
    keys = path.split(".")
    current = data
    for key in keys[:-1]:
        if key not in current or not isinstance(current[key], dict):
            current[key] = {}
        current = current[key]
    current[keys[-1]] = value


def _merge_path(target: dict[str, Any], path: str, value: Any) -> None:
    """_merge_path（内部函数 merge path）的函数说明。

    target（参数）、path（参数）、value（参数）用于向该函数传入运行所需的数据。

    该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
    keys = path.split(".")
    current = target
    for key in keys[:-1]:
        if key not in current:
            current[key] = {}
        current = current[key]
    current[keys[-1]] = value
