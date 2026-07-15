from __future__ import annotations

import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable

from career_os.platform.market_research.errors import (
    MarketResearchError,
    MarketResearchErrorCode,
)
from career_os.platform.market_research.models import (
    ResearchSnapshot,
    ResearchStage,
    ResearchStatus,
)
from career_os.platform.market_research.plans import MarketResearchPlanStore
from career_os.platform.market_research.runner import MarketResearchRunner, TerminalHandler
from career_os.platform.market_research.store import MarketResearchStore
from career_os.platform.store.session import SessionStore


RunnerFactory = Callable[
    [MarketResearchStore, TerminalHandler],
    MarketResearchRunner,
]
"""RunnerFactory（运行器工厂）为共享 Service 创建带终态回调的单线程 Runner。"""


class MarketResearchService:
    """MarketResearchService（市场调研应用门面）统一管理方案消费、单任务锁和运行控制。"""

    def __init__(
        self,
        *,
        store: MarketResearchStore | None = None,
        plan_store: MarketResearchPlanStore | None = None,
        session_store: SessionStore | None = None,
        runner_factory: RunnerFactory | None = None,
    ) -> None:
        """注入同一 demo 的 Store、方案 Store、Session Store 和 Runner 工厂。"""
        self.store = store or MarketResearchStore()  # 运行状态、活动锁和正式结果存储器
        self.plan_store = plan_store or MarketResearchPlanStore(self.store.root)  # 冻结方案存储器
        self.session_store = session_store or SessionStore()  # Session 生命周期信封存储器
        self.runner_factory = runner_factory or self._default_runner_factory  # 单线程 Runner 构造函数
        self._lock = threading.RLock()  # 包住检查、占位、消费和 Runner 注册的完整临界区
        self._runners: dict[str, MarketResearchRunner] = {}  # research_id 到活动 Runner 的唯一注册表

    def start(self, plan_id: str, session_id: str) -> ResearchSnapshot:
        """消费用户确认方案并在完整单任务临界区内启动后台调研。"""
        with self._lock:
            active_run = self.store.get_active_run()
            if active_run is not None:
                summary = {
                    "research_id": active_run.get("research_id"),
                    "status": active_run.get("status"),
                }
                raise MarketResearchError(
                    MarketResearchErrorCode.RESEARCH_CONFLICT,
                    message=f"active research exists: {summary}",
                )

            plan = self.plan_store.get(plan_id, session_id)
            if plan.status != "confirmed" or plan.confirmed_at is None:
                raise MarketResearchError(MarketResearchErrorCode.PLAN_NOT_CONFIRMED)
            research_id = f"research_{uuid.uuid4().hex}"
            now = datetime.now(UTC)
            queued = ResearchSnapshot(
                research_id=research_id,
                plan_id=plan_id,
                origin_session_id=session_id,
                status=ResearchStatus.QUEUED,
                stage=ResearchStage.QUEUED,
                available_actions=("cancel",),
                created_at=now,
                updated_at=now,
            )
            consumed = False
            reserved = False
            try:
                self.store.write_status(queued)
                self.store.reserve_active_run(research_id, session_id, plan_id)
                reserved = True
                frozen_plan = self.plan_store.consume(plan_id, session_id)
                consumed = True
                self.session_store.patch_artifacts(
                    session_id,
                    [
                        {
                            "op": "set",
                            "path": "market.active_plan_id",
                            "value": plan_id,
                        },
                        {
                            "op": "set",
                            "path": "market.active_research_id",
                            "value": research_id,
                        },
                    ],
                )
                runner = self.runner_factory(self.store, self._on_runner_terminal)
                self._runners[research_id] = runner
                runner.start(research_id, frozen_plan)
                return queued
            except Exception as error:
                self._runners.pop(research_id, None)
                if reserved:
                    self.store.clear_active_run(research_id)
                if consumed:
                    failed = queued.model_copy(
                        update={
                            "status": ResearchStatus.FAILED,
                            "stage": ResearchStage.FINISHED,
                            "available_actions": (),
                            "error": MarketResearchError(
                                MarketResearchErrorCode.EXECUTION_FAILED,
                                stage=ResearchStage.STARTING_BROWSER.value,
                                message=type(error).__name__,
                            ).to_payload(),
                            "updated_at": datetime.now(UTC),
                        }
                    )
                    self.store.write_status(failed)
                    self._clear_session_active_reference(session_id, research_id)
                else:
                    self.store.delete_run_placeholder(research_id)
                raise

    def get_status(self, research_id: str, session_id: str) -> ResearchSnapshot:
        """读取属于指定 Session 的调研状态快照。"""
        snapshot = self.store.read_status(research_id)
        if snapshot is None:
            raise KeyError(research_id)
        self._require_owner(snapshot, session_id)
        return snapshot

    def continue_research(self, research_id: str, session_id: str) -> ResearchSnapshot:
        """校验归属后恢复 waiting_user（等待用户）状态中的当前方向。"""
        with self._lock:
            snapshot = self.get_status(research_id, session_id)
            runner = self._runners.get(research_id)
            if runner is None:
                raise MarketResearchError(
                    MarketResearchErrorCode.PROCESS_INTERRUPTED,
                    stage=snapshot.stage.value,
                )
            runner.request_continue(research_id)
            return snapshot

    def cancel(self, research_id: str, session_id: str) -> ResearchSnapshot:
        """校验归属并请求活动 Runner 在安全检查点取消和清理。"""
        with self._lock:
            snapshot = self.get_status(research_id, session_id)
            if snapshot.status in {
                ResearchStatus.COMPLETED,
                ResearchStatus.PARTIAL_COMPLETED,
                ResearchStatus.FAILED,
                ResearchStatus.CANCELLED,
            }:
                return snapshot
            runner = self._runners.get(research_id)
            if runner is None:
                raise MarketResearchError(
                    MarketResearchErrorCode.PROCESS_INTERRUPTED,
                    stage=snapshot.stage.value,
                )
            runner.request_cancel(research_id)
            return snapshot

    def cancel_for_session_delete(
        self,
        research_id: str,
        session_id: str,
        *,
        timeout_seconds: float = 10.0,
    ) -> None:
        """删除 Session 前取消所属活动任务，并等待未发布临时数据完成清理。"""
        self.cancel(research_id, session_id)
        with self._lock:
            runner = self._runners.get(research_id)
        if runner is not None and not runner.join(timeout_seconds):
            raise RuntimeError("market research cancellation did not finish before session delete")

    def recover_interrupted_runs(self) -> list[str]:
        """恢复启动时遗留活动状态，并清除相关 Session 的活动任务引用。"""
        recovered = self.store.recover_interrupted_runs()
        for research_id in recovered:
            snapshot = self.store.read_status(research_id)
            if snapshot is not None:
                self._clear_session_active_reference(
                    snapshot.origin_session_id,
                    research_id,
                )
        return recovered

    def shutdown(self, timeout_seconds: float = 10.0) -> None:
        """请求全部活动 Runner 取消并等待有限时间，不声称支持断点续跑。"""
        with self._lock:
            runners = list(self._runners.items())
        for research_id, runner in runners:
            if runner.is_alive:
                runner.request_cancel(research_id)
        deadline = time.monotonic() + timeout_seconds
        for _research_id, runner in runners:
            remaining = max(0.0, deadline - time.monotonic())
            runner.join(remaining)

    def active_summary(self) -> dict[str, object] | None:
        """返回当前活动任务的调研编号和公开状态，不包含 Session、方案内容或路径。"""
        active_run = self.store.get_active_run()
        if active_run is None:
            return None
        return {
            "research_id": active_run.get("research_id"),
            "status": active_run.get("status"),
        }

    def _on_runner_terminal(
        self,
        research_id: str,
        snapshot: ResearchSnapshot,
    ) -> None:
        """Runner 进入终态后释放注册、demo 活动槽和 Session 活动引用。"""
        with self._lock:
            self._runners.pop(research_id, None)
            self.store.clear_active_run(research_id)
            self._clear_session_active_reference(
                snapshot.origin_session_id,
                research_id,
            )

    def _clear_session_active_reference(
        self,
        session_id: str,
        research_id: str,
    ) -> None:
        """仅当 Session 仍指向当前调研时清空 active_research_id（活动调研编号）。"""
        if not self.session_store.session_exists(session_id):
            return
        artifacts = self.session_store.get_artifacts(session_id)
        market = artifacts.get("market") if isinstance(artifacts, dict) else None
        if not isinstance(market, dict) or market.get("active_research_id") != research_id:
            return
        self.session_store.patch_artifacts(
            session_id,
            [
                {
                    "op": "set",
                    "path": "market.active_research_id",
                    "value": None,
                }
            ],
        )

    @staticmethod
    def _require_owner(snapshot: ResearchSnapshot, session_id: str) -> None:
        """校验 origin_session_id（来源 Session）与控制请求 Session 一致。"""
        if snapshot.origin_session_id != session_id:
            raise MarketResearchError(MarketResearchErrorCode.PLAN_FORBIDDEN)

    @staticmethod
    def _default_runner_factory(
        store: MarketResearchStore,
        terminal_handler: TerminalHandler,
    ) -> MarketResearchRunner:
        """创建默认单线程 Runner；后续采集任务向它注入阶段实现。"""
        return MarketResearchRunner(store, terminal_handler=terminal_handler)


_service_lock = threading.RLock()
_service: MarketResearchService | None = None


def initialize_market_research_service(
    *,
    root: Path | None = None,
    runner_factory: RunnerFactory | None = None,
) -> MarketResearchService:
    """initialize_market_research_service（初始化市场调研服务）创建进程内唯一共享实例。"""
    global _service
    with _service_lock:
        if _service is None:
            store = MarketResearchStore(root) if root is not None else MarketResearchStore()
            _service = MarketResearchService(store=store, runner_factory=runner_factory)
        return _service


def get_market_research_service() -> MarketResearchService:
    """get_market_research_service（获取市场调研服务）返回已初始化实例，否则明确失败。"""
    with _service_lock:
        if _service is None:
            raise RuntimeError("market research service is not initialized")
        return _service


def shutdown_market_research_service() -> None:
    """shutdown_market_research_service（关闭市场调研服务）取消线程并释放全局实例。"""
    global _service
    with _service_lock:
        service = _service
    if service is not None:
        service.shutdown()
    with _service_lock:
        if _service is service:
            _service = None
