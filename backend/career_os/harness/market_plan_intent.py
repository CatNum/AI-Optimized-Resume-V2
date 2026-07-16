from __future__ import annotations

import re
import unicodedata

from career_os.platform.market_research.errors import MarketResearchError
from career_os.platform.market_research.models import DirectionProposal, ResearchPlan
from career_os.platform.market_research.plans import MarketResearchPlanStore


_SINGLE_DIRECTION_PATTERN = re.compile(r"(?:只|仅)(?:想|要|需要)?(?:调研|研究|保留)")


def _normalize_message(value: str) -> str:
    """规范化用户消息，供方向名称做稳定的大小写无关匹配。"""
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def revise_plan_from_selection_message(
    plan_store: MarketResearchPlanStore,
    plan_id: str,
    session_id: str,
    user_message: str,
) -> ResearchPlan | None:
    """把“只调研某方向”的明确选择原子修订到当前未消费方案。"""
    if _SINGLE_DIRECTION_PATTERN.search(user_message) is None:
        return None
    try:
        plan = plan_store.get(plan_id, session_id)
    except MarketResearchError:
        return None
    if plan.status == "consumed":
        return None
    normalized_message = _normalize_message(user_message)
    selected = [
        direction
        for direction in plan.directions
        if _normalize_message(direction.direction_name) in normalized_message
    ]
    if len(selected) != 1:
        return None
    proposal_payload = selected[0].model_dump(mode="python")
    proposal_payload.pop("direction_key", None)
    proposal = DirectionProposal.model_validate(proposal_payload)
    return plan_store.revise(plan.plan_id, session_id, [proposal])
