from typing import Any, Callable

from langgraph.graph import END, StateGraph

from career_os.agents.lc.worker_llm import synthesize_with_llm
from career_os.agents.state.coordinator import CoordinatorState
from career_os.harness.explore_closure import (
    can_set_explore_gate_pending,
    mark_worker_done,
)
from career_os.harness.errors import HarnessError
from career_os.platform.worker.registry import WorkerRegistry

WorkerRunner = Callable[[str, str, dict[str, Any], dict[str, Any]], dict[str, Any]]


def _default_worker_runner(
    worker_id: str,
    goal: str,
    session_state: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    return {
        "worker_id": worker_id,
        "status": "completed",
        "structured_output": {"user_visible_summary": goal},
    }


def build_coordinator_graph(
    harness: Any,
    *,
    worker_runner: WorkerRunner | None = None,
) -> Any:
    runner = worker_runner or _default_worker_runner

    def analyze(state: CoordinatorState) -> CoordinatorState:
        if state.get("stop_delegate"):
            return state
        pending = list(state.get("pending_workers") or [])
        if not pending:
            return {**state, "current_worker_id": None}
        return {**state, "current_worker_id": pending[0]}

    def delegate(state: CoordinatorState) -> CoordinatorState:
        worker_id = state.get("current_worker_id")
        if not worker_id or state.get("stop_delegate"):
            return state

        session_state = dict(state.get("session_state") or {})
        result = harness.delegate_worker(
            "coordinator",
            worker_id,
            state.get("user_message", ""),
            session_state,
            session_id=state.get("session_id"),
        )
        if isinstance(result, HarnessError):
            return {
                **state,
                "stop_delegate": True,
                "last_worker_result": {"status": "failed", "error": result.message},
            }

        worker_result = runner(
            worker_id,
            state.get("user_message", ""),
            session_state,
            result.get("context") or {},
        )
        prior_results = dict(session_state.get("prior_results") or {})
        if worker_result.get("status") == "completed":
            prior_results[worker_id] = worker_result.get("structured_output") or {}
        session_state["prior_results"] = prior_results

        explore_closure = mark_worker_done(
            session_state.get("explore_closure"), worker_id
        )
        session_state["explore_closure"] = explore_closure

        structured = worker_result.get("structured_output") or {}
        gate_prompt = structured.get("gate_prompt")
        stop_delegate = bool(gate_prompt)
        if can_set_explore_gate_pending(explore_closure):
            stop_delegate = True

        pending = list(state.get("pending_workers") or [])
        if worker_id in pending:
            pending.remove(worker_id)

        return {
            **state,
            "session_state": session_state,
            "last_worker_result": worker_result,
            "stop_delegate": stop_delegate,
            "pending_workers": pending,
            "delegate_count": state.get("delegate_count", 0) + 1,
            "current_worker_id": None,
        }

    def synthesize(state: CoordinatorState) -> CoordinatorState:
        session_state = dict(state.get("session_state") or {})
        last = state.get("last_worker_result") or {}
        structured = last.get("structured_output") or {}

        if can_set_explore_gate_pending(session_state.get("explore_closure")):
            text = "初探两线已完成，请确认是否完成初探？"
            gates = dict(session_state.get("gates") or {})
            gates["pending"] = {
                "name": "explore_complete",
                "prompt": text,
            }
            session_state["gates"] = gates
            explore = dict(session_state.get("explore_closure") or {})
            explore["gate_pending"] = True
            session_state["explore_closure"] = explore
        elif structured.get("gate_prompt"):
            gate = structured["gate_prompt"]
            text = gate.get("prompt") or structured.get("user_visible_summary", "")
            gates = dict(session_state.get("gates") or {})
            gates["pending"] = {
                "name": gate.get("name") or gate.get("gate_name"),
                "prompt": text,
            }
            session_state["gates"] = gates
        else:
            text = structured.get("user_visible_summary") or "已完成本轮处理。"

        polished = synthesize_with_llm(
            state.get("user_message", ""),
            text,
            session_state,
            last or None,
        )
        if polished:
            text = polished

        return {
            **state,
            "session_state": session_state,
            "synthesis_text": text,
        }

    def route_after_analyze(state: CoordinatorState) -> str:
        if state.get("stop_delegate") or not state.get("current_worker_id"):
            return "synthesize"
        return "delegate"

    def route_after_delegate(state: CoordinatorState) -> str:
        if state.get("stop_delegate") or not state.get("pending_workers"):
            return "synthesize"
        return "analyze"

    graph = StateGraph(CoordinatorState)
    graph.add_node("analyze", analyze)
    graph.add_node("delegate", delegate)
    graph.add_node("synthesize", synthesize)
    graph.set_entry_point("analyze")
    graph.add_conditional_edges("analyze", route_after_analyze)
    graph.add_conditional_edges("delegate", route_after_delegate)
    graph.add_edge("synthesize", END)
    return graph.compile()


def run_coordinator_turn(
    harness: Any,
    *,
    session_id: str,
    session_state: dict[str, Any],
    user_message: str,
    pending_workers: list[str] | None = None,
    worker_runner: WorkerRunner | None = None,
) -> CoordinatorState:
    worker_registry = WorkerRegistry()
    initial: CoordinatorState = {
        "messages": [],
        "session_id": session_id,
        "session_state": session_state,
        "worker_index": worker_registry.get_worker_index(),
        "pending_workers": pending_workers or [],
        "user_message": user_message,
        "stop_delegate": False,
        "delegate_count": 0,
    }
    graph = build_coordinator_graph(harness, worker_runner=worker_runner)
    return graph.invoke(initial)
