from typing import Any

from career_os.agents.graphs.workers.base import finalize_worker_result


def run(harness: Any, goal: str, session_state: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    list_type = session_state.get("list_type") or context.get("list_type")
    payload: dict[str, Any] = {
        "user_visible_summary": "已给出三条路径与三时间维度策略。",
        "path_options": [
            {"id": "path_a", "label": "稳健投递", "summary": "匹配当前 JD", "risks": []}
        ],
        "three_horizons": {
            "apply_narrative": "先聚焦匹配 JD 投递",
            "horizon_1_2y": "强化云原生项目背书",
            "horizon_3_5y": "技术负责人方向",
        },
    }
    if list_type == "jd" and context.get("requires_optimize_gate", True):
        payload["gate_prompt"] = {
            "name": "optimize_confirm",
            "prompt": "是否确认按该 JD 优化简历？",
        }
    elif list_type == "plan":
        payload.pop("gate_prompt", None)
    return finalize_worker_result("strategy", payload)
