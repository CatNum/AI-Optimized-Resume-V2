from __future__ import annotations

from enum import StrEnum

from career_os.platform.market_research.models import MarketResearchErrorPayload


class MarketResearchErrorCode(StrEnum):
    """MarketResearchErrorCode（市场错误码）列出调用方可以稳定分支处理的固定失败类型。"""

    BROWSER_FAILED = "browser_failed"  # Chrome 未找到、无法启动或异常退出
    PAGE_CHANGED = "page_changed"  # 版本化页面契约的关键字段失效
    TREND_NO_DATA = "trend_no_data"  # 页面正常但当前搜索词没有搜索关注度数据
    TREND_COMPARISON_UNAVAILABLE = "trend_comparison_unavailable"  # 页面正常但没有窗口比较字段
    PROCESS_INTERRUPTED = "process_interrupted"  # FastAPI 进程退出导致本地线程任务中断
    STORAGE_FAILED = "storage_failed"  # 状态或正式结果无法可靠写入磁盘
    BUDGET_EXHAUSTED = "budget_exhausted"  # 当前方向十分钟有效预算已经耗尽
    EXECUTION_FAILED = "execution_failed"  # 方向执行器发生不含页面原文的技术失败
    PLAN_NOT_CONFIRMED = "plan_not_confirmed"  # 调研方案尚未获得用户明确确认
    PLAN_HASH_MISMATCH = "plan_hash_mismatch"  # 当前方案内容与确认时哈希不一致
    PLAN_CONSUMED = "plan_consumed"  # 冻结方案已经被其他调研启动消费
    PLAN_NOT_FOUND = "plan_not_found"  # 指定方案不存在或已被清理
    PLAN_FORBIDDEN = "plan_forbidden"  # 当前 Session 不是方案所属 Session
    RESEARCH_CONFLICT = "research_conflict"  # 当前 demo 已存在其他活动调研或重试


ERROR_DEFINITIONS: dict[MarketResearchErrorCode, tuple[str, str]] = {
    MarketResearchErrorCode.BROWSER_FAILED: (
        "browser",
        "请检查 Google Chrome 是否已安装以及配置路径是否正确。",
    ),
    MarketResearchErrorCode.PAGE_CHANGED: (
        "page_contract",
        "页面结构可能已经变化，请更新页面字段契约后重新调研。",
    ),
    MarketResearchErrorCode.TREND_NO_DATA: (
        "source_data",
        "当前搜索词没有可用数据，可继续查看岗位结果或调整搜索词后重试。",
    ),
    MarketResearchErrorCode.TREND_COMPARISON_UNAVAILABLE: (
        "source_data",
        "页面没有提供窗口比较字段，可继续查看岗位结果或稍后重试。",
    ),
    MarketResearchErrorCode.PROCESS_INTERRUPTED: (
        "runtime",
        "后端进程已中断本次调研，请创建并确认新方案后重新开始。",
    ),
    MarketResearchErrorCode.STORAGE_FAILED: (
        "storage",
        "本地结果保存失败，请检查数据目录权限和磁盘空间后重试。",
    ),
    MarketResearchErrorCode.BUDGET_EXHAUSTED: (
        "budget",
        "当前方向已达到十分钟有效预算，可查看已有样本或单独重试该方向。",
    ),
    MarketResearchErrorCode.EXECUTION_FAILED: (
        "runtime",
        "当前方向执行失败，可查看状态后重试该方向。",
    ),
    MarketResearchErrorCode.PLAN_NOT_CONFIRMED: (
        "plan",
        "请先预览并明确确认当前调研方案。",
    ),
    MarketResearchErrorCode.PLAN_HASH_MISMATCH: (
        "plan",
        "方案确认后发生变化，请重新预览并确认。",
    ),
    MarketResearchErrorCode.PLAN_CONSUMED: (
        "plan",
        "该方案已经启动过调研，请生成并确认新方案。",
    ),
    MarketResearchErrorCode.PLAN_NOT_FOUND: (
        "plan",
        "没有找到该调研方案，请重新生成方案。",
    ),
    MarketResearchErrorCode.PLAN_FORBIDDEN: (
        "authorization",
        "当前会话不能读取或修改其他会话的调研方案。",
    ),
    MarketResearchErrorCode.RESEARCH_CONFLICT: (
        "runtime",
        "当前环境已有活动调研，请等待其结束或由所属 Session 取消。",
    ),
}


class MarketResearchError(Exception):
    """MarketResearchError（市场调研异常）携带机器码、类别、用户动作和失败阶段。"""

    def __init__(
        self,
        error_code: MarketResearchErrorCode,
        *,
        stage: str | None = None,
        message: str | None = None,
    ) -> None:
        """根据固定错误码创建可供 API、Trace 和运行状态复用的异常。"""
        error_category, user_action = ERROR_DEFINITIONS[error_code]
        self.error_category = error_category  # 错误所属的大类
        self.error_code = error_code  # 供程序分支判断的具体机器码
        self.user_action = user_action  # 用户可执行的下一步操作
        self.stage = stage  # 发生错误时的调研阶段
        self.message = message or error_code.value  # 不含网页原文或隐私数据的诊断消息
        super().__init__(self.message)

    def to_payload(self) -> MarketResearchErrorPayload:
        """把异常转换为可安全持久化和返回给 API 的结构化错误载荷。"""
        return MarketResearchErrorPayload(
            error_category=self.error_category,
            error_code=self.error_code.value,
            user_action=self.user_action,
            stage=self.stage,
        )


def build_market_research_error(
    error_code: MarketResearchErrorCode,
    *,
    stage: str | None = None,
    message: str | None = None,
) -> MarketResearchError:
    """build_market_research_error（构造市场错误）按固定定义生成统一异常。"""
    return MarketResearchError(error_code, stage=stage, message=message)
