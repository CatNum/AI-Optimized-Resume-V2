import json
from typing import Any

from career_os.agents.lc.client import invoke_json, invoke_text, llm_enabled
from career_os.agents.lc.models import LLMRole
from career_os.agents.schemas.workers import WORKER_SCHEMAS, validate_structured_output


def plan_workers_with_llm(user_message: str, session_state: dict[str, Any]) -> list[str] | None:
    if not llm_enabled():
        return None
    flags = (session_state.get("gates") or {}).get("flags") or {}
    system = (
        "你是职业规划协调者。根据用户消息选择需要派工的 worker 列表，"
        "仅返回 JSON：{\"workers\": [\"market\",\"opportunity\"]}。"
        "可选 worker：identity,capability,market,opportunity,strategy,resume,asset。"
        "JD/岗位评估 → market,opportunity；初探 → identity,capability；"
        "已 optimize_confirmed 的简历优化 → resume,asset。"
    )
    user = json.dumps(
        {
            "message": user_message,
            "list_type": session_state.get("list_type"),
            "optimize_confirmed": flags.get("optimize_confirmed", False),
            "prior_workers": list((session_state.get("prior_results") or {}).keys()),
        },
        ensure_ascii=False,
    )
    try:
        data = invoke_json(system, user, role=LLMRole.COORDINATOR)
        if not data:
            return None
        workers = data.get("workers") or []
        allowed = set(WORKER_SCHEMAS.keys()) | {"asset"}
        return [w for w in workers if w in allowed]
    except Exception:
        return None


def synthesize_with_llm(
    user_message: str,
    draft_text: str,
    session_state: dict[str, Any],
    last_worker_result: dict[str, Any] | None,
) -> str | None:
    if not llm_enabled():
        return None
    system = (
        "你是面向用户的职业规划协调者。基于 Worker 结果用中文给出简洁、可执行的回复。"
        "不要暴露内部 worker 名称；若存在 gate 问句，保留确认意图。"
    )
    user = json.dumps(
        {
            "user_message": user_message,
            "draft": draft_text,
            "prior_results": session_state.get("prior_results"),
            "last_worker_result": last_worker_result,
            "gates": session_state.get("gates"),
        },
        ensure_ascii=False,
    )
    try:
        return invoke_text(system, user, role=LLMRole.COORDINATOR).strip()
    except Exception:
        return None


def enhance_worker_summary_with_llm(
    worker_id: str,
    goal: str,
    structured_output: dict[str, Any],
) -> dict[str, Any] | None:
    if not llm_enabled():
        return None
    schema = WORKER_SCHEMAS.get(worker_id)
    schema_hint = schema.model_json_schema() if schema else {"user_visible_summary": "string"}
    system = (
        f"你是 {worker_id} worker。返回符合 schema 的 JSON structured_output，"
        f"保留业务字段，优化 user_visible_summary 的中文质量。schema: {json.dumps(schema_hint, ensure_ascii=False)}"
    )
    user = json.dumps({"goal": goal, "structured_output": structured_output}, ensure_ascii=False)
    try:
        payload = invoke_json(system, user, role=LLMRole.WORKER)
        if not payload:
            return None
        validated, error = validate_structured_output(worker_id, payload)
        if error or not validated:
            return None
        return validated
    except Exception:
        return None
