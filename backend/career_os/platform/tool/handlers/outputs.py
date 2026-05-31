from dataclasses import dataclass
from pathlib import Path
from typing import Any

from career_os.platform.store.output import OutputStore
from career_os.platform.store.profile import ProfileStore


@dataclass
class OutputsToolError:
    code: str
    message: str


def register_outputs_index(
    actor: str, args: dict[str, Any]
) -> OutputsToolError | dict[str, Any]:
    if actor != "asset":
        return OutputsToolError("tool_not_allowed", "register_outputs_index is asset-only")
    deliveries = args.get("deliveries") or []
    profile = ProfileStore()
    existing = profile.get(["outputs_index"]).get("outputs_index") or []
    registered: list[dict[str, Any]] = []
    for item in deliveries:
        path = Path(item["path"])
        if not path.exists():
            return OutputsToolError("output_missing", f"Missing file {path}")
        entry = {
            "path": str(path),
            "optimization_level": item.get("optimization_level"),
            "created_at": item.get("created_at"),
        }
        existing.append(entry)
        registered.append(entry)
    profile.patch([{"path": "outputs_index", "value": existing, "op": "set"}])
    return {"registered": registered}


def delete_output(actor: str, args: dict[str, Any]) -> OutputsToolError | dict[str, Any]:
    if actor != "asset":
        return OutputsToolError("tool_not_allowed", "delete_output is asset-only")
    path = Path(args["path"])
    store = OutputStore()
    profile = ProfileStore()
    if not store.delete(path):
        return OutputsToolError("output_missing", f"Cannot delete {path}")
    existing = profile.get(["outputs_index"]).get("outputs_index") or []
    filtered = [e for e in existing if e.get("path") != str(path)]
    profile.patch([{"path": "outputs_index", "value": filtered, "op": "set"}])
    return {"deleted": str(path)}
