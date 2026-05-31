"""Deterministic ReAct stand-ins for L1 tests when LLM_API_KEY is absent."""
from typing import Any

from career_os.agents.graphs.workers.base import finalize_worker_result


def mock_run_worker_react(
    harness: Any,
    *,
    worker_id: str,
    goal: str,
    session_state: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    session_id = session_state.get("session_id")
    if worker_id == "market":
        harness.execute_tool(
            "market",
            "profile_patch",
            {"path": "market.role_families", "value": ["后端", "云原生"], "op": "set"},
            session_id=session_id,
        )
        harness.execute_tool(
            "market",
            "profile_patch",
            {
                "path": "market.trend_notes",
                "value": [{"topic": "云原生后端", "summary": "需求稳定"}],
                "op": "set",
            },
            session_id=session_id,
        )
        return finalize_worker_result(
            "market",
            {
                "user_visible_summary": "已完成市场调研，覆盖岗位族与趋势要点。",
                "topics": [{"topic": "云原生后端", "summary": "岗位需求稳定，Kubernetes 技能常见"}],
            },
        )

    if worker_id == "opportunity":
        import hashlib

        fingerprint = hashlib.sha256(goal.encode()).hexdigest()[:12]
        snapshots = [
            {
                "jd_fingerprint": fingerprint,
                "recommendation": "recommended",
                "summary": "与当前能力画像匹配度较高",
            }
        ]
        harness.execute_tool(
            "opportunity",
            "profile_patch",
            {"path": "market.opportunity_snapshots", "value": snapshots, "op": "set"},
            session_id=session_id,
        )
        return finalize_worker_result(
            "opportunity",
            {
                "recommendation": "recommended",
                "user_visible_summary": "JD 评估完成，建议继续策略制定。",
                "jd_fingerprint": fingerprint,
            },
        )

    return {
        "worker_id": worker_id,
        "status": "failed",
        "error": f"No L1 mock for react worker {worker_id}",
    }
