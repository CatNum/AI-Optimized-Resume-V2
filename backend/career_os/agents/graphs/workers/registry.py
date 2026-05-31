from typing import Any, Callable

from career_os.agents.graphs.workers import (
    asset,
    capability,
    identity,
    market,
    opportunity,
    resume,
    strategy,
)
from career_os.agents.graphs.workers.base import finalize_worker_result

WorkerFn = Callable[[Any, str, dict[str, Any], dict[str, Any]], dict[str, Any]]

WORKER_RUNNERS: dict[str, WorkerFn] = {
    "market": market.run,
    "opportunity": opportunity.run,
    "identity": identity.run,
    "capability": capability.run,
    "strategy": strategy.run,
    "resume": resume.run,
    "asset": asset.run,
}


def build_harness_worker_runner(harness: Any) -> Callable[[str, str, dict[str, Any], dict[str, Any]], dict[str, Any]]:
    def runner(
        worker_id: str,
        goal: str,
        session_state: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        fn = WORKER_RUNNERS.get(worker_id)
        if fn is None:
            return {"worker_id": worker_id, "status": "failed", "error": "unknown worker"}
        return fn(harness, goal, session_state, context)

    return runner
