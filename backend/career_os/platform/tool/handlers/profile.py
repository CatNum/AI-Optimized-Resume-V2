from dataclasses import dataclass
from typing import Any

from career_os.platform.store.profile import ProfileStore
from career_os.platform.store.session import SessionStore

PROFILE_PATCH_WHITELIST: dict[str, list[str]] = {
    "identity": ["exploration."],
    "capability": ["exploration.", "resume.experience_bank.", "capability."],
    "market": ["market.trend_notes", "market.role_families"],
    "opportunity": ["market.opportunity_snapshots"],
    "strategy": ["strategy.", "career."],
    "resume": ["resume.last_optimization_levels"],
    "coordinator": ["career.jd_override"],
}
SESSION_ARTIFACT_PREFIXES = ("exploration.", "market.", "strategy.")
SESSION_STATE_PREFIXES = ("career.jd_override",)


@dataclass
class ProfilePatchError:
    """ProfilePatchError（ProfilePatchError）的项目代码结构说明。

    该类封装当前模块中的一组相关状态或行为，供业务代码、测试代码或运行时流程复用。"""
    code: str
    message: str


def _path_allowed(actor: str, path: str) -> bool:
    """_path_allowed（内部函数 path allowed）的函数说明。

    actor（参数）、path（参数）用于向该函数传入运行所需的数据。

    该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
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
    """profile_patch（profile patch）的函数说明。

    actor（参数）、args（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    path = args.get("path", "")
    value = args.get("value")
    op = args.get("op", "set")
    session_id = args.get("session_id")
    if op != "set":
        return ProfilePatchError("profile_patch_rejected", f"Unsupported op {op}")
    if not _path_allowed(actor, path):
        return ProfilePatchError(
            "profile_patch_rejected",
            f"Actor {actor} cannot patch {path}",
        )
    if path.startswith(SESSION_ARTIFACT_PREFIXES):
        if not session_id:
            return ProfilePatchError(
                "profile_patch_rejected",
                f"Session scoped patch requires session_id: {path}",
            )
        SessionStore().patch_artifacts(
            session_id, [{"path": path, "value": value, "op": "set"}]
        )
        return {"ok": True, "path": path, "scope": "session_artifacts"}
    if path in SESSION_STATE_PREFIXES:
        if not session_id:
            return ProfilePatchError(
                "profile_patch_rejected",
                f"Session scoped patch requires session_id: {path}",
            )
        state = SessionStore().get_state(session_id)
        if path == "career.jd_override":
            state["jd_override"] = value
        SessionStore().update_state(session_id, state)
        return {"ok": True, "path": path, "scope": "session_state"}
    try:
        ProfileStore().patch([{"path": path, "value": value, "op": "set"}])
    except ValueError as exc:
        return ProfilePatchError("profile_path_forbidden", str(exc))
    return {"ok": True, "path": path, "scope": "profile"}


def apply_proposed_patches(
    actor: str, args: dict[str, Any]
) -> ProfilePatchError | dict[str, Any]:
    """apply_proposed_patches（apply proposed patches）的函数说明。

    actor（参数）、args（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
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
        try:
            store.patch(valid)
        except ValueError as exc:
            return ProfilePatchError("profile_path_forbidden", str(exc))
    return {"ok": True, "applied": len(valid)}


def profile_get(actor: str, args: dict[str, Any]) -> dict[str, Any]:
    """profile_get（profile get）的函数说明。

    actor（参数）、args（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    paths = args.get("paths") or ["basic", "intent", "exploration", "career", "strategy"]
    store = ProfileStore()
    return store.get(paths)
