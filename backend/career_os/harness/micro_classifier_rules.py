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
