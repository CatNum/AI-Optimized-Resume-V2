from __future__ import annotations

import re
from typing import Any

from career_os.platform.market_research.errors import MarketResearchError
from career_os.platform.market_research.service import get_market_research_service


def market_research(actor: str, args: dict[str, Any]) -> dict[str, Any]:
    """market_research（市场调研工具）按冻结方案异步启动任务，不接受任意搜索条件或 URL。"""
    if actor != "market":
        return {
            "accepted": False,
            "status": "failed",
            "message": "market_research is only available to the market worker",
            "error_code": "tool_not_allowed",
        }
    if set(args) - {"plan_id", "session_id"}:
        return {
            "accepted": False,
            "status": "failed",
            "message": "market_research only accepts plan_id",
            "error_code": "invalid_arguments",
        }
    plan_id = args.get("plan_id")  # 用户已预览并确认的冻结调研方案编号
    session_id = args.get("session_id")  # Harness 注入且用于校验方案和运行归属的 Session 编号
    if (
        not isinstance(plan_id, str)
        or re.fullmatch(r"^plan_[0-9a-f]+$", plan_id) is None
        or not isinstance(session_id, str)
    ):
        return {
            "accepted": False,
            "status": "failed",
            "message": "plan_id and Harness session_id are required",
            "error_code": "invalid_arguments",
        }
    try:
        snapshot = get_market_research_service().start(plan_id, session_id)
    except MarketResearchError as error:
        return {
            "accepted": False,
            "plan_id": plan_id,
            "status": "failed",
            "message": error.user_action,
            "error_code": error.error_code.value,
        }
    except RuntimeError:
        return {
            "accepted": False,
            "plan_id": plan_id,
            "status": "failed",
            "message": "市场调研服务尚未初始化，请稍后重试。",
            "error_code": "service_unavailable",
        }
    return {
        "accepted": True,
        "research_id": snapshot.research_id,
        "plan_id": snapshot.plan_id,
        "status": snapshot.status.value,
        "message": "市场调研已在后台启动，可通过状态卡查看进度。",
    }
