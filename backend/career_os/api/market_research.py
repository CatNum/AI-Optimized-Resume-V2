from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from career_os.platform.market_research.errors import MarketResearchError
from career_os.platform.market_research.models import DirectionProposal, ResearchPlan
from career_os.platform.market_research.plans import MarketResearchPlanStore


router = APIRouter(prefix="/v1/market-research", tags=["market-research"])


class ReviseMarketResearchPlanRequest(BaseModel):
    """ReviseMarketResearchPlanRequest（修改方案请求）承载 Session 和新的方向提案。"""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(pattern=r"^sess_[0-9a-f]{32}$")  # 发起修改且必须拥有方案的 Session
    directions: Annotated[list[DirectionProposal], Field(min_length=1, max_length=3)]  # 用户修改后的完整方向列表


class ConfirmMarketResearchPlanRequest(BaseModel):
    """ConfirmMarketResearchPlanRequest（确认方案请求）承载明确确认方案的 Session。"""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(pattern=r"^sess_[0-9a-f]{32}$")  # 发起确认且必须拥有方案的 Session


def _plan_store_error(error: MarketResearchError) -> HTTPException:
    """把方案存储器的结构化错误转换为稳定 HTTP 错误响应。"""
    status = 403 if error.error_code.value == "plan_forbidden" else 409
    if error.error_code.value == "plan_not_found":
        status = 404
    return HTTPException(status_code=status, detail=error.to_payload().model_dump())


@router.patch("/plans/{plan_id}", response_model=ResearchPlan)
def revise_market_research_plan(
    plan_id: str,
    body: ReviseMarketResearchPlanRequest,
) -> ResearchPlan:
    """修改方案并使已有确认和哈希失效。"""
    try:
        return MarketResearchPlanStore().revise(plan_id, body.session_id, body.directions)
    except MarketResearchError as error:
        raise _plan_store_error(error) from None
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None


@router.post("/plans/{plan_id}/confirm", response_model=ResearchPlan)
def confirm_market_research_plan(
    plan_id: str,
    body: ConfirmMarketResearchPlanRequest,
) -> ResearchPlan:
    """确认方案并返回包含稳定哈希的完整条件预览。"""
    try:
        return MarketResearchPlanStore().confirm(plan_id, body.session_id)
    except MarketResearchError as error:
        raise _plan_store_error(error) from None


@router.get("/plans/{plan_id}", response_model=ResearchPlan)
def get_market_research_plan(
    plan_id: str,
    session_id: Annotated[str, Query(pattern=r"^sess_[0-9a-f]{32}$")],
) -> ResearchPlan:
    """读取当前 Session 拥有的完整方案预览。"""
    try:
        return MarketResearchPlanStore().get(plan_id, session_id)
    except MarketResearchError as error:
        raise _plan_store_error(error) from None
