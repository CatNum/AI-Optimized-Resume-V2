"""Resolve which profile (long-term memory) sections apply to a turn and materialize for LLM calls."""

from __future__ import annotations

from typing import Any

from career_os.harness.explore_intake import explore_intake_submitted
from career_os.harness.micro_classifier import classify
from career_os.harness.micro_classifier_rules import match_profile_memory_rules
from career_os.harness.pipeline_routing import get_current_phase
from career_os.platform.store.profile import ProfileStore
from career_os.platform.store.session import SessionStore

# Logical section id -> ProfileStore.get path prefixes
SECTION_PATHS: dict[str, tuple[str, ...]] = {
    "resume": ("resume", "exploration"),
    "basic_intent": ("basic", "intent"),
    "exploration": ("exploration",),
    "market": ("market",),
    "strategy": ("strategy",),
    "capability": ("capability",),
}

WORKERS_REQUIRE_RESUME: frozenset[str] = frozenset(
    {"market", "opportunity", "strategy", "resume", "asset"}
)

PHASES_REQUIRE_RESUME: frozenset[str] = frozenset(
    {"market", "jd_analysis", "resume_strategy", "resume_optimize"}
)

_ANALYZE_RESUME_SNIPPET_CHARS = 1200


def _phase_requires_resume(session_state: dict[str, Any]) -> bool:
    phase = get_current_phase(session_state) or "explore"
    return phase in PHASES_REQUIRE_RESUME


def resolve_profile_memory_sections(
    user_message: str,
    session_state: dict[str, Any],
    *,
    worker_id: str | None = None,
) -> list[str]:
    """Return ordered section ids to load for this turn (rules + classifier + mandatory resume)."""
    found: set[str] = set(match_profile_memory_rules(user_message))

    if worker_id and worker_id in WORKERS_REQUIRE_RESUME:
        found.add("resume")
    if _phase_requires_resume(session_state):
        found.add("resume")
        if (get_current_phase(session_state) or "") in {
            "jd_analysis",
            "resume_strategy",
            "resume_optimize",
        }:
            found.add("market")
        if (get_current_phase(session_state) or "") in {
            "resume_strategy",
            "resume_optimize",
        }:
            found.add("strategy")

    classified = classify(
        "profile_memory_scope",
        user_message,
        context={
            "current_phase": get_current_phase(session_state),
            "worker_id": worker_id,
            "list_type": session_state.get("list_type"),
        },
    )
    if classified.get("source") in {"rule", "llm"} and (
        float(classified.get("confidence") or 0) >= 0.6
        or classified.get("source") == "rule"
    ):
        for section in classified.get("sections") or []:
            if section in SECTION_PATHS:
                found.add(section)

    order = ("resume", "basic_intent", "exploration", "market", "strategy", "capability")
    return [s for s in order if s in found]


def _resume_payload(
    profile: dict[str, Any],
    *,
    full_text: bool,
    intake_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resume = profile.get("resume") or {}
    exploration = profile.get("exploration") or {}
    intake = intake_override or exploration.get("intake") or {}
    source = (resume.get("source_text") or intake.get("resume_text") or "").strip()
    basic = profile.get("basic") or {}
    intent = profile.get("intent") or {}
    summary_parts = [
        p
        for p in [
            basic.get("name"),
            basic.get("years_of_experience") and f"{basic.get('years_of_experience')}年经验",
            intent.get("target_role"),
        ]
        if p
    ]
    out: dict[str, Any] = {
        "resume_on_file": bool(source),
        "intake_submitted": explore_intake_submitted(profile),
        "submitted_at": intake.get("submitted_at"),
        "summary": " · ".join(str(x) for x in summary_parts) if summary_parts else None,
    }
    if full_text and source:
        out["source_text"] = source
    elif source:
        cap = _ANALYZE_RESUME_SNIPPET_CHARS
        out["source_excerpt"] = source[:cap] + ("…" if len(source) > cap else "")
    return out


def _session_artifact_memory(session_state: dict[str, Any] | None) -> dict[str, Any]:
    state = session_state or {}
    prior = state.get("prior_results") or {}
    artifacts: dict[str, Any] = {}
    session_id = state.get("session_id")
    if session_id:
        artifacts = SessionStore().get_artifacts(session_id)
    ref_artifacts: list[dict[str, Any]] = []
    for ref in state.get("artifact_refs") or []:
        if isinstance(ref, str):
            ref_artifacts.append(SessionStore().get_artifacts(ref))
    out: dict[str, Any] = {}
    if isinstance(artifacts.get("market"), dict) and artifacts.get("market"):
        out["market"] = artifacts.get("market") or {}
    elif isinstance(prior.get("market"), dict):
        out["market"] = prior.get("market") or {}
    if isinstance(artifacts.get("strategy"), dict) and artifacts.get("strategy"):
        out["strategy"] = artifacts.get("strategy") or {}
    elif isinstance(prior.get("strategy"), dict):
        out["strategy"] = prior.get("strategy") or {}
    exploration: dict[str, Any] = {}
    for key in ("identity", "capability"):
        blob = (artifacts.get("exploration") or {}).get(key)
        if isinstance(blob, dict):
            exploration[key] = blob
    for worker_id in ("identity", "capability"):
        blob = prior.get(worker_id)
        if isinstance(blob, dict):
            exploration[worker_id] = blob
    if exploration:
        out["exploration"] = exploration
    # Explicit references only; do not auto-load historical sessions.
    for ref_blob in ref_artifacts:
        if not out.get("market") and isinstance(ref_blob.get("market"), dict):
            out["market"] = ref_blob.get("market") or {}
        if not out.get("strategy") and isinstance(ref_blob.get("strategy"), dict):
            out["strategy"] = ref_blob.get("strategy") or {}
        if not out.get("exploration") and isinstance(ref_blob.get("exploration"), dict):
            out["exploration"] = ref_blob.get("exploration") or {}
    return out


def materialize_profile_memory(
    sections: list[str],
    *,
    full_resume_text: bool = False,
    session_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not sections:
        return {}
    paths: list[str] = []
    for section in sections:
        paths.extend(SECTION_PATHS.get(section, ()))
    paths = list(dict.fromkeys(paths))
    profile = ProfileStore().get(paths)

    memory: dict[str, Any] = {"sections_loaded": sections}
    session_memory = _session_artifact_memory(session_state)
    if "resume" in sections:
        intake_override = (
            (session_state or {}).get("intake_status")
            if isinstance((session_state or {}).get("intake_status"), dict)
            else None
        )
        memory["resume"] = _resume_payload(
            profile, full_text=full_resume_text, intake_override=intake_override
        )
    if "basic_intent" in sections:
        memory["basic"] = profile.get("basic") or {}
        memory["intent"] = profile.get("intent") or {}
    if "exploration" in sections:
        if session_memory.get("exploration"):
            memory["exploration"] = session_memory["exploration"]
        else:
            exploration = dict(profile.get("exploration") or {})
            exploration.pop("intake", None)
            memory["exploration"] = exploration
    if "market" in sections:
        memory["market"] = session_memory.get("market") or {}
    if "strategy" in sections:
        memory["strategy"] = session_memory.get("strategy") or {}
    if "capability" in sections:
        memory["capability"] = profile.get("capability") or {}
    return memory


def attach_profile_memory_to_context(
    context: dict[str, Any],
    user_message: str,
    session_state: dict[str, Any],
    *,
    worker_id: str | None = None,
) -> None:
    sections = resolve_profile_memory_sections(
        user_message, session_state, worker_id=worker_id
    )
    full_resume = bool(worker_id and worker_id in WORKERS_REQUIRE_RESUME)
    memory = materialize_profile_memory(
        sections, full_resume_text=full_resume, session_state=session_state
    )
    if memory:
        context["profile_memory"] = memory
        context["profile_memory_sections"] = sections


def format_profile_memory_for_draft(memory: dict[str, Any]) -> str:
    if not memory:
        return "（本轮未加载档案切片）"
    lines: list[str] = []
    resume = memory.get("resume") or {}
    if resume:
        if resume.get("resume_on_file"):
            lines.append(
                "档案中已有用户简历"
                + (f"（{resume['summary']}）" if resume.get("summary") else "")
                + (
                    f"；初探表已于 {resume['submitted_at']} 提交"
                    if resume.get("submitted_at")
                    else ""
                )
                + "。"
            )
            if resume.get("source_excerpt"):
                lines.append(f"简历摘录：{resume['source_excerpt']}")
        else:
            lines.append("档案中尚无简历正文，可引导用户通过初探信息表提交。")
    if memory.get("exploration"):
        lines.append("已加载 exploration 档案字段（不含 intake 全文）。")
    if memory.get("market"):
        lines.append("已加载 market 档案字段。")
    if memory.get("strategy"):
        lines.append("已加载 strategy 档案字段。")
    return "\n".join(lines) if lines else "（档案切片为空）"


def build_profile_aware_chat_draft(
    user_message: str,
    session_state: dict[str, Any],
) -> str:
    """Build synthesis draft before synthesize LLM; embeds profile facts for this turn."""
    from career_os.agents.lc.coordinator_llm import chat_only_synthesis_draft

    sections = resolve_profile_memory_sections(user_message, session_state)
    memory = materialize_profile_memory(
        sections, full_resume_text=False, session_state=session_state
    )
    base = chat_only_synthesis_draft(session_state)
    facts = format_profile_memory_for_draft(memory)
    return (
        f"{base}\n\n"
        f"【本回合档案事实 — 回答须与此一致】\n{facts}\n"
        "若 resume_on_file 为真，不得声称没有用户简历；用户问档案/简历时直接据档案回答。"
    )
