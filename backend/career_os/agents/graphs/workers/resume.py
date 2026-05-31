from typing import Any

from career_os.agents.graphs.workers.base import finalize_worker_result
from career_os.platform.tool.handlers.resume_html import sort_optimization_levels


def run(harness: Any, goal: str, session_state: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    levels = sort_optimization_levels(
        context.get("selected_optimization_levels") or ["标准"]
    )
    deliveries: list[dict[str, Any]] = []
    for level in levels:
        result = harness.execute_tool(
            "resume",
            "write_resume_html",
            {
                "html": f"<html><body><h1>{level}</h1></body></html>",
                "filename": f"resume_{level}.html",
                "optimization_level": level,
            },
            session_id=session_state.get("session_id"),
        )
        if hasattr(result, "code"):
            return {"worker_id": "resume", "status": "failed", "error": result.message}
        deliveries.append(result)
    harness.execute_tool(
        "resume",
        "profile_patch",
        {"path": "resume.last_optimization_levels", "value": levels, "op": "set"},
        session_id=session_state.get("session_id"),
    )
    payload = {
        "user_visible_summary": f"已生成 {len(deliveries)} 份简历 HTML。",
        "html_deliveries": deliveries,
    }
    return finalize_worker_result("resume", payload)
