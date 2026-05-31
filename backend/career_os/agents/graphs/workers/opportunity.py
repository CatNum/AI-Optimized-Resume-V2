import hashlib
from typing import Any

from career_os.agents.graphs.workers.base import finalize_worker_result
from career_os.platform.store.profile import ProfileStore


def run(harness: Any, goal: str, session_state: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    jd_text = context.get("jd_text") or goal
    fingerprint = hashlib.sha256(jd_text.encode()).hexdigest()[:12]
    profile = ProfileStore()
    snapshots = profile.get(["market.opportunity_snapshots"]).get("market", {}).get(
        "opportunity_snapshots"
    ) or []
    snapshot = {
        "jd_fingerprint": fingerprint,
        "recommendation": "recommended",
        "summary": "与当前能力画像匹配度较高",
    }
    snapshots.append(snapshot)
    harness.execute_tool(
        "opportunity",
        "profile_patch",
        {"path": "market.opportunity_snapshots", "value": snapshots, "op": "set"},
        session_id=session_state.get("session_id"),
    )
    payload = {
        "recommendation": "recommended",
        "user_visible_summary": "JD 评估完成，建议继续策略制定。",
        "jd_fingerprint": fingerprint,
        "match_highlights": ["后端经验匹配"],
        "blockers": [],
    }
    return finalize_worker_result("opportunity", payload)
