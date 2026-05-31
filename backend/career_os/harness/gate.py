import re
from typing import Any

GATE_PATTERNS: list[tuple[str, str, list[str], list[str]]] = [
    (
        "explore_complete",
        "confirm",
        [r"确认完成初探", r"初探完成", r"完成初探"],
        [r"还要改", r"再改改", r"还没好"],
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
]


def match_gate_intent(
    user_message: str,
    pending_gate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    message = user_message.strip()
    pending_name = (pending_gate or {}).get("name")

    for gate_name, _default_intent, confirm_patterns, reject_patterns in GATE_PATTERNS:
        if pending_name and gate_name != pending_name:
            continue
        for pattern in reject_patterns:
            if re.search(pattern, message, re.IGNORECASE):
                return {
                    "matched": True,
                    "gate_name": gate_name,
                    "intent": "reject",
                    "confidence": 0.95,
                }
        for pattern in confirm_patterns:
            if re.search(pattern, message, re.IGNORECASE):
                return {
                    "matched": True,
                    "gate_name": gate_name,
                    "intent": "confirm",
                    "confidence": 0.95,
                }

    if pending_name:
        return {
            "matched": False,
            "gate_name": pending_name,
            "intent": "unknown",
            "confidence": 0.0,
        }
    return {
        "matched": False,
        "gate_name": None,
        "intent": "unknown",
        "confidence": 0.0,
    }
