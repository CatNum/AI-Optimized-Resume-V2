from __future__ import annotations

from typing import Any


def run_depth_judge(
    track: str,
    profile: dict[str, Any],
    messages: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Harness depth judge stub; replace with LLM call in production."""
    _ = messages
    exploration = profile.get("exploration") or {}
    rounds = (exploration.get("depth_rounds") or {}).get(track, 0)
    sufficient = rounds >= 6
    return {
        "track": track,
        "sufficient": sufficient,
        "reasons": [f"rounds={rounds}"],
    }
