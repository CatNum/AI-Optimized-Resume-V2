from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Callable

from career_os.platform.market_research.errors import (
    MarketResearchError,
    MarketResearchErrorCode,
)
from career_os.platform.market_research.models import (
    DirectionPlan,
    DirectionResult,
    FailedDirection,
    JobRejectionAudit,
    MarketResearchErrorPayload,
    ResearchPlan,
    ResearchSnapshot,
    ResearchStage,
    ResearchStatus,
    SemanticValidationAudit,
    SynthesisValidationAudit,
    TrendResearchResult,
)
from career_os.platform.market_research.store import MarketResearchStore


_BUDGETED_STAGES = (
    ResearchStage.COLLECTING_TRENDS,
    ResearchStage.COLLECTING_BOSS,
    ResearchStage.EXTRACTING_SEMANTICS,
)
_POST_BUDGET_STAGES = (
    ResearchStage.CALCULATING_STATISTICS,
    ResearchStage.SYNTHESIZING,
)
_ALLOWED_STATUS_TRANSITIONS: dict[ResearchStatus, set[ResearchStatus]] = {
    ResearchStatus.QUEUED: {ResearchStatus.RUNNING, ResearchStatus.CANCELLING},
    ResearchStatus.RUNNING: {
        ResearchStatus.WAITING_USER,
        ResearchStatus.CANCELLING,
        ResearchStatus.COMPLETED,
        ResearchStatus.PARTIAL_COMPLETED,
        ResearchStatus.FAILED,
    },
    ResearchStatus.WAITING_USER: {
        ResearchStatus.RUNNING,
        ResearchStatus.CANCELLING,
    },
    ResearchStatus.CANCELLING: {ResearchStatus.CANCELLED},
    ResearchStatus.COMPLETED: set(),
    ResearchStatus.PARTIAL_COMPLETED: set(),
    ResearchStatus.FAILED: set(),
    ResearchStatus.CANCELLED: set(),
}


class ActiveBudget:
    """ActiveBudget（有效预算时钟）统计网页、自动等待和提取 LLM 的有效耗时。"""

    def __init__(
        self,
        budget_seconds: float,
        *,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        """创建固定秒数预算；monotonic（单调时钟）允许行为验证注入可控时间。"""
        if budget_seconds <= 0:
            raise ValueError("budget_seconds must be positive")
        self.budget_seconds = float(budget_seconds)  # 当前方向有效预算总秒数
        self._monotonic = monotonic  # 不受系统时间校准影响的单调时钟函数
        self._started_at = monotonic()  # 有效预算开始计时的单调时间点
        self._paused_at: float | None = None  # 等待用户期间暂停计时的起点
        self._paused_seconds = 0.0  # 已累计排除的人工等待秒数
        self._lock = threading.Lock()  # 保护后台线程与控制请求并发读取预算状态

    def remaining_seconds(self) -> float:
        """返回扣除有效耗时后的剩余秒数；人工等待期间数值保持不变。"""
        with self._lock:
            now = self._paused_at if self._paused_at is not None else self._monotonic()
            elapsed = max(0.0, now - self._started_at - self._paused_seconds)
            return max(0.0, self.budget_seconds - elapsed)

    def elapsed_seconds(self) -> float:
        """返回已经消耗的有效预算秒数，不包含 waiting_user（等待用户）时间。"""
        return self.budget_seconds - self.remaining_seconds()

    def pause_for_user(self) -> None:
        """开始排除人工登录或验证等待；重复暂停不会重复计时。"""
        with self._lock:
            if self._paused_at is None:
                self._paused_at = self._monotonic()

    def resume_from_user(self) -> None:
        """结束人工等待并恢复有效预算；未暂停时调用保持幂等。"""
        with self._lock:
            if self._paused_at is None:
                return
            self._paused_seconds += max(0.0, self._monotonic() - self._paused_at)
            self._paused_at = None


@dataclass
class DirectionRunContext:
    """DirectionRunContext（方向运行上下文）在同一线程的阶段处理器之间传递受控状态。"""

    research_id: str  # 当前主调研任务编号
    direction_run_id: str  # 当前方向本次执行的唯一编号
    plan: ResearchPlan  # 用户确认且已消费的冻结调研方案
    direction: DirectionPlan  # 当前严格顺序执行的职业方向条件
    budget: ActiveBudget  # 当前方向独立的十分钟有效预算时钟
    candidate_count: int = 0  # 页面已经看到的候选岗位数量
    valid_job_count: int = 0  # 已通过确定性准入的岗位数量
    rejected_job_count: int = 0  # 已判定不进入有效样本的岗位数量
    rejection_counts: dict[str, int] = field(default_factory=dict)  # 按机器码汇总的拒绝原因
    recent_rejections: list[JobRejectionAudit] = field(default_factory=list)  # 最近拒绝审计，最多五十条
    synthesis_validation_audits: list[SynthesisValidationAudit] = field(default_factory=list)  # 综合 Harness 最近两次校验失败审计
    semantic_rejected_job_count: int = 0  # 最终未通过语义校验的岗位数量
    semantic_failure_counts: dict[str, int] = field(default_factory=dict)  # 按机器码汇总的语义失败原因
    recent_semantic_failures: list[SemanticValidationAudit] = field(default_factory=list)  # 最近语义失败审计，最多五十条
    semantic_analyzed_count: int = 0  # 已通过结构和依据校验的岗位数量
    llm_attempt_count: int = 0  # 已发起的常规岗位提取 LLM 调用次数
    data: dict[str, Any] = field(default_factory=dict)  # 后续采集与综合模块使用的方向内存数据

    def require_browser_page(self) -> Any:
        """返回 page（专用 Chrome 唯一标签页）；未接入浏览器时明确拒绝执行采集。"""
        page = self.data.get("page")
        if page is None:
            raise MarketResearchError(
                MarketResearchErrorCode.BROWSER_FAILED,
                stage=ResearchStage.STARTING_BROWSER.value,
                message="dedicated browser page is not available",
            )
        return page

    def record_trend_result(self, result: TrendResearchResult) -> None:
        """记录唯一 v2 趋势结果，供综合、报告和最终持久化阶段顺序读取。"""
        self.data["trend_result"] = result

    def record_boss_results(self, result: Any) -> None:
        """记录 BOSS 确定性岗位和执行口径；raw_job_descriptions 只保留在线程内存供提取。"""
        self.valid_job_count = len(result.jobs)
        self.data["jobs"] = list(result.jobs)
        self.data["raw_job_descriptions"] = dict(result.raw_job_descriptions)
        self.data["visited_cities"] = tuple(result.visited_cities)
        self.data["keyword_statuses"] = dict(result.keyword_statuses)
        self.data["screenshot_paths"] = tuple(result.screenshot_paths)
        self.data["rejection_audits"] = tuple(result.rejection_audits)
        self.data["sample_limitations"] = tuple(result.sample_limitations)

    def record_rejection(self, audit: JobRejectionAudit) -> None:
        """累计岗位拒绝原因并保留最近五十条不含 JD 原文的审计记录。"""
        self.rejected_job_count += 1
        self.rejection_counts[audit.reason] = self.rejection_counts.get(audit.reason, 0) + 1
        self.recent_rejections = [*self.recent_rejections[-49:], audit]

    def record_synthesis_validation_audit(self, audit: SynthesisValidationAudit) -> None:
        """保存综合 Harness 最近两次脱敏失败审计，供终态状态卡说明失败位置。"""
        self.synthesis_validation_audits = [
            *self.synthesis_validation_audits[-1:],
            audit,
        ]

    def record_semantic_validation_failure(self, audit: SemanticValidationAudit) -> None:
        """累计最终语义失败并保留最近五十条不含 JD/evidence 的审计记录。"""
        self.semantic_rejected_job_count += 1
        self.semantic_failure_counts[audit.failure_type] = (
            self.semantic_failure_counts.get(audit.failure_type, 0) + 1
        )
        self.recent_semantic_failures = [*self.recent_semantic_failures[-49:], audit]

    def record_statistics(self, statistics: Any) -> None:
        """记录确定性统计并同步两类岗位计数和带正确分母的冻结技能词表。"""
        self.valid_job_count = statistics.valid_job_count
        self.semantic_analyzed_count = statistics.semantic_analyzed_count
        self.data["statistics"] = statistics
        self.data["skill_taxonomy"] = statistics.skill_taxonomy
        limitations = list(self.data.get("sample_limitations") or ())
        if statistics.sample_level == "limited":
            limitations.append("本次岗位样本少于 30 条，只进行有限分析。")
        elif statistics.sample_level == "limited_no_reference":
            limitations.append(
                f"本次仅有 {statistics.valid_job_count} 条岗位样本，结果不具参考价值。"
            )
        self.data["sample_limitations"] = tuple(dict.fromkeys(limitations))

    def record_direction_result(self, direction_result: DirectionResult) -> None:
        """记录经过 Harness 引用校验并合并冻结数字后的单方向正式结果候选。"""
        if direction_result.direction_run_id != self.direction_run_id:
            raise ValueError("direction result run id must match context")
        if direction_result.direction_key != self.direction.direction_key:
            raise ValueError("direction result key must match context")
        self.data["direction_result"] = direction_result


StageHandler = Callable[[DirectionRunContext], None]
"""StageHandler（阶段处理器）在 Runner 所在线程内执行一个方向阶段。"""

CompletionHandler = Callable[
    [str, ResearchPlan, list[DirectionRunContext], list[FailedDirection]],
    None,
]
"""CompletionHandler（完成处理器）在预算外合并并原子发布至少一个成功方向。"""

TerminalHandler = Callable[[str, ResearchSnapshot], None]
"""TerminalHandler（终态处理器）通知 Service 清理运行注册和 Session 活动引用。"""


class _CancellationRequested(Exception):
    """_CancellationRequested（取消请求）只用于 Runner 内部跳转到幂等取消清理。"""


class MarketResearchRunner:
    """MarketResearchRunner（市场调研运行器）在唯一后台线程中串行执行所有职业方向。"""

    def __init__(
        self,
        store: MarketResearchStore,
        *,
        stage_handlers: dict[ResearchStage, StageHandler] | None = None,
        fallback_extractor: StageHandler | None = None,
        completion_handler: CompletionHandler | None = None,
        open_handler: Callable[[str], Any] | None = None,
        close_handler: Callable[[], None] | None = None,
        terminal_handler: TerminalHandler | None = None,
    ) -> None:
        """注入阶段、兜底提取、发布、关闭和终态回调；所有回调均在同一后台线程执行。"""
        self.store = store  # 市场状态、临时数据和正式结果的唯一存储器
        self.stage_handlers = dict(stage_handlers or {})  # 各采集或计算阶段的实现映射
        self.fallback_extractor = fallback_extractor  # 预算耗尽且尚未提取时的批量兜底函数
        self.completion_handler = completion_handler  # 至少一个方向成功后的正式发布函数
        self.open_handler = open_handler  # 同线程创建 DrissionPage 等线程绑定资源的函数
        self.close_handler = close_handler  # 同线程关闭 DrissionPage 等线程绑定资源的函数
        self.terminal_handler = terminal_handler  # 通知 Service 释放活动任务槽的回调
        self.continue_event = threading.Event()  # 用户完成登录或验证后恢复当前方向的事件
        self.cancel_event = threading.Event()  # 用户请求安全取消整个调研的事件
        self._thread: threading.Thread | None = None  # 本 Runner 唯一允许创建的后台线程
        self._research_id: str | None = None  # 当前 Runner 绑定且用于权限检查的调研编号
        self._active_budget: ActiveBudget | None = None  # 当前方向预算，供等待控制暂停和恢复
        self._browser_page: Any | None = None  # 专用 Chrome 唯一标签页，供所有阶段顺序复用
        self._control_lock = threading.RLock()  # 保护线程启动、控制事件和当前预算引用

    def start(self, research_id: str, plan: ResearchPlan) -> None:
        """创建并启动唯一后台线程；重复启动同一个 Runner 会被拒绝。"""
        with self._control_lock:
            if self._thread is not None:
                raise RuntimeError("market research runner already started")
            self._research_id = research_id
            self._thread = threading.Thread(
                target=self.run,
                args=(research_id, plan),
                name=f"market-research-{research_id}",
                daemon=True,
            )
            self._thread.start()

    def run(self, research_id: str, plan: ResearchPlan) -> None:
        """按方案顺序执行方向；至少一个方向成功时进入统计、综合和发布。"""
        with self._control_lock:
            if self._research_id is None:
                self._research_id = research_id
            elif self._research_id != research_id:
                raise ValueError("runner is already bound to another research_id")
        successful: list[DirectionRunContext] = []
        failed: list[FailedDirection] = []
        terminal_snapshot: ResearchSnapshot | None = None
        try:
            self._check_cancelled(research_id)
            self._transition(research_id, ResearchStatus.RUNNING)
            if self.open_handler is not None:
                self._update_run_stage(research_id, ResearchStage.STARTING_BROWSER)
                self._browser_page = self.open_handler(research_id)
            for direction in plan.directions:
                self._check_cancelled(research_id)
                context = DirectionRunContext(
                    research_id=research_id,
                    direction_run_id=f"direction_{uuid.uuid4().hex}",
                    plan=plan,
                    direction=direction,
                    budget=ActiveBudget(plan.budget_seconds),
                )
                if self._browser_page is not None:
                    context.data["page"] = self._browser_page
                with self._control_lock:
                    self._active_budget = context.budget
                try:
                    self._run_direction(context)
                    successful.append(context)
                    self.store.append_event(
                        research_id,
                        {
                            "event": "direction.completed",
                            "direction_run_id": context.direction_run_id,
                            "direction_name": context.direction.direction_name,
                            "elapsed_seconds": context.budget.elapsed_seconds(),
                        },
                    )
                except _CancellationRequested:
                    raise
                except Exception as error:
                    market_error = self._normalize_error(error)
                    self.update_progress(context)
                    failed.append(
                        FailedDirection(
                            direction_name=context.direction.direction_name,
                            direction_key=context.direction.direction_key,
                            error=market_error.to_payload(),
                        )
                    )
                    self.store.cleanup_direction_temp(
                        research_id,
                        context.direction_run_id,
                    )
                    self.store.append_event(
                        research_id,
                        {
                            "event": "direction.failed",
                            "direction_run_id": context.direction_run_id,
                            "direction_name": context.direction.direction_name,
                            "elapsed_seconds": context.budget.elapsed_seconds(),
                            "error_code": market_error.error_code.value,
                        },
                    )
                finally:
                    with self._control_lock:
                        self._active_budget = None

            self._check_cancelled(research_id)
            if successful:
                self._update_stage(
                    research_id,
                    ResearchStage.PERSISTING,
                    successful[-1],
                )
                if self.completion_handler is None:
                    raise MarketResearchError(
                        MarketResearchErrorCode.EXECUTION_FAILED,
                        stage=ResearchStage.PERSISTING.value,
                        message="market completion handler is not configured",
                    )
                self.completion_handler(research_id, plan, successful, failed)
                final_status = (
                    ResearchStatus.PARTIAL_COMPLETED
                    if failed
                    else ResearchStatus.COMPLETED
                )
                terminal_snapshot = self._transition(
                    research_id,
                    final_status,
                    stage=ResearchStage.FINISHED,
                    error=None,
                )
            else:
                terminal_snapshot = self._transition(
                    research_id,
                    ResearchStatus.FAILED,
                    stage=ResearchStage.FINISHED,
                    error=failed[-1].error if failed else None,
                )
        except _CancellationRequested:
            terminal_snapshot = self._cancel_and_cleanup(research_id)
        except Exception as error:
            market_error = self._normalize_error(error)
            snapshot = self.store.read_status(research_id)
            if snapshot is not None and snapshot.status in {
                ResearchStatus.QUEUED,
                ResearchStatus.RUNNING,
                ResearchStatus.WAITING_USER,
            }:
                terminal_snapshot = self._transition(
                    research_id,
                    ResearchStatus.FAILED,
                    stage=ResearchStage.FINISHED,
                    error=market_error.to_payload(),
                )
        finally:
            if self.close_handler is not None:
                try:
                    self.close_handler()
                except Exception:
                    pass
            self._browser_page = None
            if terminal_snapshot is None:
                terminal_snapshot = self.store.read_status(research_id)
            if terminal_snapshot is not None and self.terminal_handler is not None:
                self.terminal_handler(research_id, terminal_snapshot)

    def request_continue(self, research_id: str) -> None:
        """设置 continue_event（继续事件），恢复人工登录或验证后的当前方向。"""
        self._validate_bound_research(research_id)
        snapshot = self.store.read_status(research_id)
        if snapshot is None or snapshot.status is not ResearchStatus.WAITING_USER:
            return
        self.continue_event.set()

    def request_cancel(self, research_id: str) -> None:
        """设置 cancel_event（取消事件），Runner 在下一安全检查点转为 cancelling。"""
        self._validate_bound_research(research_id)
        self.cancel_event.set()
        self.continue_event.set()

    def wait_for_user(
        self,
        context: DirectionRunContext,
        *,
        stage: ResearchStage,
    ) -> None:
        """暂停有效预算并无限等待用户继续或取消，不使用超时轮询结束任务。"""
        self._validate_bound_research(context.research_id)
        context.budget.pause_for_user()
        self.continue_event.clear()
        self._transition(
            context.research_id,
            ResearchStatus.WAITING_USER,
            stage=stage,
            available_actions=("continue", "cancel"),
        )
        while True:
            if self.cancel_event.is_set():
                raise _CancellationRequested()
            if self.continue_event.wait(timeout=0.25):
                break
        if self.cancel_event.is_set():
            raise _CancellationRequested()
        context.budget.resume_from_user()
        self.continue_event.clear()
        self._transition(
            context.research_id,
            ResearchStatus.RUNNING,
            stage=stage,
            available_actions=("cancel",),
        )

    def update_progress(
        self,
        context: DirectionRunContext,
        *,
        keyword: str | None = None,
        city: str | None = None,
    ) -> ResearchSnapshot:
        """把方向计数、当前关键词和城市写入状态快照，不改变生命周期状态。"""
        snapshot = self.store.read_status(context.research_id)
        if snapshot is None:
            raise RuntimeError("research snapshot does not exist")
        updated = snapshot.model_copy(
            update={
                "direction_run_id": context.direction_run_id,
                "direction_name": context.direction.direction_name,
                "keyword": keyword,
                "city": city,
                "candidate_count": context.candidate_count,
                "valid_job_count": context.valid_job_count,
                "rejected_job_count": context.rejected_job_count,
                "rejection_counts": dict(context.rejection_counts),
                "recent_rejections": tuple(context.recent_rejections),
                "synthesis_validation_audits": tuple(context.synthesis_validation_audits),
                "semantic_rejected_job_count": context.semantic_rejected_job_count,
                "semantic_failure_counts": dict(context.semantic_failure_counts),
                "recent_semantic_failures": tuple(context.recent_semantic_failures),
                "semantic_analyzed_count": context.semantic_analyzed_count,
                "elapsed_seconds": context.budget.elapsed_seconds(),
                "updated_at": datetime.now(UTC),
            }
        )
        self.store.write_status(updated)
        return updated

    def join(self, timeout: float | None = None) -> bool:
        """等待唯一后台线程结束，并返回线程是否已经退出。"""
        thread = self._thread
        if thread is None:
            return True
        thread.join(timeout=timeout)
        return not thread.is_alive()

    @property
    def is_alive(self) -> bool:
        """返回唯一后台线程是否仍在执行。"""
        return self._thread is not None and self._thread.is_alive()

    def replace_browser_page(self, page: Any) -> None:
        """在 Runner 所在线程登记专用 Chrome 重启后的新唯一标签页。"""
        thread = self._thread
        if thread is not None and thread.ident != threading.get_ident():
            raise RuntimeError("browser page can only be replaced from the Runner thread")
        self._browser_page = page

    def _run_direction(self, context: DirectionRunContext) -> None:
        """按固定阶段顺序执行一个方向，并在预算耗尽时应用唯一兜底提取。"""
        for stage in _BUDGETED_STAGES:
            self._check_cancelled(context.research_id)
            if context.budget.remaining_seconds() <= 0:
                if stage is ResearchStage.EXTRACTING_SEMANTICS:
                    self._run_fallback_extraction(context)
                    break
                raise MarketResearchError(
                    MarketResearchErrorCode.BUDGET_EXHAUSTED,
                    stage=stage.value,
                )
            self._update_stage(context.research_id, stage, context)
            handler = self.stage_handlers.get(stage)
            if handler is None:
                raise MarketResearchError(
                    MarketResearchErrorCode.EXECUTION_FAILED,
                    stage=stage.value,
                    message=f"stage handler is not configured: {stage.value}",
                )
            handler(context)
            self.update_progress(context)

        for stage in _POST_BUDGET_STAGES:
            self._check_cancelled(context.research_id)
            self._update_stage(context.research_id, stage, context)
            handler = self.stage_handlers.get(stage)
            if handler is None:
                raise MarketResearchError(
                    MarketResearchErrorCode.EXECUTION_FAILED,
                    stage=stage.value,
                    message=f"stage handler is not configured: {stage.value}",
                )
            handler(context)
            self.update_progress(context)

    def _run_fallback_extraction(self, context: DirectionRunContext) -> None:
        """预算外执行最多两次兜底批量提取，仅限零常规尝试且存在有效岗位。"""
        if context.llm_attempt_count != 0 or context.valid_job_count < 1:
            raise MarketResearchError(
                MarketResearchErrorCode.BUDGET_EXHAUSTED,
                stage=ResearchStage.EXTRACTING_SEMANTICS.value,
            )
        if self.fallback_extractor is None:
            raise MarketResearchError(
                MarketResearchErrorCode.EXECUTION_FAILED,
                stage=ResearchStage.EXTRACTING_SEMANTICS.value,
                message="fallback extractor is not configured",
            )
        last_error: Exception | None = None
        for _attempt in range(2):
            self._check_cancelled(context.research_id)
            try:
                self.fallback_extractor(context)
                self.update_progress(context)
                return
            except Exception as error:
                last_error = error
        raise self._normalize_error(last_error or RuntimeError("fallback extraction failed"))

    def _update_stage(
        self,
        research_id: str,
        stage: ResearchStage,
        context: DirectionRunContext,
    ) -> ResearchSnapshot:
        """在不改变 running 状态时切换具体执行阶段并同步方向计数。"""
        snapshot = self.store.read_status(research_id)
        if snapshot is None or snapshot.status is not ResearchStatus.RUNNING:
            raise RuntimeError("research must be running before stage update")
        updated = snapshot.model_copy(
            update={
                "stage": stage,
                "direction_run_id": context.direction_run_id,
                "direction_name": context.direction.direction_name,
                "keyword": None,
                "city": None,
                "candidate_count": context.candidate_count,
                "valid_job_count": context.valid_job_count,
                "rejected_job_count": context.rejected_job_count,
                "rejection_counts": dict(context.rejection_counts),
                "recent_rejections": tuple(context.recent_rejections),
                "synthesis_validation_audits": tuple(context.synthesis_validation_audits),
                "semantic_rejected_job_count": context.semantic_rejected_job_count,
                "semantic_failure_counts": dict(context.semantic_failure_counts),
                "recent_semantic_failures": tuple(context.recent_semantic_failures),
                "semantic_analyzed_count": context.semantic_analyzed_count,
                "elapsed_seconds": context.budget.elapsed_seconds(),
                "available_actions": ("cancel",),
                "updated_at": datetime.now(UTC),
            }
        )
        self.store.write_status(updated)
        self.store.append_event(
            research_id,
            {
                "event": "research.stage_changed",
                "status": updated.status.value,
                "stage": stage.value,
                "direction_run_id": context.direction_run_id,
                "direction_name": context.direction.direction_name,
                "elapsed_seconds": updated.elapsed_seconds,
            },
        )
        return updated

    def _update_run_stage(
        self,
        research_id: str,
        stage: ResearchStage,
    ) -> ResearchSnapshot:
        """在方向开始前更新浏览器等整次运行级阶段，不伪造方向计数。"""
        snapshot = self.store.read_status(research_id)
        if snapshot is None or snapshot.status is not ResearchStatus.RUNNING:
            raise RuntimeError("research must be running before run stage update")
        updated = snapshot.model_copy(
            update={
                "stage": stage,
                "available_actions": ("cancel",),
                "updated_at": datetime.now(UTC),
            }
        )
        self.store.write_status(updated)
        self.store.append_event(
            research_id,
            {
                "event": "research.stage_changed",
                "status": updated.status.value,
                "stage": stage.value,
                "elapsed_seconds": updated.elapsed_seconds,
            },
        )
        return updated

    def _transition(
        self,
        research_id: str,
        target: ResearchStatus,
        *,
        stage: ResearchStage | None = None,
        error: MarketResearchErrorPayload | None = None,
        available_actions: tuple[str, ...] | None = None,
    ) -> ResearchSnapshot:
        """校验并持久化唯一允许的生命周期状态转移，终态不能回退。"""
        snapshot = self.store.read_status(research_id)
        if snapshot is None:
            raise RuntimeError("research snapshot does not exist")
        if target not in _ALLOWED_STATUS_TRANSITIONS[snapshot.status]:
            raise RuntimeError(
                f"invalid research status transition: {snapshot.status.value}->{target.value}"
            )
        actions = available_actions
        if actions is None:
            actions = () if target in {
                ResearchStatus.COMPLETED,
                ResearchStatus.PARTIAL_COMPLETED,
                ResearchStatus.FAILED,
                ResearchStatus.CANCELLED,
                ResearchStatus.CANCELLING,
            } else ("cancel",)
        updated = snapshot.model_copy(
            update={
                "status": target,
                "stage": stage or snapshot.stage,
                "available_actions": actions,
                "error": error,
                "updated_at": datetime.now(UTC),
            }
        )
        validated = ResearchSnapshot.model_validate(updated)
        self.store.write_status(validated)
        self.store.update_active_run_status(research_id, target)
        self.store.append_event(
            research_id,
            {
                "event": "research.status_changed",
                "status": target.value,
                "stage": validated.stage.value,
                "error_code": error.error_code if error is not None else None,
                "elapsed_seconds": validated.elapsed_seconds,
            },
        )
        return validated

    def _check_cancelled(self, research_id: str) -> None:
        """在安全检查点把 cancel_event（取消事件）转换为内部取消流程。"""
        self._validate_bound_research(research_id)
        if self.cancel_event.is_set():
            raise _CancellationRequested()

    def _cancel_and_cleanup(self, research_id: str) -> ResearchSnapshot:
        """幂等进入 cancelling，清理全部未发布数据后才写 cancelled 终态。"""
        snapshot = self.store.read_status(research_id)
        if snapshot is None:
            raise RuntimeError("research snapshot does not exist")
        if snapshot.status is ResearchStatus.CANCELLED:
            return snapshot
        if snapshot.status is not ResearchStatus.CANCELLING:
            snapshot = self._transition(
                research_id,
                ResearchStatus.CANCELLING,
                available_actions=(),
            )
        self.store.cleanup_cancelled_run(research_id)
        return self._transition(
            research_id,
            ResearchStatus.CANCELLED,
            stage=ResearchStage.FINISHED,
            available_actions=(),
        )

    def _validate_bound_research(self, research_id: str) -> None:
        """保证控制请求只能操作当前 Runner 绑定的 research_id（调研编号）。"""
        if self._research_id != research_id:
            raise ValueError("runner is not bound to this research_id")

    @staticmethod
    def _normalize_error(error: Exception) -> MarketResearchError:
        """把阶段异常压缩为不含页面原文、DOM、Cookie 或堆栈的结构化错误。"""
        if isinstance(error, MarketResearchError):
            return error
        return MarketResearchError(
            MarketResearchErrorCode.EXECUTION_FAILED,
            message=type(error).__name__,
        )
