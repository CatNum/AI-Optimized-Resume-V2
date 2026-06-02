from typing import Any

from career_os.harness.errors import HarnessError
from career_os.harness.jd_prerequisites import jd_delegate_block_error
from career_os.harness.explore_intake import worker_context_from_intake
from career_os.platform.trace.writer import TraceWriter


def check_delegate_rules(
    worker_id: str, session_state: dict[str, Any]
) -> HarnessError | None:
    list_type = session_state.get("list_type")
    prior_results = session_state.get("prior_results") or {}
    gates = session_state.get("gates") or {}
    flags = gates.get("flags") or {}

    b1 = jd_delegate_block_error(worker_id, session_state)
    if b1:
        return b1

    if worker_id == "opportunity":
        from career_os.harness.pipeline_routing import is_pipeline_session

        on_jd_chain = list_type == "jd" or is_pipeline_session(session_state)
        if on_jd_chain and "market" not in prior_results:
            return HarnessError(
                "delegate_blocked",
                "JD-R1: opportunity requires prior_results.market",
            )

    if worker_id == "resume":
        if not flags.get("optimize_confirmed"):
            return HarnessError(
                "gate_blocked",
                "resume delegation requires optimize_confirmed",
            )
        list_id = session_state.get("list_id")
        if list_id:
            from career_os.platform.store.task import TaskStore

            meta = TaskStore().get_list_meta(list_id)
            if meta and meta.get("list_type") == "pipeline":
                if meta.get("current_phase") != "resume_optimize":
                    return HarnessError(
                        "gate_blocked",
                        "resume delegation requires current_phase=resume_optimize",
                    )

    return None


def _build_capability_bundle(worker_id: str) -> dict[str, Any]:
    from career_os.platform.skill.registry import SkillRegistry
    from career_os.platform.worker.registry import WorkerRegistry

    worker = WorkerRegistry().get_worker(worker_id) or {}
    skill_registry = SkillRegistry()
    skill_index = []
    for name in worker.get("skills") or []:
        entry = next((e for e in skill_registry.list_skills() if e.name == name), None)
        if entry:
            skill_index.append(
                {
                    "name": entry.name,
                    "description": entry.description,
                    "when_to_use": entry.when_to_use,
                    "modes": entry.modes,
                }
            )
    tool_index = [{"name": t} for t in worker.get("tools") or []]
    return {"skill_index": skill_index, "tool_index": tool_index}


def delegate_worker(
    actor: str,
    worker_id: str,
    goal: str,
    session_state: dict[str, Any],
    *,
    context: dict[str, Any] | None = None,
    trace: TraceWriter | None = None,
    session_id: str | None = None,
) -> HarnessError | dict[str, Any]:
    if actor != "coordinator":
        return HarnessError(
            "tool_not_allowed",
            "delegate_worker is coordinator-only",
        )

    err = check_delegate_rules(worker_id, session_state)
    if err:
        if trace:
            trace.emit(
                "agent.run.end",
                session_id=session_id or session_state.get("session_id"),
                worker_id=worker_id,
                status="failed",
                detail={"code": err.code, "message": err.message},
            )
        return err

    if trace:
        trace.emit(
            "agent.run.start",
            session_id=session_id or session_state.get("session_id"),
            worker_id=worker_id,
            status="ok",
        )

    merged_context = dict(context or {})
    merged_context["capability_bundle"] = _build_capability_bundle(worker_id)
    merged_context.setdefault("constraints", {"no_fabrication": True})
    from career_os.harness.pipeline_routing import is_pipeline_explore_phase

    if worker_id in {"identity", "capability"} and is_pipeline_explore_phase(session_state):
        merged_context.update(worker_context_from_intake(session_state))

    return {
        "worker_id": worker_id,
        "goal": goal,
        "context": merged_context,
        "status": "delegated",
    }
