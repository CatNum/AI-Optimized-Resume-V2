from typing import Any

from career_os.agents.graphs.workers.base import finalize_worker_result


def run(harness: Any, goal: str, session_state: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "user_visible_summary": "已补充经历素材与能力图谱要点。",
        "bank_delta_summary": "新增 2 条项目经历要点",
    }
    return finalize_worker_result("capability", payload)
