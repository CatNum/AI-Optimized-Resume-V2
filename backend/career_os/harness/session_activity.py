from __future__ import annotations

from typing import Any

from career_os.harness.explore_closure import (
    DEFAULT_REQUIRED_WORKERS,
    is_closure_ready,
)
from career_os.harness.explore_intake import explore_intake_submitted
from career_os.harness.pipeline_gates import compute_needs_full_explore
from career_os.platform.store.profile import ProfileStore

EXPLORE_WORKER_TITLES = {
    "identity": "内心探索",
    "capability": "能力素材补充",
}

LIST_TYPE_LABELS = {
    "explore": "职业初探",
    "jd": "JD 评估",
    "plan": "职业规划",
    "pipeline": "职业路径",
}


def explore_flow_active(session_state: dict[str, Any]) -> bool:
    """判断当前是否仍处于活跃的职业初探流程。

    session_state（会话状态）提供 pipeline 阶段、intake 阻断、门禁和 explore_closure。
    返回值为 True 表示 Coordinator 应继续初探，而不是切到其他流程。
    """
    from career_os.harness.pipeline_gates import is_explore_gate_confirmed
    from career_os.harness.pipeline_routing import is_pipeline_explore_phase

    # 先用 profile + session_state 判断是否必须继续完整初探。
    profile = ProfileStore().get(["exploration", "intent"])
    if not compute_needs_full_explore(profile, session_state):
        return False
    # 只有 pipeline/explore 阶段才认为初探流程活跃。
    if not is_pipeline_explore_phase(session_state):
        return False
    # intake 阻断、完成 gate 已确认、用户拒绝重复初探，都表示不应继续自动推进探索 Worker。
    if session_state.get("explore_intake_blocked"):
        return False
    if is_explore_gate_confirmed(session_state):
        return False
    flags = (session_state.get("gates") or {}).get("flags") or {}
    if flags.get("explore_repeat_declined"):
        return False
    closure = session_state.get("explore_closure") or {}
    # 没有闭环状态或已经挂起完成 gate 时，synthesize 不再输出“继续探索”的草稿。
    if not closure:
        return False
    if closure.get("gate_pending"):
        return False
    return not is_closure_ready(closure)


def _explore_worker_status(
    worker_id: str,
    session_state: dict[str, Any],
) -> str:
    """计算探索 Worker 在会话活动摘要中的展示状态。

    worker_id（工作者标识）用于定位 identity/capability；
    session_state（会话状态）提供 explore_closure 和 prior_results。
    返回值是 completed、in_progress 或 pending。
    """
    closure = session_state.get("explore_closure") or {}
    worker_done = closure.get("worker_done") or {}
    # 已被闭环标记完成时，展示 completed。
    if worker_done.get(worker_id):
        return "completed"

    prior = (session_state.get("prior_results") or {}).get(worker_id) or {}
    # Worker 最近一次结果仍是 in_progress 时，展示进行中。
    if prior.get("phase_status") == "in_progress":
        return "in_progress"

    required = closure.get("required_workers") or DEFAULT_REQUIRED_WORKERS
    incomplete = [wid for wid in required if not worker_done.get(wid, False)]
    # 第一个未完成 Worker 是当前应答对象，展示 in_progress；其余未完成项保持 pending。
    if incomplete and incomplete[0] == worker_id:
        return "in_progress"
    return "pending"


def build_session_activity(session_state: dict[str, Any]) -> dict[str, Any]:
    """构建当前会话活动摘要。

    session_state（会话状态）提供 list_type、list_id、当前阶段和探索闭环。
    返回值包含 list_type（列表类型）、headline（当前阶段标题）和 items（阶段任务项），
    用于 Coordinator 合成“当前在什么阶段”的回复。
    """
    list_type = session_state.get("list_type")
    items: list[dict[str, str]] = []
    list_id = session_state.get("list_id")
    list_meta = None
    # pipeline 会话如果有 list_id，就读取任务列表元信息辅助判断 ready/阶段状态。
    if list_type == "pipeline" and list_id:
        from career_os.platform.store.task import TaskStore

        list_meta = TaskStore().get_list_meta(list_id)

    from career_os.harness.pipeline_routing import get_current_phase, is_pipeline_session
    profile = ProfileStore().get(["exploration", "intent"])
    needs_full_explore = compute_needs_full_explore(profile, session_state)

    # 需要完整初探且 intake 未提交时，活动摘要只展示“填写初探信息表”。
    if needs_full_explore and (
        session_state.get("explore_intake_blocked") or (
        is_pipeline_session(session_state)
        and get_current_phase(session_state) == "explore"
        and not explore_intake_submitted(session_state)
        )
    ):
        items.append(
            {
                "id": "explore_intake",
                "title": "填写初探信息表",
                "status": "in_progress",
            }
        )
    elif (
        is_pipeline_session(session_state)
        and get_current_phase(session_state) == "explore"
        and (list_meta or {}).get("status") != "ready"
    ):
        # explore 阶段展示 identity/capability 两个探索 Worker 的完成情况。
        closure = session_state.get("explore_closure") or {}
        required = closure.get("required_workers") or DEFAULT_REQUIRED_WORKERS
        for worker_id in required:
            items.append(
                {
                    "id": worker_id,
                    "title": EXPLORE_WORKER_TITLES.get(worker_id, worker_id),
                    "status": _explore_worker_status(worker_id, session_state),
                }
            )
    elif (
        is_pipeline_session(session_state)
        and (list_meta or {}).get("status") != "ready"
        and get_current_phase(session_state) in {
            "market",
            "jd_analysis",
            "resume_strategy",
            "resume_optimize",
        }
    ):
        # 非 explore 的 pipeline 阶段只展示一个当前阶段进行中条目。
        phase = get_current_phase(session_state) or ""
        items.append(
            {
                "id": f"phase_{phase}",
                "title": LIST_TYPE_LABELS.get("pipeline", "职业路径"),
                "status": "in_progress",
            }
        )

    headline = _activity_headline(session_state, items)
    return {
        "list_type": list_type,
        "headline": headline,
        "items": items,
    }


def _activity_headline(
    session_state: dict[str, Any],
    items: list[dict[str, str]],
) -> str | None:
    """生成会话活动摘要标题。

    session_state（会话状态）提供 list_type、list_id 和当前阶段；
    items（阶段任务项）提供进行中/已完成状态。返回值是“当前：...”标题。
    """
    list_type = session_state.get("list_type")
    list_id = session_state.get("list_id")
    list_meta = None
    # pipeline 且有 list_id 时读取列表状态，区分待开始和进行中。
    if list_type == "pipeline" and list_id:
        from career_os.platform.store.task import TaskStore

        list_meta = TaskStore().get_list_meta(list_id)
    profile = ProfileStore().get(["exploration", "intent"])
    needs_full_explore = compute_needs_full_explore(profile, session_state)
    # intake 阻断优先展示，因为此时用户下一步动作最明确。
    if session_state.get("explore_intake_blocked") and needs_full_explore:
        return "当前：请先填写初探信息表"
    from career_os.harness.pipeline_routing import get_current_phase, is_pipeline_session

    if is_pipeline_session(session_state):
        phase = get_current_phase(session_state) or "explore"
        label = LIST_TYPE_LABELS.get("pipeline", "职业路径")
        status = (list_meta or {}).get("status")
        if status == "ready":
            return f"当前：{label} · 待开始"
        phase_labels = {
            "explore": "职业初探",
            "market": "市场分析",
            "jd_analysis": "JD 分析",
            "resume_strategy": "简历优化策略",
            "resume_optimize": "简历优化",
        }
        step = phase_labels.get(phase, phase)
        # explore 阶段有具体 Worker 进行中时，把 Worker 标题带进 headline。
        active = next((item for item in items if item["status"] == "in_progress"), None)
        if active and phase == "explore":
            return f"当前：{step} · {active['title']}进行中"
        if phase == "explore" and all(item["status"] == "completed" for item in items if items):
            return "当前：职业初探 · 待确认收束"
        return f"当前：{label} · {step}"
    return None


def explore_continue_synthesis_draft(session_state: dict[str, Any]) -> str:
    """生成继续职业初探的合成草稿。

    session_state（会话状态）提供 prior_results，尤其是 identity 的上一轮摘要。
    返回值用于提醒用户当前仍在初探流程中，并引导其继续回答。
    """
    prior = session_state.get("prior_results") or {}
    identity = prior.get("identity") or {}
    if identity.get("user_visible_summary"):
        return (
            "我们仍在进行职业初探，暂不切换其他流程。"
            "你刚才的问题可以直接回在这个话题里；若需要，我可以把问题拆成几个具体选项。"
        )
    return "我们正在进行职业初探，请继续分享你的想法或回答上面的问题。"
