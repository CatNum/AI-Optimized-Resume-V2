import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class SkillIndexEntry:
    name: str
    description: str
    when_to_use: list[str]
    allowed_workers: list[str]
    modes: list[str]


@dataclass
class SkillBundle:
    name: str
    mode: str | None
    body: str
    attachments: list[str]
    hash: str
    allowed_workers: list[str]


@dataclass
class SkillRegistryError:
    code: str
    message: str


class SkillRegistry:
    _FRONT_MATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

    def __init__(self, skills_dir: Path | None = None) -> None:
        self._repo_root = self._find_repo_root()
        self._skills_dir = skills_dir or (self._repo_root / ".agent" / "skills")
        self._entries: dict[str, SkillIndexEntry] = {}
        self._skill_paths: dict[str, Path] = {}
        self._mode_workers: dict[str, dict[str, list[str]]] = {}
        self.reload()

    @staticmethod
    def _find_repo_root() -> Path:
        current = Path(__file__).resolve()
        for parent in current.parents:
            if (parent / ".agent" / "skills").exists():
                return parent
        return current.parents[4]

    def reload(self) -> None:
        self._entries.clear()
        self._skill_paths.clear()
        self._mode_workers.clear()
        if not self._skills_dir.exists():
            return
        for skill_path in sorted(self._skills_dir.glob("*/SKILL.md")):
            meta, _body = self._parse_skill_file(skill_path)
            name = meta.get("name") or skill_path.parent.name
            modes_meta = meta.get("modes") or {}
            modes = list(modes_meta.keys()) if isinstance(modes_meta, dict) else []
            allowed_workers = sorted(
                {
                    worker
                    for mode_cfg in (
                        modes_meta.values()
                        if isinstance(modes_meta, dict)
                        else []
                    )
                    for worker in (
                        mode_cfg.get("allowed_workers", [])
                        if isinstance(mode_cfg, dict)
                        else []
                    )
                }
            )
            self._entries[name] = SkillIndexEntry(
                name=name,
                description=str(meta.get("description", "")).strip(),
                when_to_use=[],
                allowed_workers=allowed_workers,
                modes=modes,
            )
            self._skill_paths[name] = skill_path
            if isinstance(modes_meta, dict):
                self._mode_workers[name] = {
                    mode: cfg.get("allowed_workers", [])
                    for mode, cfg in modes_meta.items()
                    if isinstance(cfg, dict)
                }

    def list_skills(self) -> list[SkillIndexEntry]:
        return list(self._entries.values())

    def load_skill(
        self,
        name: str,
        *,
        mode: str | None = None,
        worker_id: str | None = None,
    ) -> SkillBundle | SkillRegistryError:
        skill_path = self._skill_paths.get(name)
        if skill_path is None:
            return SkillRegistryError("skill_not_found", f"Skill {name} not found")

        meta, body = self._parse_skill_file(skill_path)
        allowed = self._allowed_workers_for_mode(name, mode, meta)
        if worker_id and worker_id not in allowed:
            return SkillRegistryError(
                "skill_worker_rejected",
                f"Worker {worker_id} not allowed for skill {name} mode {mode}",
            )

        content_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]
        return SkillBundle(
            name=name,
            mode=mode,
            body=body.strip(),
            attachments=[],
            hash=content_hash,
            allowed_workers=allowed,
        )

    def _allowed_workers_for_mode(
        self, name: str, mode: str | None, meta: dict[str, Any]
    ) -> list[str]:
        if mode:
            mode_workers = self._mode_workers.get(name, {})
            return list(mode_workers.get(mode, []))
        modes_meta = meta.get("modes") or {}
        if isinstance(modes_meta, dict):
            workers: set[str] = set()
            for cfg in modes_meta.values():
                if isinstance(cfg, dict):
                    workers.update(cfg.get("allowed_workers", []))
            return sorted(workers)
        return list(self._entries.get(name, SkillIndexEntry("", "", [], [], [])).allowed_workers)

    def _parse_skill_file(self, path: Path) -> tuple[dict[str, Any], str]:
        text = path.read_text(encoding="utf-8")
        match = self._FRONT_MATTER_RE.match(text)
        if not match:
            return {}, text
        front_matter = match.group(1)
        body = text[match.end() :]
        meta = self._parse_simple_yaml(front_matter)
        return meta, body

    @staticmethod
    def _parse_simple_yaml(text: str) -> dict[str, Any]:
        result: dict[str, Any] = {}
        current_key: str | None = None
        current_mode: str | None = None
        modes: dict[str, dict[str, list[str]]] = {}

        for raw_line in text.splitlines():
            line = raw_line.rstrip()
            if not line.strip() or line.strip().startswith("#"):
                continue
            if line.startswith("  ") and current_mode and line.strip().startswith(
                "allowed_workers:"
            ):
                workers = SkillRegistry._parse_inline_list(line.split(":", 1)[1])
                modes[current_mode]["allowed_workers"] = workers
                continue
            if not line.startswith(" ") and line.endswith(":"):
                key = line[:-1].strip()
                if key == "modes":
                    current_key = "modes"
                    result["modes"] = modes
                    current_mode = None
                    continue
                current_key = key
                current_mode = None
                if key == "name":
                    result["name"] = ""
                continue
            if current_key == "modes" and line.startswith("  ") and line.rstrip().endswith(":"):
                current_mode = line.strip()[:-1]
                modes[current_mode] = {}
                continue
            if current_key == "name" and ":" in line:
                result["name"] = line.split(":", 1)[1].strip()
            elif current_key == "description" and ":" in line:
                value = line.split(":", 1)[1].strip()
                if value == ">-" or value == "|":
                    result["description"] = ""
                else:
                    result["description"] = value.strip('"')
            elif current_key == "description" and line.startswith("  "):
                prev = str(result.get("description", ""))
                chunk = line.strip()
                result["description"] = f"{prev} {chunk}".strip()

        if modes:
            result["modes"] = modes
        return result

    @staticmethod
    def _parse_inline_list(value: str) -> list[str]:
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            if not inner:
                return []
            return [item.strip().strip('"').strip("'") for item in inner.split(",")]
        return []
