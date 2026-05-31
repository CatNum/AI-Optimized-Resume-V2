from dataclasses import dataclass
from datetime import date
from typing import Any

from career_os.platform.store.output import OutputStore
from career_os.platform.tool.handlers.outputs import normalize_output_path

LEVEL_ORDER = ["保守", "标准", "进取"]


@dataclass
class ResumeHtmlError:
    code: str
    message: str


def write_resume_html(actor: str, args: dict[str, Any]) -> ResumeHtmlError | dict[str, Any]:
    if actor != "resume":
        return ResumeHtmlError("tool_not_allowed", "write_resume_html is resume-only")
    content = args.get("html") or args.get("content") or ""
    filename = args.get("filename") or "resume.html"
    level = args.get("optimization_level") or "标准"
    store = OutputStore()
    path = store.write(filename, content, day=date.today())
    return {
        "path": normalize_output_path(path),
        "optimization_level": level,
        "filename_tags": args.get("filename_tags") or [],
    }


def sort_optimization_levels(levels: list[str]) -> list[str]:
    order = {name: idx for idx, name in enumerate(LEVEL_ORDER)}
    return sorted(levels, key=lambda x: order.get(x, 99))
