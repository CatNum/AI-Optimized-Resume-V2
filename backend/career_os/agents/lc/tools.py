from typing import Any

from career_os.platform.tool.registry import WORKER_BUSINESS_TOOLS, WORKER_META_TOOLS

TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "load_skill": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "mode": {"type": "string"},
        },
        "required": ["name"],
    },
    "list_skills": {"type": "object", "properties": {}},
    "profile_patch": {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "value": {},
            "op": {"type": "string", "enum": ["set", "append"]},
        },
        "required": ["path", "value"],
    },
    "browser_fetch": {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
    "write_resume_html": {
        "type": "object",
        "properties": {
            "html": {"type": "string"},
            "content": {"type": "string"},
            "filename": {"type": "string"},
            "optimization_level": {
                "type": "string",
                "enum": ["保守", "标准", "进取"],
            },
            "filename_tags": {
                "type": "array",
                "items": {"type": "string"},
            },
            "target_role": {"type": "string"},
            "tech_stack_tags": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
    },
    "register_outputs_index": {
        "type": "object",
        "properties": {
            "deliveries": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "optimization_level": {"type": "string"},
                        "created_at": {"type": "string"},
                    },
                    "required": ["path"],
                },
            },
        },
        "required": ["deliveries"],
    },
    "resume_read": {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
        },
    },
    "delete_output": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "pattern": "^output/"},
        },
        "required": ["path"],
    },
}


def get_litellm_tools_for_worker(worker_id: str) -> list[dict[str, Any]]:
    allowed = set(WORKER_META_TOOLS) | WORKER_BUSINESS_TOOLS.get(worker_id, set())
    tools: list[dict[str, Any]] = []
    for name in sorted(allowed):
        schema = TOOL_SCHEMAS.get(name)
        if not schema:
            continue
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": f"Harness tool {name} for worker {worker_id}",
                    "parameters": schema,
                },
            }
        )
    return tools
