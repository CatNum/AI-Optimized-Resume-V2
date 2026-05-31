import json
from typing import Any

from career_os.agents.lc.client import invoke_json, llm_enabled
from career_os.agents.lc.models import LLMRole
from career_os.agents.schemas.workers import WORKER_SCHEMAS, validate_structured_output
from career_os.platform.prompt.loader import load_worker_llm_prompt, render_prompt


def enhance_worker_summary_with_llm(
    worker_id: str,
    goal: str,
    structured_output: dict[str, Any],
) -> dict[str, Any] | None:
    if not llm_enabled():
        return None
    schema = WORKER_SCHEMAS.get(worker_id)
    schema_hint = schema.model_json_schema() if schema else {"user_visible_summary": "string"}
    system = render_prompt(
        load_worker_llm_prompt("enhance_summary"),
        worker_id=worker_id,
        schema=json.dumps(schema_hint, ensure_ascii=False),
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
