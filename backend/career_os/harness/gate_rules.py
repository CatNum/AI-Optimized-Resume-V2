"""基于硬规则的闸门意图匹配，不执行 IO。"""

from __future__ import annotations

import re
from typing import Any

from career_os.harness.gate_patterns import (
    EXPLORE_COMPLETE_AFFIRMATIVE,
    GATE_PATTERNS,
    matches_explore_complete_affirmative,
)

_RULE_CONFIDENCE = 0.95


def _rule_hit(
    gate_name: str,
    intent: str,
    *,
    pattern: str | None = None,
) -> dict[str, Any]:
    """_rule_hit（内部函数 rule hit）的函数说明。

    gate_name（参数）、intent（参数）、pattern（参数）用于向该函数传入运行所需的数据。

    该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
    out: dict[str, Any] = {
        "matched": True,
        "gate_name": gate_name,
        "intent": intent,
        "confidence": _RULE_CONFIDENCE,
        "source": "rule",
    }
    if pattern:
        out["pattern"] = pattern
    return out


def _unknown(pending_name: str | None) -> dict[str, Any]:
    """_unknown（内部函数 unknown）的函数说明。

    pending_name（参数）用于向该函数传入运行所需的数据。

    该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
    if pending_name:
        return {
            "matched": False,
            "gate_name": pending_name,
            "intent": "unknown",
            "confidence": 0.0,
            "source": "none",
        }
    return {
        "matched": False,
        "gate_name": None,
        "intent": "unknown",
        "confidence": 0.0,
        "source": "none",
    }


def _explore_repeat_confirm_blocked(message: str) -> bool:
    """_explore_repeat_confirm_blocked（内部函数 explore repeat confirm blocked）的函数说明。

    message（参数）用于向该函数传入运行所需的数据。

    该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
    if matches_explore_complete_affirmative(message):
        return True
    blocked = (
        r"^确认$",
        r"^要$",
        r"^好$",
        r"^继续$",
    )
    return any(re.search(p, message, re.IGNORECASE) for p in blocked)


def match_gate_intent_rules(
    user_message: str,
    pending_gate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """match_gate_intent_rules（match gate intent rules）的函数说明。

    user_message（参数）、pending_gate（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    message = user_message.strip()
    pending_name = (pending_gate or {}).get("name")

    if pending_name == "explore_complete" and matches_explore_complete_affirmative(message):
        return _rule_hit("explore_complete", "confirm")

    for gate_name, _default_intent, confirm_patterns, reject_patterns in GATE_PATTERNS:
        if pending_name and gate_name != pending_name:
            continue
        for pattern in reject_patterns:
            if re.search(pattern, message, re.IGNORECASE):
                return _rule_hit(gate_name, "reject", pattern=pattern)
        for pattern in confirm_patterns:
            if gate_name == "explore_repeat" and _explore_repeat_confirm_blocked(message):
                continue
            if re.search(pattern, message, re.IGNORECASE):
                return _rule_hit(gate_name, "confirm", pattern=pattern)

    return _unknown(pending_name)


def is_rule_clear_hit(result: dict[str, Any]) -> bool:
    """is_rule_clear_hit（is rule clear hit）的函数说明。

    result（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    return bool(result.get("matched") and result.get("source") == "rule")
