from __future__ import annotations

from typing import Any


def run_depth_judge(
    track: str,
    profile: dict[str, Any],
    messages: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Harness 探索深度判断占位实现，生产环境可替换为 LLM 调用。"""
    _ = messages
    exploration = profile.get("exploration") or {}
    rounds = (exploration.get("depth_rounds") or {}).get(track, 0)
    sufficient = rounds >= 6
    return {
        "track": track,
        "sufficient": sufficient,
        "reasons": [f"rounds={rounds}"],
    }
