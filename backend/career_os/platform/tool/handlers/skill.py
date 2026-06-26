from typing import Any

from career_os.harness.errors import HarnessError
from career_os.platform.skill.registry import SkillRegistry
from career_os.platform.trace.writer import TraceWriter
from career_os.platform.worker.registry import WorkerRegistry


def load_skill(actor: str, args: dict[str, Any]) -> dict[str, Any] | HarnessError:
    """load_skill（load skill）的函数说明。

    actor（参数）、args（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    registry = SkillRegistry()
    bundle = registry.load_skill(
        args["name"],
        mode=args.get("mode"),
        worker_id=actor,
    )
    if hasattr(bundle, "code"):
        return HarnessError("skill_not_allowed", bundle.message)
    TraceWriter().emit(
        "skill.load",
        actor=actor,
        tool_name=bundle.name,
        status="ok",
        detail={"mode": bundle.mode, "hash": bundle.hash},
    )
    return {
        "name": bundle.name,
        "mode": bundle.mode,
        "body": bundle.body,
        "hash": bundle.hash,
    }


def list_skills(actor: str, args: dict[str, Any]) -> dict[str, Any]:
    """list_skills（list skills）的函数说明。

    actor（参数）、args（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    registry = SkillRegistry()
    worker = WorkerRegistry().get_worker(actor) or {}
    allowed = set(worker.get("skills") or [])
    skills = []
    for entry in registry.list_skills():
        if allowed and entry.name not in allowed:
            continue
        skills.append(
            {
                "name": entry.name,
                "description": entry.description,
                "modes": entry.modes,
            }
        )
    return {"skills": skills}
