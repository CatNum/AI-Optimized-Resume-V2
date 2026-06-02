"""Hard rules for micro_classifier tasks (no IO)."""

from __future__ import annotations

import re
from typing import Any

_RULE_CONFIDENCE = 0.95

_HISTORY_SCOPE_PHRASES = (
    "完整对话",
    "全部历史",
    "整个会话",
    "检查上下文",
    "查看历史",
    "上文说过",
    "之前提到的",
    "前面发的",
    "回顾聊天",
    "聊天记录",
    "完整上下文",
    "根据我们之前",
    "根据上面",
)

_PROFILE_RESUME_PHRASES = (
    "简历",
    "resume",
    "cv",
    "履历",
    "有没有我的",
    "有我的简历",
    "我的档案",
    "档案里",
    "档案中",
    "上传过",
    "发过简历",
)

_PROFILE_EXPLORATION_PHRASES = (
    "初探",
    "探索",
    "内心",
    "职业方向",
    "职业规划",
)

_PROFILE_MARKET_PHRASES = (
    "市场",
    "趋势",
    "岗位族",
    "jd",
    "job",
    "匹配度",
    "投递",
    "招聘",
    "岗位",
)

_PROFILE_STRATEGY_PHRASES = (
    "策略",
    "优化策略",
    "简历优化",
    "怎么改简历",
)

_PROFILE_BASIC_PHRASES = (
    "薪资",
    "工资",
    "目标岗",
    "工作年限",
    "建档",
    "基本信息",
)


def match_history_scope_rules(user_message: str) -> dict[str, Any] | None:
    text = (user_message or "").strip()
    if not text:
        return None
    for phrase in _HISTORY_SCOPE_PHRASES:
        if phrase in text:
            return {
                "needs_full_history": True,
                "confidence": _RULE_CONFIDENCE,
                "source": "rule",
                "reason": f"matched:{phrase}",
            }
    return None


def match_profile_memory_rules(user_message: str) -> set[str]:
    """Return profile section ids suggested by hard rules."""
    text = (user_message or "").strip()
    if not text:
        return set()
    lower = text.lower()
    sections: set[str] = set()
    if any(p in text or p in lower for p in _PROFILE_RESUME_PHRASES):
        sections.add("resume")
        sections.add("basic_intent")
    if any(p in text for p in _PROFILE_EXPLORATION_PHRASES):
        sections.add("exploration")
        if "简历" not in text:
            sections.update({"resume", "basic_intent"})
    if any(p in text or p in lower for p in _PROFILE_MARKET_PHRASES):
        sections.update({"market", "resume"})
    if any(p in text for p in _PROFILE_STRATEGY_PHRASES):
        sections.update({"strategy", "resume"})
    if any(p in text for p in _PROFILE_BASIC_PHRASES):
        sections.add("basic_intent")
    if re.search(r"有没有|是否已有|档案", text):
        sections.update({"resume", "basic_intent", "exploration"})
    return sections
