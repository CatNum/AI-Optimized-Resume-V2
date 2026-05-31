from dataclasses import dataclass
from pathlib import Path
from typing import Any

from career_os.config import settings
from career_os.platform.store.output import OutputStore
from career_os.platform.store.profile import ProfileStore


@dataclass
class OutputsToolError:
    code: str
    message: str


def _output_root() -> Path:
    return Path(settings.output_dir).resolve()


def normalize_output_path(path: str | Path) -> str:
    raw = Path(path)
    output_dir = Path(settings.output_dir)
    output_root = _output_root()

    if raw.is_absolute():
        resolved = raw.resolve()
    elif raw.parts and raw.parts[0] == output_dir.name:
        resolved = output_root.joinpath(*raw.parts[1:]).resolve()
    else:
        resolved = (output_root / raw).resolve()

    try:
        rel = resolved.relative_to(output_root)
        return (output_dir / rel).as_posix()
    except ValueError:
        return raw.as_posix()


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
    raw = Path(path)
    output_dir = Path(settings.output_dir)
    output_root = _output_root()
    candidates: list[Path] = []
    if raw.is_absolute():
        candidates.append(raw)
    else:
        if raw.parts and raw.parts[0] == output_dir.name:
            candidates.append(output_root.joinpath(*raw.parts[1:]))
        candidates.extend([output_root / raw, raw])
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return None


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
