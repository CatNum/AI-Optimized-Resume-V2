from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_PROMPT_DIR = Path(__file__).resolve().parent
_FRONTMATTER_RE = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)
_SECTION_RE = re.compile(r"^### ([^\n]+)\n", re.MULTILINE)


def _strip_frontmatter(text: str) -> str:
    """_strip_frontmatter（内部函数 strip frontmatter）的函数说明。

    text（参数）用于向该函数传入运行所需的数据。

    该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
    return _FRONTMATTER_RE.sub("", text, count=1).strip()


def _read_system_document(path: Path) -> str:
    """_read_system_document（内部函数 read system document）的函数说明。

    path（参数）用于向该函数传入运行所需的数据。

    该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
    return _strip_frontmatter(path.read_text(encoding="utf-8"))


def _parse_sections(body: str) -> dict[str, str]:
    """_parse_sections（内部函数 parse sections）的函数说明。

    body（参数）用于向该函数传入运行所需的数据。

    该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
    matches = list(_SECTION_RE.finditer(body))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        name = match.group(1).strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        sections[name] = body[start:end].strip()
    return sections


@lru_cache(maxsize=32)
def load_worker_system_prompt(worker_id: str) -> str:
    """Load worker agent prompt from platform/prompt/{worker_id}/system.md."""
    md_path = _PROMPT_DIR / worker_id / "system.md"
    if md_path.exists():
        return _read_system_document(md_path)
    legacy_path = _PROMPT_DIR / worker_id / "default.tmpl"
    if legacy_path.exists():
        return legacy_path.read_text(encoding="utf-8")
    return f"You are the {worker_id} worker."


def load_prompt(worker_id: str, name: str = "default") -> str:
    """加载指定 Worker 的 prompt。

    worker_id（工作者标识）决定读取哪个 prompt 目录；
    name（模板名称）默认为 default，表示读取系统 prompt。
    返回值是 prompt 文本；如果指定模板不存在，会回退到 Worker system prompt。
    """
    if name == "default":
        return load_worker_system_prompt(worker_id)
    path = _PROMPT_DIR / worker_id / f"{name}.tmpl"
    if not path.exists():
        return load_worker_system_prompt(worker_id)
    return path.read_text(encoding="utf-8")


def load_worker_llm_prompt(name: str) -> str:
    """Load shared worker LLM prompt from platform/prompt/worker/{name}.tmpl."""
    path = _PROMPT_DIR / "worker" / f"{name}.tmpl"
    return path.read_text(encoding="utf-8")


def render_prompt(template: str, **replacements: str) -> str:
    """Replace __KEY__ placeholders without interpreting JSON braces."""
    result = template
    for key, value in replacements.items():
        result = result.replace(f"__{key.upper()}__", value)
    return result


@dataclass(frozen=True)
class CoordinatorPrompt:
    """Structured entry-router agent prompt (platform/prompt/coordinator/system.md)."""

    system: str
    chat_only_draft: str
    jd_prerequisite_draft_onboarding: str
    jd_prerequisite_draft_explore: str


@lru_cache(maxsize=1)
def load_coordinator_prompt() -> CoordinatorPrompt:
    """加载 Coordinator 结构化 prompt。

    返回值是 CoordinatorPrompt（协调器提示词对象），包含 system（系统提示词）、
    chat_only_draft（纯聊天草稿）和 JD 前置条件提示草稿。
    """
    path = _PROMPT_DIR / "coordinator" / "system.md"
    raw = path.read_text(encoding="utf-8")
    body = _strip_frontmatter(raw)
    sections = _parse_sections(body)
    chat_only_draft = sections.get("chat_only_draft", "")
    if not chat_only_draft:
        raise ValueError("coordinator prompt missing ### chat_only_draft section")
    onboarding = sections.get("jd_prerequisite_draft_onboarding", "")
    explore = sections.get("jd_prerequisite_draft_explore", "")
    if not onboarding or not explore:
        raise ValueError("coordinator prompt missing jd_prerequisite_draft sections")
    return CoordinatorPrompt(
        system=body,
        chat_only_draft=chat_only_draft,
        jd_prerequisite_draft_onboarding=onboarding,
        jd_prerequisite_draft_explore=explore,
    )


@lru_cache(maxsize=1)
def load_gate_intent_prompt() -> str:
    """load_gate_intent_prompt（load gate intent prompt）的函数说明。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    path = _PROMPT_DIR / "gate_intent" / "system.md"
    return _read_system_document(path)


@lru_cache(maxsize=8)
def load_micro_classifier_prompt(task: str) -> str:
    """load_micro_classifier_prompt（load micro classifier prompt）的函数说明。

    task（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    path = _PROMPT_DIR / "micro_classifier" / task / "system.md"
    if not path.exists():
        raise FileNotFoundError(f"micro_classifier prompt not found: {task}")
    return _read_system_document(path)
