from __future__ import annotations

import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from career_os.platform.market_research.browser import DedicatedChromeSession
from career_os.platform.market_research.boss import BossJobCollector
from career_os.platform.market_research.errors import (
    MarketResearchError,
    MarketResearchErrorCode,
)
from career_os.platform.market_research.models import (
    DirectionRetryRun,
    FailedDirection,
    ResearchPlan,
    ResearchSnapshot,
    ResearchStage,
    ResearchStatus,
)
from career_os.platform.market_research.extraction import (
    SemanticExtractionEngine,
    build_extraction_stage_handler,
    build_fallback_extractor,
)
from career_os.platform.market_research.page_contracts import (
    BossPageContract,
    TrendsPageContract,
)
from career_os.platform.market_research.plans import MarketResearchPlanStore
from career_os.platform.market_research.runner import (
    DirectionRunContext,
    MarketResearchRunner,
    TerminalHandler,
)
from career_os.platform.market_research.statistics import (
    DeterministicStatisticsCalculator,
    build_statistics_stage_handler,
)
from career_os.platform.market_research.store import MarketResearchStore
from career_os.platform.market_research.synthesis import (
    MarketCompletionPublisher,
    MarketSynthesisService,
    build_synthesis_stage_handler,
)
from career_os.platform.market_research.trends import (
    GoogleTrendsCollector,
)
from career_os.platform.store.session import SessionStore


RunnerFactory = Callable[
    [MarketResearchStore, TerminalHandler],
    MarketResearchRunner,
]
"""RunnerFactory（运行器工厂）为共享 Service 创建带终态回调的单线程 Runner。"""

_DIRECTION_ALIASES: dict[str, tuple[str, ...]] = {
    "llm 应用开发": ("大模型应用开发", "ai 应用开发", "llm应用开发"),
    "大模型应用开发": ("llm 应用开发", "ai 应用开发", "llm应用开发"),
    "ai agent 开发": ("agent 开发", "智能体开发", "ai智能体开发"),
    "agent 开发": ("ai agent 开发", "智能体开发", "ai智能体开发"),
}


class _RetryStoreAdapter:
    """_RetryStoreAdapter（重试存储适配器）让现有 Runner 读写独立重试状态。"""

    def __init__(self, store: MarketResearchStore, retry_id: str) -> None:
        """绑定基础 Store 和唯一 retry_id（重试编号）。"""
        self._store = store
        self._retry_id = retry_id

    def read_status(self, research_id: str) -> ResearchSnapshot | None:
        """把 DirectionRetryRun（方向重试运行）转换为 Runner 使用的状态快照。"""
        if research_id != self._retry_id:
            return None
        retry = self._store.read_retry_status(research_id)
        if retry is None:
            return None
        return ResearchSnapshot(
            research_id=retry.retry_id,
            plan_id=retry.plan_id,
            origin_session_id=retry.origin_session_id,
            status=retry.status,
            stage=retry.stage,
            direction_run_id=retry.direction_run_id,
            direction_name=retry.direction_name,
            keyword=retry.keyword,
            city=retry.city,
            candidate_count=retry.candidate_count,
            valid_job_count=retry.valid_job_count,
            rejected_job_count=retry.rejected_job_count,
            rejection_counts=retry.rejection_counts,
            recent_rejections=retry.recent_rejections,
            synthesis_validation_audits=retry.synthesis_validation_audits,
            semantic_rejected_job_count=retry.semantic_rejected_job_count,
            semantic_failure_counts=retry.semantic_failure_counts,
            recent_semantic_failures=retry.recent_semantic_failures,
            semantic_analyzed_count=retry.semantic_analyzed_count,
            elapsed_seconds=retry.elapsed_seconds,
            available_actions=retry.available_actions,
            error=retry.error,
            created_at=retry.created_at,
            updated_at=retry.updated_at,
        )

    def write_status(self, snapshot: ResearchSnapshot) -> None:
        """把 Runner 状态字段合并回独立重试记录，不触碰原主任务。"""
        retry = self._store.read_retry_status(snapshot.research_id)
        if retry is None:
            raise RuntimeError("direction retry status does not exist")
        self._store.write_retry_status(
            retry.model_copy(
                update={
                    "status": snapshot.status,
                    "stage": snapshot.stage,
                    "direction_run_id": snapshot.direction_run_id,
                    "keyword": snapshot.keyword,
                    "city": snapshot.city,
                    "candidate_count": snapshot.candidate_count,
                    "valid_job_count": snapshot.valid_job_count,
                    "rejected_job_count": snapshot.rejected_job_count,
                    "rejection_counts": snapshot.rejection_counts,
                    "recent_rejections": snapshot.recent_rejections,
                    "synthesis_validation_audits": snapshot.synthesis_validation_audits,
                    "semantic_rejected_job_count": snapshot.semantic_rejected_job_count,
                    "semantic_failure_counts": snapshot.semantic_failure_counts,
                    "recent_semantic_failures": snapshot.recent_semantic_failures,
                    "semantic_analyzed_count": snapshot.semantic_analyzed_count,
                    "elapsed_seconds": snapshot.elapsed_seconds,
                    "available_actions": snapshot.available_actions,
                    "error": snapshot.error,
                    "updated_at": snapshot.updated_at,
                }
            )
        )

    def update_active_run_status(self, research_id: str, status: ResearchStatus) -> None:
        """同步 demo 唯一活动槽的公开状态。"""
        self._store.update_active_run_status(research_id, status)

    def __getattr__(self, name: str) -> Any:
        """把事件、临时目录、清理和浏览器目录操作委托给基础 Store。"""
        return getattr(self._store, name)


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
        self._retry_runners: dict[str, MarketResearchRunner] = {}  # retry_id 到独立方向重试 Runner 的注册表

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
                        {
                            "op": "set",
                            "path": "market.last_research_id",
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

    def find_reuse_candidates(
        self,
        session_id: str,
        direction_key: str,
    ) -> list[dict[str, Any]]:
        """查找但不自动选择同 demo 未过期方向结果。"""
        if not self.session_store.session_exists(session_id):
            raise KeyError(session_id)
        normalized_key = direction_key.strip().casefold()
        alias_set = set(_DIRECTION_ALIASES.get(normalized_key, ()))
        for canonical, known_aliases in _DIRECTION_ALIASES.items():
            if normalized_key in {alias.casefold() for alias in known_aliases}:
                alias_set.add(canonical)
                alias_set.update(known_aliases)
        return [
            candidate.model_dump(mode="json")
            for candidate in self.store.find_reuse_candidates(
                normalized_key,
                aliases=tuple(sorted(alias_set)),
            )
        ]

    def reuse_result(
        self,
        session_id: str,
        research_id: str,
        result_version: int,
        direction_key: str,
    ) -> dict[str, Any]:
        """把用户明确选择的单方向正式结果作为不可变引用绑定到当前 Session。"""
        if not self.session_store.session_exists(session_id):
            raise KeyError(session_id)
        result = self.store.read_result(research_id, result_version)
        selected = None
        for entry in result.successful_directions:
            direction = self.store.resolve_direction_entry(entry)
            if direction.direction_key == direction_key:
                selected = direction
                break
        if selected is None:
            raise KeyError(direction_key)
        if datetime.now(UTC) >= selected.expires_at:
            raise ValueError("market_result_expired")
        direction_ref = self.store.build_direction_reference(
            research_id,
            result_version,
            direction_key,
        ).direction_result_ref
        reuse_ref = {
            "research_id": research_id,
            "result_version": result_version,
            "direction_key": direction_key,
            "direction_result_ref": direction_ref.model_dump(mode="json"),
            "reuse_session_id": session_id,
            "reused_at": datetime.now(UTC).isoformat(),
        }
        self.session_store.bind_market_reuse_for_confirmation(session_id, reuse_ref)
        self.store.append_event(
            research_id,
            {
                "event": "market.result.reused",
                "direction_name": selected.direction_name,
                "result_version": result_version,
                "published": True,
            },
            session_id=session_id,
        )
        return reuse_ref

    def result_references(self, research_id: str, session_id: str) -> list[str]:
        """校验原始结果归属后返回删除前需要展示的 Session 引用关系。"""
        result = self.store.read_result(research_id)
        if result.origin_session_id != session_id:
            raise MarketResearchError(MarketResearchErrorCode.PLAN_FORBIDDEN)
        return self.session_store.sessions_referencing_market_result(research_id)

    def delete_result(
        self,
        research_id: str,
        session_id: str,
    ) -> list[str]:
        """校验原始结果归属，清除 Session 引用后删除全部正式版本。"""
        active = self.store.get_active_run()
        if isinstance(active, dict):
            active_id = active.get("research_id")
            if isinstance(active_id, str):
                retry = self.store.read_retry_status(active_id)
                if retry is not None and retry.parent_research_id == research_id:
                    raise MarketResearchError(MarketResearchErrorCode.RESEARCH_CONFLICT)
        references = self.result_references(research_id, session_id)
        affected = self.session_store.invalidate_market_result_references(research_id)
        self.store.append_event(
            research_id,
            {
                "event": "market.result.deleted",
                "published": False,
            },
        )
        self.store.delete_formal_result(research_id)
        return affected or references

    def continue_research(
        self, research_id: str, session_id: str
    ) -> ResearchSnapshot | DirectionRetryRun:
        """校验归属后恢复 waiting_user（等待用户）状态中的当前方向。"""
        with self._lock:
            retry = self.store.read_retry_status(research_id)
            if retry is not None:
                self._require_retry_owner(retry, session_id)
                runner = self._retry_runners.get(research_id)
                if runner is None:
                    return self._mark_retry_process_interrupted(retry)
                runner.request_continue(research_id)
                return self.store.read_retry_status(research_id) or retry
            snapshot = self.get_status(research_id, session_id)
            runner = self._runners.get(research_id)
            if runner is None:
                raise MarketResearchError(
                    MarketResearchErrorCode.PROCESS_INTERRUPTED,
                    stage=snapshot.stage.value,
                )
            runner.request_continue(research_id)
            return snapshot

    def cancel(
        self, research_id: str, session_id: str
    ) -> ResearchSnapshot | DirectionRetryRun:
        """校验归属并请求活动 Runner 在安全检查点取消和清理。"""
        with self._lock:
            retry = self.store.read_retry_status(research_id)
            if retry is not None:
                self._require_retry_owner(retry, session_id)
                if retry.status in {
                    ResearchStatus.COMPLETED,
                    ResearchStatus.FAILED,
                    ResearchStatus.CANCELLED,
                }:
                    return retry
                runner = self._retry_runners.get(research_id)
                if runner is None:
                    return self._mark_retry_process_interrupted(retry)
                runner.request_cancel(research_id)
                return self.store.read_retry_status(research_id) or retry
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
            runner = self._runners.get(research_id) or self._retry_runners.get(research_id)
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
                continue
            retry = self.store.read_retry_status(research_id)
            if retry is not None:
                self._clear_session_retry_reference(
                    retry.origin_session_id,
                    retry.retry_id,
                )
        return recovered

    def shutdown(self, timeout_seconds: float = 10.0) -> None:
        """请求全部活动 Runner 取消并等待有限时间，不声称支持断点续跑。"""
        with self._lock:
            runners = [*self._runners.items(), *self._retry_runners.items()]
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

    def get_retry_status(
        self,
        retry_id: str,
        session_id: str,
    ) -> DirectionRetryRun:
        """读取属于指定 Session 的独立方向重试状态。"""
        retry = self.store.read_retry_status(retry_id)
        if retry is None:
            raise KeyError(retry_id)
        self._require_retry_owner(retry, session_id)
        return retry

    def retry_direction(
        self,
        research_id: str,
        direction_key: str,
        session_id: str,
    ) -> DirectionRetryRun:
        """为原主任务的一个失败方向启动独立重试，不改写原主任务终态。"""
        with self._lock:
            if self.store.get_active_run() is not None:
                raise MarketResearchError(MarketResearchErrorCode.RESEARCH_CONFLICT)
            parent = self.get_status(research_id, session_id)
            if parent.status not in {
                ResearchStatus.COMPLETED,
                ResearchStatus.PARTIAL_COMPLETED,
                ResearchStatus.FAILED,
            }:
                raise ValueError("market_research_not_terminal")
            plan = self.plan_store.get(parent.plan_id, session_id)
            selected = next(
                (direction for direction in plan.directions if direction.direction_key == direction_key),
                None,
            )
            if selected is None:
                raise KeyError(direction_key)
            latest_ref = self.store.read_latest_ref(research_id)
            if latest_ref is not None:
                latest = self.store.read_result(research_id, latest_ref.result_version)
                failed_keys = {failure.direction_key for failure in latest.failed_directions}
                if direction_key not in failed_keys:
                    raise ValueError("direction_not_failed")
                prior_failed = latest.failed_directions
            else:
                if parent.status is not ResearchStatus.FAILED:
                    raise ValueError("direction_not_failed")
                error = parent.error or MarketResearchError(
                    MarketResearchErrorCode.EXECUTION_FAILED
                ).to_payload()
                prior_failed = tuple(
                    FailedDirection(
                        direction_name=direction.direction_name,
                        direction_key=direction.direction_key,
                        error=error,
                    )
                    for direction in plan.directions
                )
            retry_id = f"research_{uuid.uuid4().hex}"
            now = datetime.now(UTC)
            retry = DirectionRetryRun(
                retry_id=retry_id,
                parent_research_id=research_id,
                base_result_version=(
                    latest_ref.result_version if latest_ref is not None else None
                ),
                plan_id=plan.plan_id,
                origin_session_id=session_id,
                direction_name=selected.direction_name,
                direction_key=selected.direction_key,
                status=ResearchStatus.QUEUED,
                stage=ResearchStage.QUEUED,
                available_actions=("cancel",),
                created_at=now,
                updated_at=now,
            )
            self.store.write_retry_status(retry)
            self.store.reserve_active_run(retry_id, session_id, plan.plan_id)
            self.store.append_event(
                retry_id,
                {
                    "event": "market.retry.started",
                    "status": retry.status.value,
                    "stage": retry.stage.value,
                    "direction_name": retry.direction_name,
                    "retry_count": 1,
                },
            )
            self.session_store.patch_artifacts(
                session_id,
                [
                    {"op": "set", "path": "market.active_retry_id", "value": retry_id},
                    {"op": "set", "path": "market.last_retry_id", "value": retry_id},
                ],
            )
            adapter = _RetryStoreAdapter(self.store, retry_id)
            publisher = MarketCompletionPublisher(
                self.store,
                self.session_store,
                MarketSynthesisService(),
            )
            runner = self.runner_factory(
                adapter,
                lambda run_id, snapshot: self._on_retry_terminal(
                    run_id,
                    snapshot,
                ),
            )
            runner.completion_handler = (
                lambda run_id, retry_plan, successful, _failed: publisher.publish_retry(
                    research_id,
                    run_id,
                    session_id,
                    retry_plan,
                    successful,
                    prior_failed,
                )
            )
            self._retry_runners[retry_id] = runner
            retry_plan = plan.model_copy(update={"directions": (selected,)})
            try:
                runner.start(retry_id, retry_plan)
            except Exception:
                self._retry_runners.pop(retry_id, None)
                self.store.clear_active_run(retry_id)
                self._clear_session_retry_reference(session_id, retry_id)
                raise
            return retry

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

    def _on_retry_terminal(
        self,
        retry_id: str,
        _snapshot: ResearchSnapshot,
    ) -> None:
        """方向重试终止后只释放重试注册和活动槽，不修改原主任务快照。"""
        with self._lock:
            self._retry_runners.pop(retry_id, None)
            self.store.clear_active_run(retry_id)
            retry = self.store.read_retry_status(retry_id)
            if retry is not None:
                self._clear_session_retry_reference(
                    retry.origin_session_id,
                    retry_id,
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

    def _clear_session_retry_reference(self, session_id: str, retry_id: str) -> None:
        """仅在 Session 仍指向该方向重试时清空 active_retry_id（活动重试编号）。"""
        if not self.session_store.session_exists(session_id):
            return
        artifacts = self.session_store.get_artifacts(session_id)
        market = artifacts.get("market") if isinstance(artifacts, dict) else None
        if not isinstance(market, dict) or market.get("active_retry_id") != retry_id:
            return
        self.session_store.patch_artifacts(
            session_id,
            [{"op": "set", "path": "market.active_retry_id", "value": None}],
        )

    def _mark_retry_process_interrupted(
        self, retry: DirectionRetryRun
    ) -> DirectionRetryRun:
        """将没有内存 Runner（执行线程）的遗留重试收敛为可见失败终态。"""
        interrupted = retry.model_copy(
            update={
                "status": ResearchStatus.FAILED,
                "stage": ResearchStage.FINISHED,
                "available_actions": (),
                "error": MarketResearchError(
                    MarketResearchErrorCode.PROCESS_INTERRUPTED,
                    stage=retry.stage.value,
                ).to_payload(),
                "updated_at": datetime.now(UTC),
            }
        )
        self.store.write_retry_status(interrupted)
        self.store.append_event(
            retry.retry_id,
            {
                "event": "market.retry.process_interrupted",
                "status": interrupted.status.value,
                "stage": interrupted.stage.value,
                "error_code": MarketResearchErrorCode.PROCESS_INTERRUPTED.value,
            },
        )
        self.store.clear_active_run(retry.retry_id)
        self._clear_session_retry_reference(retry.origin_session_id, retry.retry_id)
        return interrupted

    @staticmethod
    def _require_owner(snapshot: ResearchSnapshot, session_id: str) -> None:
        """校验 origin_session_id（来源 Session）与控制请求 Session 一致。"""
        if snapshot.origin_session_id != session_id:
            raise MarketResearchError(MarketResearchErrorCode.PLAN_FORBIDDEN)

    @staticmethod
    def _require_retry_owner(retry: DirectionRetryRun, session_id: str) -> None:
        """校验方向重试来源 Session 与控制请求 Session 一致。"""
        if retry.origin_session_id != session_id:
            raise MarketResearchError(MarketResearchErrorCode.PLAN_FORBIDDEN)

    def _default_runner_factory(
        self,
        store: MarketResearchStore,
        terminal_handler: TerminalHandler,
    ) -> MarketResearchRunner:
        """组装浏览器、采集、提取、统计、综合、发布和终态清理的完整单线程 Runner。"""
        browser_session = DedicatedChromeSession(store)
        extraction_engine = SemanticExtractionEngine()
        statistics_calculator = DeterministicStatisticsCalculator()
        synthesis_service = MarketSynthesisService()
        completion_publisher = MarketCompletionPublisher(
            store,
            self.session_store,
            synthesis_service,
        )
        runner: MarketResearchRunner

        def collect_trends(direction_context: DirectionRunContext) -> None:
            """在当前方向复用唯一标签页采集唯一 v2 搜索关注度结果。"""
            contract = TrendsPageContract()
            collector = GoogleTrendsCollector(
                contract=contract,
                navigate_handler=lambda url: browser_session.navigate(
                    url, contract.allowed_hosts
                ),
                user_action_handler=lambda target_url: browser_session.wait_for_user_verification(
                    runner=runner,
                    context=direction_context,
                    contract=contract,
                    stage=ResearchStage.COLLECTING_TRENDS,
                    target_url=target_url,
                ),
            )
            trend_result = collector.collect(
                direction_context.direction,
                direction_context.require_browser_page(),
                direction_context.budget,
            )
            direction_context.record_trend_result(trend_result)

        def collect_boss(direction_context: DirectionRunContext) -> None:
            """在当前方向组装 BOSS 回调，支持登录等待、状态更新和一次安全重启。"""
            contract = BossPageContract()

            def restart_browser() -> object:
                """安全重启已登记专用 Chrome，并让后续方向使用新的唯一标签页。"""
                page = browser_session.restart()
                runner.replace_browser_page(page)
                return page

            collector = BossJobCollector(
                store,
                contract=contract,
                restart_handler=restart_browser,
                user_action_handler=lambda target_url: browser_session.wait_for_user_verification(
                    runner=runner,
                    context=direction_context,
                    contract=contract,
                    stage=ResearchStage.COLLECTING_BOSS,
                    target_url=target_url,
                ),
                page_review_handler=lambda _error: runner.wait_for_user(
                    direction_context,
                    stage=ResearchStage.COLLECTING_BOSS,
                ),
                progress_handler=lambda current, keyword, city: runner.update_progress(
                    current,
                    keyword=keyword,
                    city=city,
                ),
            )
            result = collector.collect(
                direction_context,
                direction_context.require_browser_page(),
            )
            direction_context.record_boss_results(result)

        runner = MarketResearchRunner(
            store,
            stage_handlers={
                ResearchStage.COLLECTING_TRENDS: collect_trends,
                ResearchStage.COLLECTING_BOSS: collect_boss,
                ResearchStage.EXTRACTING_SEMANTICS: build_extraction_stage_handler(
                    extraction_engine
                ),
                ResearchStage.CALCULATING_STATISTICS: build_statistics_stage_handler(
                    statistics_calculator
                ),
                ResearchStage.SYNTHESIZING: build_synthesis_stage_handler(
                    synthesis_service
                ),
            },
            fallback_extractor=build_fallback_extractor(extraction_engine),
            completion_handler=completion_publisher.publish,
            open_handler=browser_session.open,
            close_handler=browser_session.close,
            terminal_handler=terminal_handler,
        )
        return runner


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
