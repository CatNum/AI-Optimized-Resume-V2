from __future__ import annotations

from typing import Any

from career_os.harness.errors import HarnessError
from career_os.harness.pipeline_gates import is_explore_gate_confirmed
from career_os.platform.store.profile import ProfileStore

JD_CHAIN_WORKERS = frozenset({"market", "opportunity", "strategy"})

JD_INTENT_KEYWORDS = ("jd", "job", "岗位", "职位", "匹配度", "投递", "招聘")


def is_jd_intent(user_message: str) -> bool:
    text = user_message.lower()
    return any(k in text or k in user_message for k in JD_INTENT_KEYWORDS)


def _onboarding_complete(profile: dict[str, Any]) -> bool:
    basic = profile.get("basic") or {}
    return bool(basic)


def _explore_completed(profile: dict[str, Any], session_state: dict[str, Any]) -> bool:
    _ = profile
    if session_state.get("explore_completed_at"):
        return True
    if is_explore_gate_confirmed(session_state):
        return True
    explore = session_state.get("explore_closure") or {}
    return bool(explore.get("completed"))


def check_jd_prerequisites(session_state: dict[str, Any]) -> tuple[bool, str | None]:
    """Return (ready, block_reason). block_reason is onboarding | explore."""
    profile = ProfileStore().get(["basic", "capability"])
    if not _onboarding_complete(profile):
        return False, "onboarding"
    if not _explore_completed(profile, session_state):
        return False, "explore"
    return True, None


def jd_delegate_block_error(
    worker_id: str, session_state: dict[str, Any]
) -> HarnessError | None:
    if worker_id not in JD_CHAIN_WORKERS:
        return None
    ready, reason = check_jd_prerequisites(session_state)
    if ready:
        return None
    block = reason or "explore"
    return HarnessError(
        "delegate_blocked",
        f"JD-B1: {block} required before {worker_id}",
    )


def parse_jd_b1_block_reason(message: str) -> str | None:
    if not message.startswith("JD-B1:"):
        return None
    tail = message.split(":", 1)[1].strip()
    reason = tail.split()[0] if tail else ""
    if reason in {"onboarding", "explore"}:
        return reason
    return "explore"


def jd_prerequisites_payload(session_state: dict[str, Any]) -> dict[str, Any]:
    profile = ProfileStore().get(["basic"])
    ready, reason = check_jd_prerequisites(session_state)
    return {
        "jd_prerequisites_met": ready,
        "jd_block_reason": reason,
        "profile_has_basic": _onboarding_complete(profile),
        "explore_completed": _explore_completed(profile, session_state),
    }
