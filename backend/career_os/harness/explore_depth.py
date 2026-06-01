from __future__ import annotations

from typing import Any

from career_os.harness.explore_closure import (
    DEFAULT_REQUIRED_WORKERS,
    is_closure_ready,
)
from career_os.harness.explore_depth_judge import run_depth_judge
from career_os.harness.pipeline_gates import compute_hard_pass, never_explored

IDENTITY_WORKERS = frozenset({"identity"})
CAPABILITY_WORKERS = frozenset({"capability"})


def _exploration_depth(profile: dict[str, Any]) -> dict[str, Any]:
    exploration = profile.get("exploration") or {}
    depth = exploration.get("depth") or {}
    if not isinstance(depth, dict):
        depth = {}
    return depth


def record_explore_round(
    session_state: dict[str, Any],
    profile: dict[str, Any],
    workers_delegated: list[str],
) -> dict[str, Any]:
    exploration = dict(profile.get("exploration") or {})
    depth = dict(_exploration_depth(profile))
    rounds = dict(depth.get("rounds") or {"personal": 0, "capability": 0})
    for worker_id in workers_delegated:
        if worker_id in IDENTITY_WORKERS:
            rounds["personal"] = int(rounds.get("personal", 0)) + 1
        if worker_id in CAPABILITY_WORKERS:
            rounds["capability"] = int(rounds.get("capability", 0)) + 1
    depth["rounds"] = rounds
    exploration["depth"] = depth
    profile_patch = {"exploration": exploration}
    session_state["_explore_depth_rounds"] = rounds
    return profile_patch


def should_run_depth_judge(track: str, round_count: int) -> bool:
    if round_count == 6:
        return True
    if round_count == 8:
        return True
    if round_count > 8:
        return True
    return False


def depth_pass_for_track(profile: dict[str, Any], track: str) -> bool:
    depth = _exploration_depth(profile)
    flags = depth.get("sufficient") or {}
    return bool(flags.get(track))


def explore_closure_both_done(session_state: dict[str, Any]) -> bool:
    closure = session_state.get("explore_closure")
    if not closure:
        return False
    required = closure.get("required_workers") or DEFAULT_REQUIRED_WORKERS
    worker_done = closure.get("worker_done") or {}
    return all(worker_done.get(w) for w in required)


def can_offer_explore_complete(
    profile: dict[str, Any], session_state: dict[str, Any]
) -> tuple[bool, dict[str, Any]]:
    hard, hard_reasons = compute_hard_pass(profile)
    personal = depth_pass_for_track(profile, "personal")
    capability = depth_pass_for_track(profile, "capability")
    closure = explore_closure_both_done(session_state)
    ok = hard and personal and capability and closure
    return ok, {
        "hard_pass": hard,
        "hard_reasons": hard_reasons,
        "depth_pass_personal": personal,
        "depth_pass_capability": capability,
        "explore_closure_both_done": closure,
        "never_explored": never_explored(profile),
    }


def maybe_run_depth_judges(
    profile: dict[str, Any],
    messages: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    depth = _exploration_depth(profile)
    rounds = depth.get("rounds") or {"personal": 0, "capability": 0}
    sufficient = dict(depth.get("sufficient") or {})
    for track in ("personal", "capability"):
        count = int(rounds.get(track, 0))
        if should_run_depth_judge(track, count):
            result = run_depth_judge(track, profile, messages)
            sufficient[track] = bool(result.get("sufficient"))
    exploration = dict(profile.get("exploration") or {})
    exploration.setdefault("depth", {})
    exploration["depth"]["sufficient"] = sufficient
    return {"exploration": exploration["depth"]}


def delegate_blocked_missing_capability_round(
    session_state: dict[str, Any], profile: dict[str, Any]
) -> str | None:
    from career_os.harness.pipeline_routing import get_current_phase, is_pipeline_explore_phase

    if not is_pipeline_explore_phase(session_state):
        return None
    meta_phase = session_state.get("pipeline_phase") or get_current_phase(session_state) or "explore"
    if meta_phase != "explore":
        return None
    if is_closure_ready(session_state.get("explore_closure")):
        return None
    rounds = (_exploration_depth(profile).get("rounds") or {}).get("capability", 0)
    personal = (_exploration_depth(profile).get("rounds") or {}).get("personal", 0)
    if personal >= 6 and rounds < 6:
        return "capability"
    return None
