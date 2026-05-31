from dataclasses import dataclass
from typing import Any

from career_os.platform.store.profile import ProfileStore

PROFILE_PATCH_WHITELIST: dict[str, list[str]] = {
    "identity": ["exploration."],
    "capability": ["exploration.", "resume.experience_bank.", "capability."],
    "market": ["market.trend_notes", "market.role_families"],
    "opportunity": ["market.opportunity_snapshots"],
    "strategy": ["strategy.", "career."],
    "resume": ["resume.last_optimization_levels"],
    "coordinator": ["career.jd_override"],
}


@dataclass
class ProfilePatchError:
    code: str
    message: str


def _path_allowed(actor: str, path: str) -> bool:
    prefixes = PROFILE_PATCH_WHITELIST.get(actor, [])
    for prefix in prefixes:
        if prefix.endswith("[]"):
            base = prefix[:-2]
            if path == base or path.startswith(f"{base}[") or path.startswith(base):
                return True
        elif path == prefix.rstrip(".") or path.startswith(prefix):
            return True
    return False


def profile_patch(actor: str, args: dict[str, Any]) -> ProfilePatchError | dict[str, Any]:
    path = args.get("path", "")
    value = args.get("value")
    op = args.get("op", "set")
    if op != "set":
        return ProfilePatchError("profile_patch_rejected", f"Unsupported op {op}")
    if not _path_allowed(actor, path):
        return ProfilePatchError(
            "profile_patch_rejected",
            f"Actor {actor} cannot patch {path}",
        )
    store = ProfileStore()
    store.patch([{"path": path, "value": value, "op": "set"}])
    return {"ok": True, "path": path}


def apply_proposed_patches(
    actor: str, args: dict[str, Any]
) -> ProfilePatchError | dict[str, Any]:
    if actor != "coordinator":
        return ProfilePatchError(
            "profile_patch_rejected",
            "apply_proposed_patches is coordinator-only",
        )
    patches = args.get("patches", [])
    store = ProfileStore()
    valid: list[dict[str, Any]] = []
    for patch in patches:
        path = patch.get("path", "")
        if not _path_allowed("coordinator", path):
            worker = patch.get("source_worker")
            if worker and _path_allowed(worker, path):
                valid.append({"path": path, "value": patch.get("value"), "op": "set"})
            else:
                return ProfilePatchError(
                    "profile_patch_rejected",
                    f"Rejected proposed patch for {path}",
                )
        else:
            valid.append({"path": path, "value": patch.get("value"), "op": "set"})
    if valid:
        store.patch(valid)
    return {"ok": True, "applied": len(valid)}


def profile_get(actor: str, args: dict[str, Any]) -> dict[str, Any]:
    paths = args.get("paths") or ["basic", "intent", "exploration", "career", "strategy"]
    store = ProfileStore()
    return store.get(paths)
