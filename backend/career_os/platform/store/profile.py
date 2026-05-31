import json
import threading
from pathlib import Path
from typing import Any

from career_os.config import settings

_lock = threading.Lock()

_MINIMAL_PROFILE: dict[str, Any] = {
    "meta": {"version": 1, "updated_at": None},
    "basic": {},
}


class ProfileStore:
    def __init__(self) -> None:
        self._data_dir = Path(settings.data_dir)
        self._profile_path = self._data_dir / "profile.json"
        self._example_path = self._repo_root() / "data" / "profile.example.json"

    @staticmethod
    def _repo_root() -> Path:
        return Path(__file__).resolve().parents[4]

    def _ensure_profile(self) -> None:
        self._data_dir.mkdir(parents=True, exist_ok=True)
        if self._profile_path.exists():
            return
        if self._example_path.exists():
            self._profile_path.write_text(
                self._example_path.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
        else:
            self._profile_path.write_text(
                json.dumps(_MINIMAL_PROFILE, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    def _load(self) -> dict[str, Any]:
        self._ensure_profile()
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
