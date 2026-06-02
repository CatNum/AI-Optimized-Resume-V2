from dataclasses import dataclass
from datetime import date
import re
from pathlib import Path
from typing import Any

from career_os.config import settings
from career_os.platform.store.output import OutputStore
from career_os.platform.tool.handlers.outputs import normalize_output_path

LEVEL_ORDER = ["保守", "标准", "进取"]


def ensure_html_filename(filename: str) -> str:
    name = (filename or "resume").strip() or "resume"
    if not name.lower().endswith(".html"):
        name = f"{name}.html"
    return name


def _sanitize_tag(tag: str) -> str:
    text = re.sub(r"[\\/:*?\"<>|]+", "_", (tag or "").strip())
    text = re.sub(r"\s+", "_", text).strip("._-")
    if len(text) > 16:
        text = text[:16].rstrip("._-")
    return text


def _normalize_filename_tags(raw_tags: list[str] | None) -> list[str]:
    tags = [_sanitize_tag(str(tag)) for tag in (raw_tags or [])]
    uniq: list[str] = []
    for tag in tags:
        if tag and tag not in uniq:
            uniq.append(tag)
        if len(uniq) >= 3:
            break
    return uniq


def _derive_filename_tags(args: dict[str, Any]) -> list[str]:
    manual = _normalize_filename_tags(args.get("filename_tags"))
    if manual:
        return manual
    auto_source: list[str] = []
    target_role = str(args.get("target_role") or "").strip()
    if target_role:
        auto_source.append(target_role)
    for item in args.get("tech_stack_tags") or []:
        text = str(item).strip()
        if text:
            auto_source.append(text)
    return _normalize_filename_tags(auto_source)


def _build_prd_filename(day: date, tags: list[str], level: str) -> str:
    level_name = level if level in LEVEL_ORDER else "标准"
    summary = "-".join(tags) if tags else "通用"
    return f"{day.isoformat()}-{summary}-{level_name}.html"


def _ensure_unique_filename(filename: str, day: date) -> str:
    day_dir = Path(settings.output_dir).resolve() / day.isoformat()
    candidate = day_dir / filename
    if not candidate.exists():
        return filename
    stem = candidate.stem
    suffix = candidate.suffix or ".html"
    idx = 1
    while True:
        next_name = f"{stem}({idx}){suffix}"
        if not (day_dir / next_name).exists():
            return next_name
        idx += 1


@dataclass
class ResumeHtmlError:
    code: str
    message: str


def write_resume_html(actor: str, args: dict[str, Any]) -> ResumeHtmlError | dict[str, Any]:
    if actor != "resume":
        return ResumeHtmlError("tool_not_allowed", "write_resume_html is resume-only")
    content = args.get("html") or args.get("content") or ""
    level = args.get("optimization_level") or "标准"
    today = date.today()
    tags = _derive_filename_tags(args)
    filename = _build_prd_filename(today, tags, level)
    filename = _ensure_unique_filename(filename, today)
    store = OutputStore()
    path = store.write(filename, content, day=today)
    return {
        "path": normalize_output_path(path),
        "optimization_level": level,
        "filename_tags": tags,
    }


def sort_optimization_levels(levels: list[str]) -> list[str]:
    order = {name: idx for idx, name in enumerate(LEVEL_ORDER)}
    return sorted(levels, key=lambda x: order.get(x, 99))
