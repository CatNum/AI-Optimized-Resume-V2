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

RESUME_DEFAULT_WORKS: tuple[dict[str, Any], ...] = (
    {
        "task_id": "work_view_strategy",
        "subject": "查看优化策略",
        "description": "阅读并确认本轮简历优化策略要点",
        "sort_order": 1,
    },
    {
        "task_id": "work_view_resume",
        "subject": "查看当前简历",
        "description": "对照策略检查当前简历结构与内容",
        "sort_order": 2,
    },
    {
        "task_id": "work_optimize_experience",
        "subject": "优化工作经历模块",
        "description": "按策略改写工作经历要点",
        "sort_order": 3,
    },
    {
        "task_id": "work_generate_html",
        "subject": "生成简历 HTML",
        "description": "产出可交付的简历 HTML",
        "sort_order": 4,
    },
)
