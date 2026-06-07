from __future__ import annotations

from typing import Any

PIPELINE_PHASES: tuple[str, ...] = (
    "explore",
    "market",
    "jd_analysis",
    "resume_strategy",
    "resume_optimize",
)

PHASE_TO_MILESTONE_ID: dict[str, str] = {
    "explore": "ms_explore",
    "market": "ms_market",
    "jd_analysis": "ms_jd",
    "resume_strategy": "ms_strategy",
    "resume_optimize": "ms_resume",
}

MILESTONE_ID_TO_PHASE: dict[str, str] = {v: k for k, v in PHASE_TO_MILESTONE_ID.items()}

JUMP_TARGET_PHASES: frozenset[str] = frozenset(
    {"explore", "market", "jd_analysis", "resume_strategy"}
)
