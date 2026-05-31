import json
from typing import Any

import litellm

from career_os.agents.graphs.workers.base import finalize_worker_result
from career_os.agents.lc import models as models_mod
from career_os.agents.lc.client import extract_json_object
from career_os.agents.lc.models import LLMRole, resolve_llm_config
from career_os.agents.lc.tools import get_litellm_tools_for_worker
from career_os.agents.state.worker import WorkerState
from career_os.platform.prompt.loader import load_prompt, load_worker_llm_prompt, render_prompt

MAX_ITERATIONS = 12


def _format_boot_user(
    goal: str,
    session_state: dict[str, Any] | None,
    context: dict[str, Any] | None,
) -> str:
    payload = {
        "goal": goal,
        "session_state": session_state or {},
        "context": context or {},
    }
    payload = json.dumps(payload, ensure_ascii=False, indent=2)
    return render_prompt(load_worker_llm_prompt("react_boot_user"), payload=payload)


def _build_system_prompt(worker_id: str, context: dict[str, Any]) -> str:
    prompt = load_prompt(worker_id)
    bundle = context.get("capability_bundle") or {}
    skill_lines = []
    for skill in bundle.get("skill_index") or []:
        name = skill.get("name")
        desc = skill.get("description")
        if name:
            skill_lines.append(f"- {name}: {desc or ''}".rstrip())
    tool_lines = []
    for tool in bundle.get("tool_index") or []:
        name = tool.get("name")
        if name:
            tool_lines.append(f"- {name}")

    additions: list[str] = []
    if skill_lines:
        additions.append("可参考技能：\n" + "\n".join(skill_lines))
    if tool_lines:
        additions.append("可用工具：\n" + "\n".join(tool_lines))
    if not additions:
        return prompt
    return prompt + "\n\n" + "\n\n".join(additions)


def _serialize_tool_result(result: Any) -> str:
    if hasattr(result, "code"):
        message = getattr(result, "message", str(result))
        return json.dumps(
            {"error": {"code": result.code, "message": message}},
            ensure_ascii=False,
        )
    try:
        return json.dumps(result, ensure_ascii=False, default=str)
    except TypeError:
        return json.dumps({"result": str(result)}, ensure_ascii=False)


def run_worker_react(
    harness: Any,
    *,
    worker_id: str,
    goal: str,
    session_state: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    session_state = dict(session_state or {})
    context = dict(context or {})

    models_mod.model_settings.__init__()
    config = resolve_llm_config(role=LLMRole.WORKER)
    if not config.get("api_key"):
        return {
            "worker_id": worker_id,
            "status": "failed",
            "structured_output": None,
            "error": "LLM_API_KEY is not configured",
        }

    tools = get_litellm_tools_for_worker(worker_id)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _build_system_prompt(worker_id, context)},
        {"role": "user", "content": _format_boot_user(goal, session_state, context)},
    ]

    state: WorkerState = {
        "worker_id": worker_id,
        "goal": goal,
        "context": context,
        "session_state": session_state,
        "messages": messages,
        "iteration": 0,
        "max_iterations": MAX_ITERATIONS,
        "status": "running",
    }

    for iteration in range(1, MAX_ITERATIONS + 1):
        state["iteration"] = iteration
        kwargs: dict[str, Any] = {
            "model": config["litellm_model"],
            "messages": state["messages"],
            "api_key": config["api_key"],
            "temperature": config["temperature"],
            "tools": tools,
            "tool_choice": "auto",
        }
        if config.get("api_base"):
            kwargs["api_base"] = config["api_base"]

        try:
            response = litellm.completion(**kwargs)
        except Exception as exc:
            return {
                "worker_id": worker_id,
                "status": "failed",
                "structured_output": None,
                "error": f"LiteLLM completion failed: {exc}",
            }

        msg = response.choices[0].message
        if getattr(msg, "tool_calls", None):
            assistant_msg = {
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ],
            }
            state["messages"].append(assistant_msg)

            for tc in msg.tool_calls:
                args_raw = tc.function.arguments or "{}"
                args: dict[str, Any] = {}
                if isinstance(args_raw, str):
                    try:
                        parsed = json.loads(args_raw)
                        if isinstance(parsed, dict):
                            args = parsed
                    except json.JSONDecodeError:
                        args = {}
                elif isinstance(args_raw, dict):
                    args = args_raw

                tool_result = harness.execute_tool(
                    worker_id,
                    tc.function.name,
                    args,
                    session_id=session_state.get("session_id"),
                )
                state["messages"].append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": tc.function.name,
                        "content": _serialize_tool_result(tool_result),
                    }
                )
            continue

        content = msg.content or ""
        state["messages"].append({"role": "assistant", "content": content})
        payload = extract_json_object(content)
        if payload is None:
            return {
                "worker_id": worker_id,
                "status": "failed",
                "structured_output": None,
                "error": "No valid JSON object found in worker response",
            }
        return finalize_worker_result(worker_id, payload)

    return {
        "worker_id": worker_id,
        "status": "failed",
        "structured_output": None,
        "error": f"Reached max iterations ({MAX_ITERATIONS})",
    }
