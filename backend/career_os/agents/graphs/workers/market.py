import hashlib
from typing import Any

from career_os.agents.graphs.workers.base import finalize_worker_result


def run(harness: Any, goal: str, session_state: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    families = ["后端", "云原生"]
    harness.execute_tool(
        "market",
        "profile_patch",
        {"path": "market.role_families", "value": families, "op": "set"},
        session_id=session_state.get("session_id"),
    )
    harness.execute_tool(
        "market",
        "profile_patch",
        {
            "path": "market.trend_notes",
            "value": [{"topic": "云原生后端", "summary": "需求稳定"}],
            "op": "set",
        },
        session_id=session_state.get("session_id"),
    )
    payload = {
        "user_visible_summary": "已完成市场调研，覆盖岗位族与趋势要点。",
        "topics": [{"topic": "云原生后端", "summary": "岗位需求稳定，Kubernetes 技能常见"}],
        "role_families": families,
    }
    return finalize_worker_result("market", payload)
