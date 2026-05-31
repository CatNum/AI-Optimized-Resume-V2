from typing import Any

from career_os.agents.graphs.workers.base import finalize_worker_result
from career_os.platform.store.profile import ProfileStore


def run(harness: Any, goal: str, session_state: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    harness.execute_tool(
        "identity",
        "profile_patch",
        {
            "path": "exploration.summary",
            "value": "用户重视技术深度与稳定团队。",
            "op": "set",
        },
        session_id=session_state.get("session_id"),
    )
    payload = {
        "user_visible_summary": "已完成 identity 初探线，归纳内心诉求草案。",
        "exploration_draft": {"summary": "用户重视技术深度与稳定团队。"},
    }
    return finalize_worker_result("identity", payload)
