import json
from typing import Any

from career_os.agents.lc.client import invoke_json, llm_enabled
from career_os.agents.lc.models import LLMRole


def fallback_analyze_workers(
    user_message: str,
    session_state: dict[str, Any],
) -> dict[str, Any] | None:
    text = user_message.lower()
    prior = session_state.get("prior_results") or {}
    flags = (session_state.get("gates") or {}).get("flags") or {}

    if "jd" in text or "岗位" in user_message or "job" in text:
        return {"workers": ["market", "opportunity"], "list_type": "jd"}
    if "初探" in user_message or "explore" in text:
        return {"workers": ["identity", "capability"], "list_type": "explore"}

    if session_state.get("list_type") == "jd":
        if (
            "market" in prior
            and "opportunity" in prior
            and "strategy" not in prior
            and any(k in user_message for k in ("策略", "继续", "下一步", "制定"))
        ):
            return {"workers": ["strategy"]}

    if flags.get("optimize_confirmed"):
        if ("优化" in user_message or "resume" in text) and "resume" not in prior:
            return {"workers": ["resume", "asset"]}
    return None


def analyze_workers(
    user_message: str,
    session_state: dict[str, Any],
    worker_index: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not llm_enabled():
        return None

    worker_summary: list[dict[str, Any]] = []
    allowed_workers: set[str] = set()
    for worker in worker_index:
        worker_id = worker.get("worker_id")
        if not worker_id:
            continue
        allowed_workers.add(worker_id)
        worker_summary.append(
            {
                "worker_id": worker_id,
                "summary": worker.get("summary", ""),
                "when_to_use": worker.get("when_to_use", []),
            }
        )

    system = (
        "你是职业规划协调者 analyze 节点。根据用户消息与会话状态选择本轮 worker。"
        "仅返回 JSON：{\"workers\": [\"market\",\"opportunity\"], \"list_type\": \"jd\"}。"
        "workers 只能来自输入的 worker_index；list_type 可选值：jd、explore。"
    )
    user = json.dumps(
        {
            "message": user_message,
            "list_type": session_state.get("list_type"),
            "gates": session_state.get("gates"),
            "prior_workers": list((session_state.get("prior_results") or {}).keys()),
            "worker_index": worker_summary,
        },
        ensure_ascii=False,
    )
    try:
        data = invoke_json(system, user, role=LLMRole.COORDINATOR)
        if not data:
            return None

        workers = data.get("workers")
        if not isinstance(workers, list):
            workers = []
        selected = [w for w in workers if isinstance(w, str) and w in allowed_workers]

        result: dict[str, Any] = {"workers": selected}
        list_type = data.get("list_type")
        if isinstance(list_type, str) and list_type in {"jd", "explore"}:
            result["list_type"] = list_type
        return result
    except Exception:
        return None
