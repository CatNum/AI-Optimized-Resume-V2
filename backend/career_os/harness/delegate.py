from typing import Any

from career_os.harness.errors import HarnessError
from career_os.platform.trace.writer import TraceWriter


def check_delegate_rules(
    worker_id: str, session_state: dict[str, Any]
) -> HarnessError | None:
    list_type = session_state.get("list_type")
    prior_results = session_state.get("prior_results") or {}
    gates = session_state.get("gates") or {}
    flags = gates.get("flags") or {}

    if worker_id == "opportunity" and list_type == "jd":
        if "market" not in prior_results:
            return HarnessError(
                "delegate_blocked",
                "JD-R1: opportunity requires prior_results.market",
            )

    if worker_id == "resume" and not flags.get("optimize_confirmed"):
        return HarnessError(
            "gate_blocked",
            "resume delegation requires optimize_confirmed",
        )

    return None


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

    return {
        "worker_id": worker_id,
        "goal": goal,
        "context": context or {},
        "status": "delegated",
    }
