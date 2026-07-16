from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from career_os.platform.market_research.errors import MarketResearchError
from career_os.platform.market_research.models import DirectionProposal, ResearchPlan
from career_os.platform.market_research.models import ResearchSnapshot
from career_os.platform.market_research.service import get_market_research_service
from career_os.harness.errors import HarnessError
from career_os.harness.market_research_result import confirm_market_result
from career_os.platform.store.session import SessionStore


router = APIRouter(prefix="/v1/market-research", tags=["market-research"])


def _active_plan_supersedes_snapshot(
    plan: ResearchPlan,
    snapshot: ResearchSnapshot,
) -> bool:
    """判断待确认的新方案是否应覆盖不同旧方案留下的终态快照。"""
    return (
        plan.status in {"draft", "confirmed"}
        and plan.plan_id != snapshot.plan_id
        and snapshot.status.value
        in {"completed", "partial_completed", "failed", "cancelled"}
    )


class ReviseMarketResearchPlanRequest(BaseModel):
    """ReviseMarketResearchPlanRequest（修改方案请求）承载 Session 和新的方向提案。"""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(pattern=r"^sess_[0-9a-f]{32}$")  # 发起修改且必须拥有方案的 Session
    directions: Annotated[list[DirectionProposal], Field(min_length=1, max_length=3)]  # 用户修改后的完整方向列表


class ConfirmMarketResearchPlanRequest(BaseModel):
    """ConfirmMarketResearchPlanRequest（确认方案请求）承载明确确认方案的 Session。"""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(pattern=r"^sess_[0-9a-f]{32}$")  # 发起确认且必须拥有方案的 Session


class MarketResearchControlRequest(BaseModel):
    """MarketResearchControlRequest（调研控制请求）标识发起操作的 Session。"""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(pattern=r"^sess_[0-9a-f]{32}$")  # 发起继续、取消或结果确认的 Session


class ReuseMarketResearchRequest(BaseModel):
    """ReuseMarketResearchRequest（复用请求）只允许用户选择一个正式方向引用。"""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(pattern=r"^sess_[0-9a-f]{32}$")  # 接收复用引用的 Session
    research_id: str = Field(pattern=r"^research_[0-9a-f]+$")  # 原始正式调研编号
    result_version: int = Field(ge=1)  # 用户查看并选择的不可变版本
    direction_key: str = Field(min_length=1)  # 用户明确选择的唯一方向规范键


def _plan_store_error(error: MarketResearchError) -> HTTPException:
    """把方案存储器的结构化错误转换为稳定 HTTP 错误响应。"""
    status = 403 if error.error_code.value == "plan_forbidden" else 409
    if error.error_code.value == "plan_not_found":
        status = 404
    return HTTPException(status_code=status, detail=error.to_payload().model_dump())


def _research_error(error: MarketResearchError) -> HTTPException:
    """把调研生命周期错误转换为不会泄露其他 Session 内容的 HTTP 响应。"""
    code = error.error_code.value
    status = 403 if code == "plan_forbidden" else 409
    return HTTPException(status_code=status, detail=error.to_payload().model_dump())


@router.patch("/plans/{plan_id}", response_model=ResearchPlan)
def revise_market_research_plan(
    plan_id: str,
    body: ReviseMarketResearchPlanRequest,
) -> ResearchPlan:
    """修改方案并使已有确认和哈希失效。"""
    try:
        return get_market_research_service().plan_store.revise(
            plan_id, body.session_id, body.directions
        )
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
        return get_market_research_service().plan_store.confirm(plan_id, body.session_id)
    except MarketResearchError as error:
        raise _plan_store_error(error) from None


@router.get("/plans/{plan_id}", response_model=ResearchPlan)
def get_market_research_plan(
    plan_id: str,
    session_id: Annotated[str, Query(pattern=r"^sess_[0-9a-f]{32}$")],
) -> ResearchPlan:
    """读取当前 Session 拥有的完整方案预览。"""
    try:
        return get_market_research_service().plan_store.get(plan_id, session_id)
    except MarketResearchError as error:
        raise _plan_store_error(error) from None


@router.get("/status")
def get_market_research_status(
    session_id: Annotated[str, Query(pattern=r"^sess_[0-9a-f]{32}$")],
) -> dict[str, object]:
    """读取当前 Session 的方案和最近调研；其他 Session 只能看到活动摘要。"""
    service = get_market_research_service()
    session_store = SessionStore()
    if not session_store.session_exists(session_id):
        raise HTTPException(status_code=404, detail="session_not_found")
    artifacts = session_store.get_artifacts(session_id)
    market = artifacts.get("market") if isinstance(artifacts, dict) else {}
    active_summary = service.active_summary()
    research_id = market.get("active_research_id") or market.get("last_research_id")
    response: dict[str, object] = {
        "has_active_research": active_summary is not None,
        "owned": False,
        "result_confirmed": bool(market.get("market_result_confirmed")),
    }
    snapshot: ResearchSnapshot | None = None
    if isinstance(research_id, str) and research_id:
        try:
            snapshot = service.get_status(research_id, session_id)
        except KeyError:
            snapshot = None
        except MarketResearchError as error:
            raise _research_error(error) from None
        if snapshot is not None:
            response["owned"] = True
            response["snapshot"] = snapshot.model_dump(mode="json")
            if snapshot.status.value in {"partial_completed", "failed"}:
                latest_ref = service.store.read_latest_ref(snapshot.research_id)
                if latest_ref is not None:
                    latest = service.store.read_result(
                        snapshot.research_id,
                        latest_ref.result_version,
                    )
                    response["retryable_directions"] = [
                        {
                            "direction_name": failure.direction_name,
                            "direction_key": failure.direction_key,
                        }
                        for failure in latest.failed_directions
                    ]
                elif plan_id := market.get("active_plan_id"):
                    try:
                        failed_plan = service.plan_store.get(str(plan_id), session_id)
                    except MarketResearchError:
                        failed_plan = None
                    if failed_plan is not None:
                        response["retryable_directions"] = [
                            {
                                "direction_name": direction.direction_name,
                                "direction_key": direction.direction_key,
                            }
                            for direction in failed_plan.directions
                        ]
    elif active_summary is not None:
        response["active_summary"] = active_summary
    plan_id = market.get("active_plan_id")
    if isinstance(plan_id, str) and plan_id:
        try:
            plan = service.plan_store.get(plan_id, session_id)
        except MarketResearchError:
            plan = None
        if plan is not None:
            response["plan"] = plan.model_dump(mode="json")
            if snapshot is not None and _active_plan_supersedes_snapshot(plan, snapshot):
                response.pop("snapshot", None)
                response.pop("retryable_directions", None)
                response["owned"] = False
    reuse_ref = market.get("reuse_ref")
    if isinstance(reuse_ref, dict):
        response["reuse_selection"] = reuse_ref
    retry_id = market.get("active_retry_id") or market.get("last_retry_id")
    if isinstance(retry_id, str) and retry_id:
        try:
            retry = service.get_retry_status(retry_id, session_id)
        except (KeyError, MarketResearchError):
            retry = None
        if retry is not None:
            response["active_retry"] = retry.model_dump(mode="json")
    return response


@router.get("/reuse-candidates")
def get_market_reuse_candidates(
    session_id: Annotated[str, Query(pattern=r"^sess_[0-9a-f]{32}$")],
    direction_key: Annotated[str, Query(min_length=1)],
) -> dict[str, object]:
    """返回同方向未过期候选，绝不自动写入 Session。"""
    try:
        candidates = get_market_research_service().find_reuse_candidates(
            session_id,
            direction_key,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="session_not_found") from None
    return {"candidates": candidates}


@router.post("/reuse")
def reuse_market_research_result(body: ReuseMarketResearchRequest) -> dict[str, object]:
    """绑定一个用户明确选择的单方向引用，不复制岗位或延长有效期。"""
    try:
        reuse_ref = get_market_research_service().reuse_result(
            body.session_id,
            body.research_id,
            body.result_version,
            body.direction_key,
        )
    except (FileNotFoundError, KeyError):
        raise HTTPException(status_code=404, detail="market_result_not_found") from None
    except ValueError as error:
        raise HTTPException(status_code=409, detail={"code": str(error)}) from None
    return {"reuse_ref": reuse_ref, "confirmation_required": True}


@router.post("/{research_id}/continue")
def continue_market_research(
    research_id: str,
    body: MarketResearchControlRequest,
) -> dict[str, object]:
    """继续处于 waiting_user（等待用户操作）状态的所属调研。"""
    try:
        snapshot = get_market_research_service().continue_research(
            research_id, body.session_id
        )
        return snapshot.model_dump(mode="json")
    except KeyError:
        raise HTTPException(status_code=404, detail="research_not_found") from None
    except MarketResearchError as error:
        raise _research_error(error) from None


@router.post("/{research_id}/cancel")
def cancel_market_research(
    research_id: str,
    body: MarketResearchControlRequest,
) -> dict[str, object]:
    """请求所属调研在安全检查点取消。"""
    try:
        snapshot = get_market_research_service().cancel(research_id, body.session_id)
        return snapshot.model_dump(mode="json")
    except KeyError:
        raise HTTPException(status_code=404, detail="research_not_found") from None
    except MarketResearchError as error:
        raise _research_error(error) from None


@router.post("/{research_id}/retry-direction/{direction_key}")
def retry_market_research_direction(
    research_id: str,
    direction_key: str,
    body: MarketResearchControlRequest,
) -> dict[str, object]:
    """为所属主任务的一个失败方向创建独立重试运行。"""
    try:
        retry = get_market_research_service().retry_direction(
            research_id,
            direction_key,
            body.session_id,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="direction_not_found") from None
    except ValueError as error:
        raise HTTPException(status_code=409, detail={"code": str(error)}) from None
    except MarketResearchError as error:
        raise _research_error(error) from None
    return retry.model_dump(mode="json")


@router.post("/{research_id}/confirm-result")
def confirm_market_research_result(
    research_id: str,
    body: MarketResearchControlRequest,
) -> dict[str, object]:
    """通过与自然语言闸门相同的 Harness 操作确认正式结果。"""
    service = get_market_research_service()
    session_store = SessionStore()
    artifacts = session_store.get_artifacts(body.session_id)
    market = artifacts.get("market") if isinstance(artifacts, dict) else {}
    current_ref = market.get("result_ref") or market.get("reuse_ref")
    if not isinstance(current_ref, dict) or current_ref.get("research_id") != research_id:
        raise HTTPException(
            status_code=409,
            detail={"code": "market_result_version_mismatch"},
        )
    if market.get("result_ref") is not None:
        try:
            snapshot = service.get_status(research_id, body.session_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="research_not_found") from None
        except MarketResearchError as error:
            raise _research_error(error) from None
        if snapshot.status.value not in {"completed", "partial_completed"}:
            raise HTTPException(status_code=409, detail={"code": "market_result_not_ready"})
    state = session_store.get_state(body.session_id)
    state["session_id"] = body.session_id
    result = confirm_market_result(body.session_id, state)
    if isinstance(result, HarnessError):
        raise HTTPException(
            status_code=409,
            detail={"code": result.code, "message": result.message},
        )
    return {"confirmed": True, "result": result.to_context()}


@router.delete("/results/{research_id}")
def delete_market_research_result(
    research_id: str,
    session_id: Annotated[str, Query(pattern=r"^sess_[0-9a-f]{32}$")],
    confirm: bool = False,
) -> dict[str, object]:
    """先展示引用 Session；只有 confirm=true 才清除引用并删除正式结果。"""
    service = get_market_research_service()
    try:
        references = service.result_references(research_id, session_id)
        if not confirm:
            return {"confirmation_required": True, "referencing_sessions": references}
        affected = service.delete_result(research_id, session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="market_result_not_found") from None
    except MarketResearchError as error:
        raise _research_error(error) from None
    return {"deleted": True, "affected_sessions": affected}
