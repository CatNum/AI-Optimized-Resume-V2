from __future__ import annotations

from typing import Any

from career_os.harness.errors import HarnessError
from career_os.harness.pipeline_gates import is_explore_gate_confirmed
from career_os.harness.pipeline_gates import compute_needs_full_explore
from career_os.platform.store.profile import ProfileStore

JD_CHAIN_WORKERS = frozenset({"market", "opportunity", "strategy"})

JD_INTENT_KEYWORDS = ("jd", "job", "岗位", "职位", "匹配度", "投递", "招聘")


def is_jd_intent(user_message: str) -> bool:
    """判断用户消息是否包含 JD/岗位相关意图。

    user_message（用户消息）会同时匹配英文 jd/job 和中文岗位、投递等关键词。
    返回值为 True 表示后续可能进入 JD 分析或投递策略链路。
    """
    text = user_message.lower()
    return any(k in text or k in user_message for k in JD_INTENT_KEYWORDS)


def _onboarding_complete(profile: dict[str, Any]) -> bool:
    """判断用户基础画像是否已完成。"""
    basic = profile.get("basic") or {}
    return bool(basic)


def _explore_completed(profile: dict[str, Any], session_state: dict[str, Any]) -> bool:
    """判断职业初探是否已完成。

    profile（用户画像）提供持久化完成时间；session_state（会话状态）提供本轮完成标记、
    gate flags 和 explore_closure。任一来源确认完成即返回 True。
    """
    exploration = profile.get("exploration") or {}
    if exploration.get("completed_at"):
        return True
    if session_state.get("explore_completed_at"):
        return True
    if is_explore_gate_confirmed(session_state):
        return True
    explore = session_state.get("explore_closure") or {}
    return bool(explore.get("completed"))


def check_jd_prerequisites(session_state: dict[str, Any]) -> tuple[bool, str | None]:
    """检查进入 JD 链路前置条件。

    session_state（会话状态）用于判断探索完成与是否需要重探。返回值是
    (ready（是否就绪）, block_reason（阻断原因）)，原因可能是 onboarding 或 explore。
    """
    profile = ProfileStore().get(
        ["basic", "capability", "exploration", "intent", "resume"]
    )
    # 没有基础画像时，先阻断到 onboarding。
    if not _onboarding_complete(profile):
        return False, "onboarding"
    # 画像过期或信息变化导致需要完整初探时，阻断到 explore。
    if compute_needs_full_explore(profile, session_state):
        return False, "explore"
    # 没有任何探索完成证据时，也不能进入 JD 链路。
    if not _explore_completed(profile, session_state):
        return False, "explore"
    return True, None


def jd_delegate_block_error(
    worker_id: str, session_state: dict[str, Any]
) -> HarnessError | None:
    """在委托 JD 链路 Worker 前生成阻断错误。

    worker_id（工作者标识）用于判断是否属于 market/opportunity/strategy；
    session_state（会话状态）用于检查前置条件。返回 None 表示允许委托。
    """
    # 非 JD 链路 Worker 不受 JD-B1 前置条件约束。
    if worker_id not in JD_CHAIN_WORKERS:
        return None
    ready, reason = check_jd_prerequisites(session_state)
    if ready:
        return None
    # HarnessError 会被 Coordinator 解析成 jd_prerequisite_blocked 状态。
    block = reason or "explore"
    return HarnessError(
        "delegate_blocked",
        f"JD-B1: {block} required before {worker_id}",
    )


def parse_jd_b1_block_reason(message: str) -> str | None:
    """解析 JD-B1 阻断原因。

    message（错误消息）通常来自 HarnessError，例如 JD-B1: explore required。
    返回值是 onboarding 或 explore；如果不是 JD-B1 错误则返回 None。
    """
    if not message.startswith("JD-B1:"):
        return None
    tail = message.split(":", 1)[1].strip()
    reason = tail.split()[0] if tail else ""
    if reason in {"onboarding", "explore"}:
        return reason
    return "explore"


def jd_prerequisites_payload(session_state: dict[str, Any]) -> dict[str, Any]:
    """构造 JD 前置条件状态负载。

    session_state（会话状态）用于检查初探、画像和简历准备情况。
    返回值包含 jd_prerequisites_met（是否满足）、jd_block_reason（阻断原因）、
    profile_has_basic（是否有基础画像）和 explore_completed（是否完成初探）。
    """
    profile = ProfileStore().get(["basic", "capability", "exploration", "intent", "resume"])
    ready, reason = check_jd_prerequisites(session_state)
    return {
        "jd_prerequisites_met": ready,
        "jd_block_reason": reason,
        "profile_has_basic": _onboarding_complete(profile),
        "explore_completed": _explore_completed(profile, session_state),
    }
