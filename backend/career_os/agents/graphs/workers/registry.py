from typing import Any, Callable

from career_os.agents.graphs.workers.react_mocks import mock_run_worker_react
from career_os.agents.graphs.workers.react_runner import run_worker_react
from career_os.agents.lc.client import llm_enabled

WorkerFn = Callable[[Any, str, dict[str, Any], dict[str, Any]], dict[str, Any]]

REACT_REQUIRED_WORKERS = frozenset(
    {"market", "opportunity", "strategy", "resume", "identity", "capability", "asset"}
)


def build_harness_worker_runner(
    harness: Any,
    *,
    use_react: bool = True,
    use_react_mocks: bool | None = None,
) -> Callable[[str, str, dict[str, Any], dict[str, Any]], dict[str, Any]]:
    react_mocks = use_react_mocks if use_react_mocks is not None else not llm_enabled()

    def runner(
        worker_id: str,
        goal: str,
        session_state: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        if not use_react or worker_id not in REACT_REQUIRED_WORKERS:
            return {"worker_id": worker_id, "status": "failed", "error": "unknown worker"}

        if react_mocks:
            return mock_run_worker_react(
                harness,
                worker_id=worker_id,
                goal=goal,
                session_state=session_state,
                context=context,
            )

        if not llm_enabled():
            return {
                "worker_id": worker_id,
                "status": "failed",
                "error": f"LLM_API_KEY is required for {worker_id} ReAct worker",
            }

        return run_worker_react(
            harness,
            worker_id=worker_id,
            goal=goal,
            session_state=session_state,
            context=context,
        )

    return runner
