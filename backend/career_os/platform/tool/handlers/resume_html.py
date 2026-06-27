from dataclasses import dataclass
from datetime import date
import re
from pathlib import Path
from typing import Any

from career_os.config import settings
from career_os.platform.store.output import OutputStore
from career_os.platform.tool.handlers.outputs import normalize_output_path

LEVEL_ORDER = ["保守", "标准", "进取"]

_RE_HTML_ROOT = re.compile(r"<html\b", re.IGNORECASE)
_RE_BODY_OPEN = re.compile(r"<body\b", re.IGNORECASE)
_RE_HTML_CLOSE = re.compile(r"</html\s*>", re.IGNORECASE)
_RE_BODY_CLOSE = re.compile(r"</body\s*>", re.IGNORECASE)
_RE_DOC_START = re.compile(r"<(!DOCTYPE|html|head|body)\b", re.IGNORECASE)


def validate_resume_html_content(content: str) -> tuple[bool, str]:
    """返回 (ok, message)，拒绝伪装成 .html 的纯文本或 Markdown 简历。"""
    stripped = (content or "").strip()
    if not stripped:
        return False, "简历 HTML 内容为空"
    if "<" not in stripped or ">" not in stripped:
        return (
            False,
            "内容未包含 HTML 标签；须输出完整 HTML 文档，不可写入纯文本或 Markdown。",
        )
    if not _RE_HTML_ROOT.search(stripped):
        return False, "缺少 <html> 根元素；须包含 <!DOCTYPE html> 与 <html>…</html>。"
    if not _RE_BODY_OPEN.search(stripped):
        return False, "缺少 <body> 元素。"
    if not _RE_HTML_CLOSE.search(stripped):
        return False, "缺少 </html> 闭合标签。"
    if not _RE_BODY_CLOSE.search(stripped):
        return False, "缺少 </body> 闭合标签。"
    head = stripped[:400].lstrip()
    if not _RE_DOC_START.search(head):
        return (
            False,
            "文档须以 HTML 结构开头（<!DOCTYPE html> 或 <html>），勿将正文纯文本直接写入文件。",
        )
    return True, ""


def ensure_html_filename(filename: str) -> str:
    """ensure_html_filename（ensure html filename）的函数说明。

    filename（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    name = (filename or "resume").strip() or "resume"
    if not name.lower().endswith(".html"):
        name = f"{name}.html"
    return name


def _sanitize_tag(tag: str) -> str:
    """_sanitize_tag（内部函数 sanitize tag）的函数说明。

    tag（参数）用于向该函数传入运行所需的数据。

    该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
    text = re.sub(r"[\\/:*?\"<>|]+", "_", (tag or "").strip())
    text = re.sub(r"\s+", "_", text).strip("._-")
    if len(text) > 16:
        text = text[:16].rstrip("._-")
    return text


def _normalize_filename_tags(raw_tags: list[str] | None) -> list[str]:
    """_normalize_filename_tags（内部函数 normalize filename tags）的函数说明。

    raw_tags（参数）用于向该函数传入运行所需的数据。

    该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
    tags = [_sanitize_tag(str(tag)) for tag in (raw_tags or [])]
    uniq: list[str] = []
    for tag in tags:
        if tag and tag not in uniq:
            uniq.append(tag)
        if len(uniq) >= 3:
            break
    return uniq


def _derive_filename_tags(args: dict[str, Any]) -> list[str]:
    """_derive_filename_tags（内部函数 derive filename tags）的函数说明。

    args（参数）用于向该函数传入运行所需的数据。

    该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
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
    """_build_prd_filename（内部函数 build prd filename）的函数说明。

    day（参数）、tags（参数）、level（参数）用于向该函数传入运行所需的数据。

    该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
    level_name = level if level in LEVEL_ORDER else "标准"
    summary = "-".join(tags) if tags else "通用"
    return f"{day.isoformat()}-{summary}-{level_name}.html"


def _ensure_unique_filename(filename: str, day: date) -> str:
    """_ensure_unique_filename（内部函数 ensure unique filename）的函数说明。

    filename（参数）、day（参数）用于向该函数传入运行所需的数据。

    该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
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
    """ResumeHtmlError（ResumeHtmlError）的项目代码结构说明。

    该类封装当前模块中的一组相关状态或行为，供业务代码、测试代码或运行时流程复用。"""
    code: str
    message: str


def write_resume_html(actor: str, args: dict[str, Any]) -> ResumeHtmlError | dict[str, Any]:
    """write_resume_html（write resume html）的函数说明。

    actor（参数）、args（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    if actor != "resume":
        return ResumeHtmlError("tool_not_allowed", "write_resume_html is resume-only")
    content = args.get("html") or args.get("content") or ""
    ok, reason = validate_resume_html_content(content)
    if not ok:
        return ResumeHtmlError("invalid_html", reason)
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
    """按固定顺序排序简历优化等级。

    levels（优化等级列表）通常包含 保守、标准、进取。
    返回值会按 LEVEL_ORDER（等级顺序）排序，未知等级排在最后。
    """
    order = {name: idx for idx, name in enumerate(LEVEL_ORDER)}
    return sorted(levels, key=lambda x: order.get(x, 99))
