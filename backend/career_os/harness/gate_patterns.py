"""Shared gate pattern tables."""

import re

EXPLORE_COMPLETE_AFFIRMATIVE = [
    r"确认完成初探",
    r"确认.*初探.*完成",
    r"初探完成",
    r"完成初探",
    r"^确认完成$",
    r"确认.*完成",
    r"足够.*梳理",
    r"已经到位",
    r"初探.*到位",
    r"^到位了?$",
    r"梳理.*到位",
    r"聊得差不多",
    r"可以进入下一",
    r"没问题了",
    r"够了",
]

GATE_PATTERNS: list[tuple[str, str, list[str], list[str]]] = [
    (
        "explore_complete",
        "confirm",
        [
            r"确认完成初探",
            r"初探完成",
            r"完成初探",
            r"^确认完成$",
            r"确认.*完成",
        ],
        [r"还要改", r"再改改", r"还没好", r"再聊聊", r"继续聊"],
    ),
    (
        "explore_review_complete",
        "confirm",
        [r"确认复盘完成", r"复盘完成"],
        [r"再想想", r"还要改"],
    ),
    (
        "optimize_confirm",
        "confirm",
        [r"确认按该\s*JD\s*优化简历", r"确认优化", r"开始优化简历"],
        [r"先不优化", r"暂不优化", r"不要优化"],
    ),
    (
        "strategy_complete",
        "confirm",
        [r"确认策略完成", r"策略阶段完成", r"策略可以了", r"策略没问题"],
        [r"还要改策略", r"策略再想想"],
    ),
    (
        "deep_explore",
        "confirm",
        [r"确认进入深度探讨", r"进入深度探讨"],
        [r"暂不", r"先聊聊", r"不用"],
    ),
    (
        "jd_continue_despite_not_recommended",
        "confirm",
        [r"确认继续", r"仍要继续", r"继续评估"],
        [r"算了", r"换\s*JD", r"不做了"],
    ),
    (
        "jd_bank_deep_dive",
        "confirm",
        [r"继续深挖经历", r"深挖经历"],
        [r"信息已够", r"直接优化"],
    ),
    (
        "task_start",
        "confirm",
        [r"开始执行", r"现在开始", r"开始吧"],
        [],
    ),
    (
        "task_abandon",
        "confirm",
        [r"放弃", r"换\s*JD\s*不做了", r"不做了"],
        [],
    ),
    (
        "explore_repeat",
        "confirm",
        [
            r"再次初探",
            r"再来一轮",
            r"再来一次",
            r"愿意再次",
            r"需要再次",
            r"^是的$",
            r"是的.*需要",
        ],
        [
            r"不用",
            r"不需要",
            r"无需",
            r"不用了",
            r"^否$",
            r"先不",
            r"算了",
            r"不要",
            r"下一步",
            r"进入下一步",
            r"推进下一步",
            r"先看看市场",
        ],
    ),
]


def matches_explore_complete_affirmative(message: str) -> bool:
    """matches_explore_complete_affirmative（matches explore complete affirmative）的函数说明。

    message（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    return any(
        re.search(pattern, message, re.IGNORECASE)
        for pattern in EXPLORE_COMPLETE_AFFIRMATIVE
    )
