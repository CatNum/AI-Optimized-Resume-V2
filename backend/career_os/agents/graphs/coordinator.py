from typing import Any, Callable

from langgraph.graph import END, StateGraph

from career_os.agents.lc.coordinator_llm import (
    analyze_workers,
    chat_only_synthesis_draft,
    fallback_analyze_workers,
    is_small_talk,
    jd_prerequisites_draft,
)
from career_os.agents.state.coordinator import CoordinatorState
from career_os.harness.explore_closure import (
    can_set_explore_gate_pending,
    mark_worker_done,
)
from career_os.harness.errors import HarnessError
from career_os.harness.jd_prerequisites import parse_jd_b1_block_reason
from career_os.platform.worker.registry import WorkerRegistry

WorkerRunner = Callable[[str, str, dict[str, Any], dict[str, Any]], dict[str, Any]]


def _emit_coordinator_analyze_trace(
    harness: Any,
    *,
    session_id: str | None,
    source: str,
    workers: list[str],
    list_type: str | None,
) -> None:
    trace = getattr(harness, "trace", None)
    if trace is None:
        return
    detail: dict[str, Any] = {"source": source, "workers": workers}
    if list_type:
        detail["list_type"] = list_type
    if workers:
        detail["next_worker"] = workers[0]
    trace.emit(
        "coordinator.analyze",
        session_id=session_id,
        actor="coordinator",
        worker_id=workers[0] if workers else None,
        status="ok",
        detail=detail,
    )


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
        session_state = dict(state.get("session_state") or {})
        session_state.pop("jd_prerequisite_blocked", None)
        session_state.pop("jd_block_reason", None)
        analysis: dict[str, Any] | None = None
        source: str | None = None

        def _apply_analysis(result: dict[str, Any] | None) -> list[str]:
            nonlocal session_state
            if not result:
                return []
            if result.get("jd_prerequisite_blocked"):
                session_state["jd_prerequisite_blocked"] = True
                session_state["jd_block_reason"] = result.get("jd_block_reason")
                return []
            workers = result.get("workers") or []
            if result.get("list_type"):
                session_state["list_type"] = result["list_type"]
            return workers

        if pending:
            source = "queue" if state.get("delegate_count", 0) > 0 else "preset"
        elif is_small_talk(state.get("user_message", "")):
            source = "fallback"
            pending = []
        else:
            analysis = analyze_workers(
                state.get("user_message", ""),
                session_state,
                state.get("worker_index") or [],
            )
            if analysis is not None:
                source = "llm"
                pending = _apply_analysis(analysis)
            else:
                analysis = fallback_analyze_workers(
                    state.get("user_message", ""),
                    session_state,
                )
                if analysis is not None:
                    source = "fallback"
                    pending = _apply_analysis(analysis)
                else:
                    source = "none"
                    pending = []

        state = {**state, "session_state": session_state}

        if source:
            _emit_coordinator_analyze_trace(
                harness,
                session_id=state.get("session_id"),
                source=source,
                workers=pending,
                list_type=session_state.get("list_type"),
            )

        if not pending:
            return {
                **state,
                "session_state": session_state,
                "current_worker_id": None,
                "pending_workers": [],
            }
        return {
            **state,
            "session_state": session_state,
            "pending_workers": pending,
            "current_worker_id": pending[0],
        }

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
            session_state = dict(state.get("session_state") or {})
            block_reason = parse_jd_b1_block_reason(result.message)
            if block_reason:
                session_state["jd_prerequisite_blocked"] = True
                session_state["jd_block_reason"] = block_reason
            return {
                **state,
                "session_state": session_state,
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
        elif session_state.get("jd_prerequisite_blocked"):
            text = jd_prerequisites_draft(session_state.get("jd_block_reason"))
        else:
            if state.get("delegate_count", 0) == 0 and not structured:
                text = chat_only_synthesis_draft()
            else:
                text = structured.get("user_visible_summary") or "已完成本轮处理。"

        return {
            **state,
            "session_state": session_state,
            "synthesis_text": text,
            "synthesis_draft": text,
            "last_worker_result": last or state.get("last_worker_result"),
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
