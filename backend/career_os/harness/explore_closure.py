from typing import Any

EXPLORE_GATE_NAMES = {"explore_complete", "explore_review_complete"}
DEFAULT_REQUIRED_WORKERS = ["identity", "capability"]
EXPLORE_WORKERS = frozenset(DEFAULT_REQUIRED_WORKERS)
PHASE_IN_PROGRESS = "in_progress"
PHASE_SEGMENT_COMPLETE = "segment_complete"
EXPLORE_DISPATCH_ORDER = ["identity", "capability"]


def init_explore_closure(
    *,
    gate_name: str = "explore_complete",
    required_workers: list[str] | None = None,
) -> dict[str, Any]:
    """初始化探索闭环状态。

    gate_name（门禁名称）表示闭环完成后要触发的确认 gate；
    required_workers（必需工作者）指定本轮探索必须完成哪些 Worker。
    返回值包含 worker_done（工作者完成表）和 gate_pending（门禁待确认状态）。
    """
    required = required_workers or DEFAULT_REQUIRED_WORKERS
    # 默认探索 Worker 中，不在 required_workers 的 Worker 视为已完成，避免阻塞闭环。
    worker_done = {
        worker_id: worker_id not in required for worker_id in DEFAULT_REQUIRED_WORKERS
    }
    for worker_id in required:
        worker_done[worker_id] = False
    return {
        "gate_name": gate_name,
        "required_workers": required,
        "worker_done": worker_done,
        "gate_pending": False,
    }


def explore_phase_status(structured_output: dict[str, Any] | None) -> str:
    """读取探索 Worker 的阶段状态。

    structured_output（结构化输出）是 identity/capability Worker 返回的结果。
    返回值是 PHASE_IN_PROGRESS（进行中）或 PHASE_SEGMENT_COMPLETE（阶段完成），
    用于 Coordinator 判断是否继续分发探索 Worker。
    """
    if not structured_output:
        return PHASE_IN_PROGRESS
    status = structured_output.get("phase_status")
    if status == PHASE_SEGMENT_COMPLETE:
        return PHASE_SEGMENT_COMPLETE
    return PHASE_IN_PROGRESS


def is_explore_segment_complete(
    worker_id: str, structured_output: dict[str, Any] | None
) -> bool:
    """判断某个探索 Worker 的当前片段是否完成。

    worker_id（工作者标识）用于区分 identity、capability 等 Worker；
    structured_output（结构化输出）提供 phase_status（阶段状态）。
    返回值为 True 表示该 Worker 可以从待执行队列移除。
    """
    if worker_id not in EXPLORE_WORKERS:
        return True
    return explore_phase_status(structured_output) == PHASE_SEGMENT_COMPLETE


def incomplete_explore_workers(session_state: dict[str, Any]) -> list[str]:
    """返回当前探索闭环中尚未完成的 Worker。

    session_state（会话状态）提供 explore_closure。返回值按 required_workers 的顺序排列，
    供 Coordinator 决定下一次派发哪个探索 Worker。
    """
    closure = session_state.get("explore_closure")
    # 没有闭环状态时，默认从完整探索顺序 identity -> capability 开始。
    if not closure:
        return list(EXPLORE_DISPATCH_ORDER)
    required = closure.get("required_workers") or DEFAULT_REQUIRED_WORKERS
    worker_done = closure.get("worker_done") or {}
    return [worker_id for worker_id in required if not worker_done.get(worker_id, False)]


def plan_explore_worker_dispatch(
    workers: list[str],
    session_state: dict[str, Any],
) -> list[str]:
    """规划探索 Worker 的分发顺序。

    workers（工作者列表）是当前候选 Worker；session_state（会话状态）保存
    explore_closure（探索闭环）进度。返回值通常只包含下一个应执行的探索 Worker，
    保证 identity 和 capability 按闭环顺序逐段推进。
    """
    # 候选队列不包含探索 Worker 时，不改变原始调度顺序。
    if not any(worker_id in EXPLORE_WORKERS for worker_id in workers):
        return workers
    incomplete = incomplete_explore_workers(session_state)
    # 探索流程一次只派发第一个未完成 Worker，等待它返回 segment_complete 后再继续。
    if incomplete:
        return [incomplete[0]]
    # 所有必需 Worker 已完成时，只保留候选探索 Worker 中排在最前的一个作为兜底。
    ordered = [worker_id for worker_id in EXPLORE_DISPATCH_ORDER if worker_id in workers]
    return ordered[:1] if ordered else workers


def explore_continuation_analyze(session_state: dict[str, Any]) -> dict[str, Any] | None:
    """分析是否需要继续未完成的探索流程。

    session_state（会话状态）提供 pipeline 阶段、门禁 flags 和 explore_closure。
    返回值是继续调度 identity/capability 的分析结果；如果不需要继续则返回 None。
    """
    from career_os.harness.pipeline_gates import is_explore_gate_confirmed
    from career_os.harness.pipeline_routing import get_current_phase, is_pipeline_explore_phase

    # 只有 pipeline 的 explore 阶段才需要自动续跑探索 Worker。
    if not is_pipeline_explore_phase(session_state):
        return None
    # 探索完成 gate 已确认后，不再自动派发探索 Worker。
    if is_explore_gate_confirmed(session_state):
        return None
    flags = (session_state.get("gates") or {}).get("flags") or {}
    # 用户拒绝重复初探时，也不能继续自动续跑。
    if flags.get("explore_repeat_declined"):
        return None
    closure = session_state.get("explore_closure") or {}
    # 闭环已完成或没有未完成 Worker 时，不需要续跑。
    if closure.get("completed"):
        return None
    incomplete = incomplete_explore_workers(session_state)
    if not incomplete:
        return None
    # 返回形态对齐 analyze_workers 的结果，Coordinator 可直接当作路由分析结果处理。
    return {
        "workers": [incomplete[0]],
        "list_type": "pipeline",
        "pipeline_phase": get_current_phase(session_state) or "explore",
    }


def mark_worker_done(
    explore_closure: dict[str, Any] | None,
    worker_id: str,
    *,
    structured_output: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """标记探索 Worker 完成状态。

    explore_closure（探索闭环状态）记录 required_workers 和 worker_done；
    worker_id（工作者标识）是刚执行完的 Worker；structured_output（结构化输出）
    提供 phase_status。返回值是更新后的 explore_closure。
    """
    # 没有现成闭环状态时先初始化，保证 worker_done 结构完整。
    state = dict(explore_closure or init_explore_closure())
    required = state.get("required_workers") or DEFAULT_REQUIRED_WORKERS
    worker_done = dict(state.get("worker_done") or {})
    if worker_id in required:
        # 探索 Worker 只有返回 segment_complete 才能标记完成；in_progress 会继续保留在队列。
        if not is_explore_segment_complete(worker_id, structured_output):
            state["worker_done"] = worker_done
            return state
        worker_done[worker_id] = True
    state["worker_done"] = worker_done
    return state


def is_closure_ready(explore_closure: dict[str, Any] | None) -> bool:
    """判断探索闭环必需 Worker 是否全部完成。

    explore_closure（探索闭环状态）提供 required_workers 和 worker_done。
    返回值为 True 表示可以准备发出完成确认 gate。
    """
    if not explore_closure:
        return False
    required = explore_closure.get("required_workers") or DEFAULT_REQUIRED_WORKERS
    worker_done = explore_closure.get("worker_done") or {}
    return all(worker_done.get(worker_id, False) for worker_id in required)


def can_set_explore_gate_pending(explore_closure: dict[str, Any] | None) -> bool:
    """判断是否可以设置探索完成门禁。

    explore_closure（探索闭环状态）记录 Worker 是否完成、门禁是否已 pending。
    返回值为 True 表示 identity/capability 都已完成，且可以向用户发出完成确认门禁。
    """
    if not explore_closure:
        return False
    if explore_closure.get("completed"):
        return False
    if explore_closure.get("gate_pending"):
        return False
    return is_closure_ready(explore_closure)


def validate_worker_structured_output(
    worker_id: str, structured_output: dict[str, Any]
) -> str | None:
    """校验 Worker 结构化输出是否违反探索门禁规则。

    worker_id（工作者标识）用于判断是否是探索 Worker；
    structured_output（结构化输出）可能包含 gate_prompt（门禁提示）。
    返回值为错误文案或 None；探索 Worker 不允许自己直接发出探索完成门禁。
    """
    gate_prompt = structured_output.get("gate_prompt")
    if not gate_prompt:
        return None
    gate_name = gate_prompt.get("name") or gate_prompt.get("gate_name")
    if worker_id in EXPLORE_WORKERS and gate_name in EXPLORE_GATE_NAMES:
        return f"{worker_id} must not emit explore gate_prompt (E2)"
    return None
