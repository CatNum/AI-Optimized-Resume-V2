from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_PROMPT_DIR = Path(__file__).resolve().parent
_FRONTMATTER_RE = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)
_SECTION_RE = re.compile(r"^### ([^\n]+)\n", re.MULTILINE)


def _strip_frontmatter(text: str) -> str:
    """去除frontmatter。"""
    return _FRONTMATTER_RE.sub("", text, count=1).strip()


def _read_system_document(path: Path) -> str:
    """读取system document。"""
    return _strip_frontmatter(path.read_text(encoding="utf-8"))


def _parse_sections(body: str) -> dict[str, str]:
    """解析sections。"""
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
    """从 platform/prompt/{worker_id}/system.md 加载 Worker agent prompt。"""
    md_path = _PROMPT_DIR / worker_id / "system.md"
    if md_path.exists():
        return _read_system_document(md_path)
    legacy_path = _PROMPT_DIR / worker_id / "default.tmpl"
    if legacy_path.exists():
        return legacy_path.read_text(encoding="utf-8")
    return f"You are the {worker_id} worker."


def load_prompt(worker_id: str, name: str = "default") -> str:
    """加载指定 Worker 的 prompt。"""
    if name == "default":
        return load_worker_system_prompt(worker_id)
    path = _PROMPT_DIR / worker_id / f"{name}.tmpl"
    if not path.exists():
        return load_worker_system_prompt(worker_id)
    return path.read_text(encoding="utf-8")


def load_worker_llm_prompt(name: str) -> str:
    """从 platform/prompt/worker/{name}.tmpl 加载共享 Worker LLM prompt。"""
    path = _PROMPT_DIR / "worker" / f"{name}.tmpl"
    return path.read_text(encoding="utf-8")


def render_prompt(template: str, **replacements: str) -> str:
    """替换 __KEY__ 占位符，但不解析 JSON 大括号。"""
    result = template
    for key, value in replacements.items():
        result = result.replace(f"__{key.upper()}__", value)
    return result


@dataclass(frozen=True)
class CoordinatorPrompt:
    """
    CoordinatorPrompt（协调器提示词）承载结构化入口路由 Agent 的 prompt 文本。
    """

    system: str  # 系统提示词
    chat_only_draft: str  # 纯聊天草稿
    jd_prerequisite_draft_onboarding: str  # onboarding 阻断草稿
    jd_prerequisite_draft_explore: str  # 初探阻断草稿


@lru_cache(maxsize=1)
def load_coordinator_prompt() -> CoordinatorPrompt:
    """加载 Coordinator 结构化 prompt。"""
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
    """加载gate intent prompt。"""
    path = _PROMPT_DIR / "gate_intent" / "system.md"
    return _read_system_document(path)


@lru_cache(maxsize=8)
def load_micro_classifier_prompt(task: str) -> str:
    """加载micro classifier prompt。"""
    path = _PROMPT_DIR / "micro_classifier" / task / "system.md"
    if not path.exists():
        raise FileNotFoundError(f"micro_classifier prompt not found: {task}")
    return _read_system_document(path)


@lru_cache(maxsize=1)
def load_market_research_extraction_prompt() -> str:
    """加载市场岗位受限语义提取 System Prompt，不向其中拼接 JD 原文。"""
    path = _PROMPT_DIR / "market_research" / "extraction_system.md"
    return _read_system_document(path)


@lru_cache(maxsize=1)
def load_market_research_direction_prompt() -> str:
    """加载单方向只读综合 Prompt；输入只允许结构化语义和冻结统计。"""
    path = _PROMPT_DIR / "market_research" / "direction_system.md"
    return _read_system_document(path)


@lru_cache(maxsize=1)
def load_market_research_comparison_prompt() -> str:
    """加载多方向并列对照 Prompt；禁止排名、匹配、评分或推荐。"""
    path = _PROMPT_DIR / "market_research" / "comparison_system.md"
    return _read_system_document(path)
