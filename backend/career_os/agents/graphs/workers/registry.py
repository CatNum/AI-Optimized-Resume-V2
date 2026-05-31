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
from career_os.agents.graphs.workers.react_runner import run_worker_react
from career_os.agents.lc.client import llm_enabled
from career_os.agents.lc.worker_llm import enhance_worker_summary_with_llm

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


def build_harness_worker_runner(
    harness: Any,
    *,
    use_react: bool = True,
) -> Callable[[str, str, dict[str, Any], dict[str, Any]], dict[str, Any]]:
    def runner(
        worker_id: str,
        goal: str,
        session_state: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        if use_react and llm_enabled():
            return run_worker_react(
                harness,
                worker_id=worker_id,
                goal=goal,
                session_state=session_state,
                context=context,
            )
        fn = WORKER_RUNNERS.get(worker_id)
        if fn is None:
            return {"worker_id": worker_id, "status": "failed", "error": "unknown worker"}
        result = fn(harness, goal, session_state, context)
        structured = result.get("structured_output")
        if result.get("status") == "completed" and isinstance(structured, dict):
            enhanced = enhance_worker_summary_with_llm(worker_id, goal, structured)
            if enhanced:
                result = {**result, "structured_output": enhanced}
        return result

    return runner
