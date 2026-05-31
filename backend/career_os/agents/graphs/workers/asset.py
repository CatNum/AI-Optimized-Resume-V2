from typing import Any

from career_os.agents.graphs.workers.base import finalize_worker_result


def run(harness: Any, goal: str, session_state: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    run_kind = context.get("run_kind") or "register"
    if run_kind == "reuse":
        payload = {
            "user_visible_summary": "建议复用上一份 HTML 作为基线。",
            "reuse_recommendation": {
                "action": "base",
                "recommended_path": context.get("reuse_path"),
                "reason": "内容相近",
            },
            "gate_prompt": {
                "name": "reuse_confirm",
                "prompt": "是否按复用建议继续？",
            },
        }
        return finalize_worker_result("asset", payload)

    deliveries = context.get("html_deliveries") or session_state.get("prior_results", {}).get(
        "resume", {}
    ).get("html_deliveries", [])
    result = harness.execute_tool(
        "asset",
        "register_outputs_index",
        {"deliveries": deliveries},
        session_id=session_state.get("session_id"),
    )
    if hasattr(result, "code"):
        return {"worker_id": "asset", "status": "failed", "error": result.message}
    payload = {
        "user_visible_summary": "产物已登记到 outputs_index。",
        "registered_deliveries": result.get("registered", []),
    }
    return finalize_worker_result("asset", payload)
