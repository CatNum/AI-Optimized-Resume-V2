from typing import Any

from career_os.harness.errors import HarnessError
from career_os.platform.skill.registry import SkillRegistry
from career_os.platform.trace.writer import TraceWriter
from career_os.platform.worker.registry import WorkerRegistry


def load_skill(actor: str, args: dict[str, Any]) -> dict[str, Any] | HarnessError:
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
