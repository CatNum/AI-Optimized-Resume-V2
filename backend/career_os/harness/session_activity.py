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

    profile = ProfileStore().get(["exploration", "intent"])
    if not compute_needs_full_explore(profile, session_state):
        return False
    if not is_pipeline_explore_phase(session_state):
        return False
    if session_state.get("explore_intake_blocked"):
        return False
    if is_explore_gate_confirmed(session_state):
        return False
    flags = (session_state.get("gates") or {}).get("flags") or {}
    if flags.get("explore_repeat_declined"):
        return False
    closure = session_state.get("explore_closure") or {}
    if not closure:
        return False
    if closure.get("gate_pending"):
        return False
    return not is_closure_ready(closure)


def _explore_worker_status(
    worker_id: str,
    session_state: dict[str, Any],
) -> str:
    """_explore_worker_status（内部函数 explore worker status）的函数说明。

    worker_id（参数）、session_state（参数）用于向该函数传入运行所需的数据。

    该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
    closure = session_state.get("explore_closure") or {}
    worker_done = closure.get("worker_done") or {}
    if worker_done.get(worker_id):
        return "completed"

    prior = (session_state.get("prior_results") or {}).get(worker_id) or {}
    if prior.get("phase_status") == "in_progress":
        return "in_progress"

    required = closure.get("required_workers") or DEFAULT_REQUIRED_WORKERS
    incomplete = [wid for wid in required if not worker_done.get(wid, False)]
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
    if list_type == "pipeline" and list_id:
        from career_os.platform.store.task import TaskStore

        list_meta = TaskStore().get_list_meta(list_id)

    from career_os.harness.pipeline_routing import get_current_phase, is_pipeline_session
    profile = ProfileStore().get(["exploration", "intent"])
    needs_full_explore = compute_needs_full_explore(profile, session_state)

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
    """_activity_headline（内部函数 activity headline）的函数说明。

    session_state（参数）、items（参数）用于向该函数传入运行所需的数据。

    该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
    list_type = session_state.get("list_type")
    list_id = session_state.get("list_id")
    list_meta = None
    if list_type == "pipeline" and list_id:
        from career_os.platform.store.task import TaskStore

        list_meta = TaskStore().get_list_meta(list_id)
    profile = ProfileStore().get(["exploration", "intent"])
    needs_full_explore = compute_needs_full_explore(profile, session_state)
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
