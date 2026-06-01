from __future__ import annotations

from typing import Any

from career_os.harness.explore_closure import (
    DEFAULT_REQUIRED_WORKERS,
    is_closure_ready,
)
from career_os.harness.explore_intake import explore_intake_submitted

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
    list_type = session_state.get("list_type")
    if list_type == "pipeline":
        from career_os.harness.pipeline_routing import get_current_phase

        if get_current_phase(session_state) != "explore":
            return False
    elif list_type != "explore":
        return False
    if session_state.get("explore_intake_blocked"):
        return False
    closure = session_state.get("explore_closure") or {}
    if closure.get("gate_pending"):
        return False
    return not is_closure_ready(closure)


def _explore_worker_status(
    worker_id: str,
    session_state: dict[str, Any],
) -> str:
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
    list_type = session_state.get("list_type")
    items: list[dict[str, str]] = []

    if session_state.get("explore_intake_blocked") or (
        list_type == "explore" and not explore_intake_submitted()
    ):
        items.append(
            {
                "id": "explore_intake",
                "title": "填写初探信息表",
                "status": "in_progress",
            }
        )
    elif list_type == "explore":
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
    elif list_type == "jd":
        items.append({"id": "jd_chain", "title": "JD 评估与策略", "status": "in_progress"})

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
    list_type = session_state.get("list_type")
    if session_state.get("explore_intake_blocked"):
        return "当前：请先填写初探信息表"
    if list_type == "explore":
        active = next((item for item in items if item["status"] == "in_progress"), None)
        if active:
            return f"当前：{LIST_TYPE_LABELS['explore']} · {active['title']}进行中"
        if all(item["status"] == "completed" for item in items if items):
            return "当前：职业初探 · 待确认收束"
        return f"当前：{LIST_TYPE_LABELS['explore']}"
    if list_type == "jd":
        return f"当前：{LIST_TYPE_LABELS['jd']}"
    return None


def explore_continue_synthesis_draft(session_state: dict[str, Any]) -> str:
    prior = session_state.get("prior_results") or {}
    identity = prior.get("identity") or {}
    if identity.get("user_visible_summary"):
        return (
            "我们仍在进行职业初探，暂不切换其他流程。"
            "你刚才的问题可以直接回在这个话题里；若需要，我可以把问题拆成几个具体选项。"
        )
    return "我们正在进行职业初探，请继续分享你的想法或回答上面的问题。"
