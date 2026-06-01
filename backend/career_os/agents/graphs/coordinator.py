from typing import Any, Callable

from langgraph.graph import END, StateGraph

from career_os.agents.lc.coordinator_llm import (
    analyze_workers,
    chat_only_synthesis_draft,
    explore_intake_draft,
    explore_repeat_draft,
    fallback_analyze_workers,
    is_small_talk,
    jd_prerequisites_draft,
)
from career_os.agents.state.coordinator import CoordinatorState
from career_os.harness.explore_closure import (
    EXPLORE_WORKERS,
    can_set_explore_gate_pending,
    explore_continuation_analyze,
    explore_phase_status,
    is_explore_segment_complete,
    mark_worker_done,
    plan_explore_worker_dispatch,
)
from career_os.harness.session_activity import (
    explore_continue_synthesis_draft,
    explore_flow_active,
)
from career_os.harness.explore_intake import enforce_explore_intake, needs_repeat_intake
from career_os.harness.explore_guidance import (
    build_explore_guidance_synthesis_draft,
    format_revealed_options,
    mark_explore_guidance_revealed,
    persist_worker_guidance,
    should_reveal_explore_guidance,
    supports_explore_guidance,
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
        from career_os.harness.pipeline_routing import maybe_apply_jd_fingerprint_from_message

        session_state = maybe_apply_jd_fingerprint_from_message(
            state.get("session_id"),
            session_state,
            state.get("user_message", ""),
        )
        session_state.pop("jd_prerequisite_blocked", None)
        session_state.pop("jd_block_reason", None)
        if not needs_repeat_intake(session_state):
            session_state.pop("explore_intake_blocked", None)
        session_state.pop("explore_guidance_reveal_pending", None)

        if should_reveal_explore_guidance(state.get("user_message", ""), session_state):
            mark_explore_guidance_revealed(session_state)
            return {
                **state,
                "session_state": session_state,
                "current_worker_id": None,
                "pending_workers": [],
                "stop_delegate": True,
            }

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
            if result.get("explore_intake_blocked"):
                session_state["explore_intake_blocked"] = True
                if result.get("list_type"):
                    session_state["list_type"] = result["list_type"]
                return []
            if result.get("explore_repeat_blocked"):
                session_state["explore_repeat_blocked"] = True
                if result.get("list_type"):
                    session_state["list_type"] = result["list_type"]
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

        if (
            not pending
            and not session_state.get("explore_intake_blocked")
            and not is_small_talk(state.get("user_message", ""))
        ):
            continued = explore_continuation_analyze(session_state)
            if continued and continued.get("workers"):
                pending = continued["workers"]
                if continued.get("list_type"):
                    session_state["list_type"] = continued["list_type"]
                source = "continuation" if source in (None, "llm", "none", "fallback") else source

        if pending and not session_state.get("explore_intake_blocked"):
            intake_payload: dict[str, Any] = {"workers": pending}
            if session_state.get("list_type"):
                intake_payload["list_type"] = session_state["list_type"]
            intake_check = enforce_explore_intake(intake_payload, session_state)
            if intake_check.get("explore_intake_blocked"):
                session_state["explore_intake_blocked"] = True
                if intake_check.get("list_type"):
                    session_state["list_type"] = intake_check["list_type"]
                pending = []
            elif intake_check.get("explore_repeat_blocked"):
                session_state["explore_repeat_blocked"] = True
                if intake_check.get("list_type"):
                    session_state["list_type"] = intake_check["list_type"]
                pending = []
            elif not intake_check.get("workers"):
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

        planned = plan_explore_worker_dispatch(pending, session_state)

        if not pending:
            return {
                **state,
                "session_state": session_state,
                "current_worker_id": None,
                "pending_workers": [],
            }
        if not planned:
            return {
                **state,
                "session_state": session_state,
                "current_worker_id": None,
                "pending_workers": pending,
            }
        return {
            **state,
            "session_state": session_state,
            "pending_workers": pending,
            "current_worker_id": planned[0],
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

        structured = worker_result.get("structured_output") or {}
        if worker_result.get("status") == "completed" and supports_explore_guidance(worker_id):
            persist_worker_guidance(session_state, worker_id, structured)
        gate_prompt = structured.get("gate_prompt")
        explore_closure = mark_worker_done(
            session_state.get("explore_closure"),
            worker_id,
            structured_output=structured,
        )
        session_state["explore_closure"] = explore_closure

        stop_delegate = bool(gate_prompt)
        if (
            worker_id in EXPLORE_WORKERS
            and explore_phase_status(structured) != "segment_complete"
        ):
            stop_delegate = True
        elif can_set_explore_gate_pending(explore_closure):
            stop_delegate = True

        pending = list(state.get("pending_workers") or [])
        if worker_id in pending and (
            worker_id not in EXPLORE_WORKERS
            or is_explore_segment_complete(worker_id, structured)
        ):
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

        from career_os.harness.explore_depth import can_offer_explore_complete
        from career_os.platform.store.profile import ProfileStore

        profile = ProfileStore().get(
            ["basic", "intent", "exploration", "resume", "capability"]
        )
        list_type = session_state.get("list_type")
        offer_explore, _diag = can_offer_explore_complete(profile, session_state)
        text: str | None = None
        if (
            list_type == "pipeline"
            and offer_explore
            and can_set_explore_gate_pending(session_state.get("explore_closure"))
        ):
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
        elif can_set_explore_gate_pending(session_state.get("explore_closure")):
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
        elif session_state.get("explore_repeat_blocked"):
            text = explore_repeat_draft()
            gates = dict(session_state.get("gates") or {})
            gates["pending"] = {
                "name": "explore_repeat",
                "prompt": text,
            }
            session_state["gates"] = gates
            session_state.pop("explore_repeat_blocked", None)
        elif session_state.get("explore_intake_blocked"):
            text = explore_intake_draft()
        elif session_state.pop("explore_guidance_reveal_pending", False):
            text = format_revealed_options(session_state.get("explore_guidance") or {})
        else:
            if state.get("delegate_count", 0) == 0 and not structured:
                if explore_flow_active(session_state):
                    text = explore_continue_synthesis_draft(session_state)
                else:
                    text = chat_only_synthesis_draft()
            elif worker_id := (last.get("worker_id") or state.get("current_worker_id")):
                if supports_explore_guidance(worker_id) and structured:
                    text = build_explore_guidance_synthesis_draft(structured, session_state)
                else:
                    text = structured.get("user_visible_summary") or "已完成本轮处理。"
            else:
                text = structured.get("user_visible_summary") or "已完成本轮处理。"

        if text is None:
            text = chat_only_synthesis_draft()

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
