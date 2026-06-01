from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_PROMPT_DIR = Path(__file__).resolve().parent
_FRONTMATTER_RE = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)
_SECTION_RE = re.compile(r"^### ([^\n]+)\n", re.MULTILINE)


def _strip_frontmatter(text: str) -> str:
    return _FRONTMATTER_RE.sub("", text, count=1).strip()


def _read_system_document(path: Path) -> str:
    return _strip_frontmatter(path.read_text(encoding="utf-8"))


def _parse_sections(body: str) -> dict[str, str]:
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
    path = _PROMPT_DIR / "gate_intent" / "system.md"
    return _read_system_document(path)
