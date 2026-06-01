from dataclasses import dataclass
from pathlib import Path
from typing import Any

from career_os.config import settings
from career_os.platform.store.output import OutputStore
from career_os.platform.store.profile import ProfileStore
_LEVEL_ORDER = ["保守", "标准", "进取"]


@dataclass
class OutputsToolError:
    code: str
    message: str


def _output_root() -> Path:
    return Path(settings.output_dir).resolve()


def canonical_output_prefix() -> str:
    """Logical URL/index prefix (e.g. output/demo), not an absolute filesystem path."""
    configured = Path(settings.output_dir)
    if not configured.is_absolute():
        return configured.as_posix().removeprefix("./")
    parts = configured.resolve().parts
    for idx, part in enumerate(parts):
        if part == "output":
            return "/".join(parts[idx:])
    return configured.name or "output"


def strip_canonical_prefix(path: str | Path) -> str:
    posix = Path(path).as_posix().lstrip("/")
    canonical = canonical_output_prefix()
    while posix.startswith(f"{canonical}/"):
        posix = posix[len(canonical) + 1 :]
    if posix == canonical:
        return ""
    return posix


def relative_output_path(path: str | Path) -> Path | None:
    output_root = _output_root()
    raw = Path(path)

    if raw.is_absolute():
        try:
            return raw.resolve().relative_to(output_root)
        except ValueError:
            pass

    stripped = strip_canonical_prefix(raw)
    if stripped:
        return Path(stripped)

    posix = raw.as_posix()
    if posix.startswith("output/"):
        without_output = Path(*Path(posix).parts[1:])
        for candidate in (
            output_root / without_output,
            output_root / Path(*without_output.parts[1:])
            if without_output.parts
            and without_output.parts[0] == Path(settings.output_dir).name
            else None,
        ):
            if candidate is not None and candidate.exists():
                try:
                    return candidate.resolve().relative_to(output_root)
                except ValueError:
                    continue
        if without_output.parts and without_output.parts[0] == Path(settings.output_dir).name:
            return Path(*without_output.parts[1:])
        return without_output

    env_name = Path(settings.output_dir).name
    if raw.parts and raw.parts[0] == env_name:
        return Path(*raw.parts[1:])

    return raw if raw.parts else None


def normalize_output_path(path: str | Path) -> str:
    canonical = canonical_output_prefix()
    resolved_file = resolve_output_file(path)
    if resolved_file is not None:
        rel = resolved_file.relative_to(_output_root())
        return f"{canonical}/{rel.as_posix()}"

    rel = relative_output_path(path)
    if rel is None or str(rel) in ("", "."):
        return strip_canonical_prefix(path) or Path(path).as_posix()
    return f"{canonical}/{rel.as_posix()}"


def dedupe_outputs_index(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for entry in entries:
        path = entry.get("path")
        if not path:
            continue
        key = normalize_output_path(path)
        if key in seen:
            continue
        seen.add(key)
        deduped.append({**entry, "path": key})
    return deduped


def resolve_output_file(path: str | Path) -> Path | None:
    output_root = _output_root()
    raw = Path(path)
    candidates: list[Path] = []

    if raw.is_absolute():
        candidates.append(raw.resolve())

    rel = relative_output_path(raw)
    if rel is not None:
        candidates.append(output_root / rel)

    stripped = strip_canonical_prefix(raw)
    if stripped:
        candidates.append(output_root / stripped)

    candidates.append(output_root / raw)

    seen: set[str] = set()
    unique_candidates: list[Path] = []
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        unique_candidates.append(candidate)

    html_candidates: list[Path] = []
    for candidate in unique_candidates:
        if candidate.suffix.lower() != ".html":
            html_candidates.append(candidate.with_suffix(".html"))
            html_candidates.append(Path(f"{candidate}.html"))
    unique_candidates.extend(html_candidates)

    for candidate in unique_candidates:
        if candidate.is_file():
            return candidate.resolve()
    return None


def infer_optimization_level(filename: str) -> str | None:
    for level in _LEVEL_ORDER:
        if level in filename:
            return level
    return None


def scan_disk_outputs() -> list[dict[str, Any]]:
    store = OutputStore()
    entries: list[dict[str, Any]] = []
    for file_path in store.list_all_files():
        path_str = normalize_output_path(file_path)
        entries.append(
            {
                "path": path_str,
                "optimization_level": infer_optimization_level(file_path.name),
            }
        )
    return entries


def merge_outputs_index(indexed: list[dict[str, Any]]) -> list[dict[str, Any]]:
    indexed_by_path = {
        normalize_output_path(entry["path"]): entry
        for entry in dedupe_outputs_index(indexed)
        if entry.get("path")
    }
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for disk_entry in scan_disk_outputs():
        path = disk_entry["path"]
        if path in seen:
            continue
        seen.add(path)
        if path in indexed_by_path:
            merged.append({**disk_entry, **indexed_by_path[path], "path": path})
        else:
            merged.append(disk_entry)
    return merged


def register_outputs_index(
    actor: str, args: dict[str, Any]
) -> OutputsToolError | dict[str, Any]:
    if actor != "asset":
        return OutputsToolError("tool_not_allowed", "register_outputs_index is asset-only")
    deliveries = args.get("deliveries") or []
    dedupe_by_path = args.get("dedupe_by_path", True)
    profile = ProfileStore()
    raw_existing = profile.get(["outputs_index"]).get("outputs_index") or []
    existing = dedupe_outputs_index(raw_existing)
    existing_paths = {normalize_output_path(e["path"]) for e in existing}
    registered: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for item in deliveries:
        resolved_file = resolve_output_file(item["path"])
        if resolved_file is None:
            return OutputsToolError("output_missing", f"Missing file {item['path']}")
        path_str = normalize_output_path(resolved_file)
        if dedupe_by_path and path_str in existing_paths:
            skipped.append({"path": path_str, "reason": "already_registered"})
            continue
        entry = {
            "path": path_str,
            "optimization_level": item.get("optimization_level"),
            "created_at": item.get("created_at"),
        }
        existing.append(entry)
        existing_paths.add(path_str)
        registered.append(entry)
    profile.patch([{"path": "outputs_index", "value": existing, "op": "set"}])
    return {"registered": registered, "skipped": skipped}


def delete_output(actor: str, args: dict[str, Any]) -> OutputsToolError | dict[str, Any]:
    if actor != "asset":
        return OutputsToolError("tool_not_allowed", "delete_output is asset-only")
    path = Path(args["path"])
    store = OutputStore()
    profile = ProfileStore()
    if not store.delete(path):
        return OutputsToolError("output_missing", f"Cannot delete {path}")
    existing = profile.get(["outputs_index"]).get("outputs_index") or []
    filtered = [e for e in existing if normalize_output_path(e.get("path", "")) != normalize_output_path(path)]
    profile.patch([{"path": "outputs_index", "value": filtered, "op": "set"}])
    return {"deleted": str(path)}
