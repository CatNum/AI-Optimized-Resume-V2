"""Hard rules for micro_classifier tasks (no IO)."""

from __future__ import annotations

import re
from typing import Any

from career_os.harness.jd_prerequisites import is_jd_intent

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

_CHAT_ONLY_PHRASES = (
    "随便聊聊",
    "闲聊",
    "先聊聊",
    "先闲聊",
    "不分配任何工作",
    "不要分配任何工作",
    "不要进入任何任务",
    "不进入任何任务",
    "直接给出打招呼话术",
)


def match_history_scope_rules(user_message: str) -> dict[str, Any] | None:
    """match_history_scope_rules（match history scope rules）的函数说明。

    user_message（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
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


def match_chat_only_intent_rules(user_message: str) -> dict[str, Any] | None:
    """match_chat_only_intent_rules（match chat only intent rules）的函数说明。

    user_message（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    text = (user_message or "").strip()
    if not text:
        return None
    if any(phrase in text for phrase in _CHAT_ONLY_PHRASES):
        return {
            "chat_only": True,
            "confidence": _RULE_CONFIDENCE,
            "source": "rule",
            "reason": "matched_chat_only_phrase",
        }
    return None


_INTENT_MARKET_PHRASES = (
    "市场",
    "趋势",
    "岗位族",
    "行业分析",
    "市场分析",
)

_INTENT_JD_EVAL_PHRASES = (
    "评估 jd",
    "评估jd",
    "匹配度",
    "投这个岗",
    "分析岗位",
    "岗位评估",
    "jd 分析",
    "jd分析",
)

_INTENT_RESUME_STRATEGY_PHRASES = (
    "简历策略",
    "优化策略",
    "怎么改简历",
    "如何改简历",
    "简历优化策略",
    "按这份",
    "按照这个",
    "按这个 jd",
    "按这个jd",
    "优化方案",
)

_INTENT_RESUME_OPTIMIZE_PHRASES = (
    "开始优化简历",
    "改工作经历",
    "生成 html",
    "生成简历",
    "优化简历",
)

# 用户声明已有在做的 Agent 项目（未必含「策略/简历」字样）
_INTENT_DECLARE_AGENT_PROJECT_PHRASES = (
    "正在做",
    "我在做",
    "我做的是",
    "我做的是",
    "正在开发",
    "在开发",
    "用正在做",
    "直接用",
    "职业规划",
    "职业 agent",
    "career",
)


def _declares_agent_project(text: str, lower: str) -> bool:
    """_declares_agent_project（内部函数 declares agent project）的函数说明。

    text（参数）、lower（参数）用于向该函数传入运行所需的数据。

    该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
    has_agent = "agent" in lower or "智能体" in text or "agen" in lower
    if not has_agent and "职业规划" not in text:
        return False
    if any(p in text for p in _INTENT_DECLARE_AGENT_PROJECT_PHRASES):
        return True
    if "项目" in text and has_agent:
        return True
    return False


def match_pipeline_intent_rule_ids(user_message: str) -> list[str]:
    """Return matched intent rule ids in priority order (highest phase first)."""
    text = (user_message or "").strip()
    if not text:
        return []
    lower = text.lower()
    matched: list[str] = []
    if any(p in text for p in _INTENT_RESUME_OPTIMIZE_PHRASES) or (
        "优化" in text and "简历" in text and "策略" not in text
    ):
        matched.append("intent_resume_optimize")
    if any(p in text or p in lower for p in _INTENT_RESUME_STRATEGY_PHRASES):
        matched.append("intent_resume_strategy")
    if "策略" in text and ("简历" in text or "jd" in lower):
        if "intent_resume_strategy" not in matched:
            matched.append("intent_resume_strategy")
    if any(p in text or p in lower for p in _INTENT_JD_EVAL_PHRASES) or is_jd_intent(
        text
    ):
        matched.append("intent_jd_eval")
    if any(p in text for p in _INTENT_MARKET_PHRASES):
        matched.append("intent_market")
    if _declares_agent_project(text, lower):
        matched.append("intent_declare_agent_project")
    return matched
