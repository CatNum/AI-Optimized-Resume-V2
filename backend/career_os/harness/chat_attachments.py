from pathlib import Path
from typing import Any

from career_os.platform.tool.handlers.outputs import normalize_output_path, resolve_output_file


def build_request_context_from_attachments(
    attachments: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Resolve B05 file_ref attachments into coordinator/worker context."""
    if not attachments:
        return {}

    refs: list[dict[str, Any]] = []
    for att in attachments:
        if att.get("type") != "file_ref":
            continue
        path = str(att.get("path") or "").strip()
        if not path:
            continue
        resolved = resolve_output_file(path)
        if resolved is None or not resolved.is_file():
            continue
        normalized = normalize_output_path(resolved)
        refs.append(
            {
                "path": normalized,
                "filename": Path(normalized).name,
                "optimization_level": att.get("optimization_level"),
            }
        )

    if not refs:
        return {}

    ctx: dict[str, Any] = {"resume_file_refs": refs}
    primary = refs[0]["path"]
    ctx["user_specified_resume_path"] = primary
    ctx["reuse_path"] = primary
    return ctx


def enrich_user_message_with_attachments(
    message: str,
    attachments: list[dict[str, Any]] | None,
) -> str:
    """Append a stable, human-readable reference block for chat history / LLM."""
    ctx = build_request_context_from_attachments(attachments)
    refs = ctx.get("resume_file_refs") or []
    if not refs:
        return message
    lines = [f"- {r['path']}" for r in refs]
    block = "【用户引用的简历文件】\n" + "\n".join(lines)
    base = (message or "").strip()
    return f"{base}\n\n{block}" if base else block
