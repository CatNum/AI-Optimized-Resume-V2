from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import unicodedata
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from career_os.config import settings
from career_os.platform.market_research.errors import (
    MarketResearchError,
    MarketResearchErrorCode,
)
from career_os.platform.market_research.models import (
    DirectionPlan,
    DirectionProposal,
    FilterPolicy,
    ResearchPlan,
)
from career_os.platform.trace.writer import TraceWriter


_plan_lock = threading.RLock()
_DEFAULT_CITIES = ("北京", "上海", "深圳", "杭州")
_PLAN_ID_PATTERN = re.compile(r"^plan_[0-9a-f]+$")


def _normalize_text(value: str) -> str:
    """规范化用户确认的名称、关键词和城市文本。"""
    normalized = unicodedata.normalize("NFKC", value)
    return " ".join(normalized.strip().split())


def _normalize_direction_key(direction_name: str) -> str:
    """把职业方向显示名称转换为稳定的跨 Session 复用键。"""
    return _normalize_text(direction_name).casefold()


def _deduplicate_texts(values: tuple[str, ...]) -> tuple[str, ...]:
    """按规范化文本去重并保持用户确认的原始顺序。"""
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = _normalize_text(value)
        identity = normalized.casefold()
        if normalized and identity not in seen:
            result.append(normalized)
            seen.add(identity)
    return tuple(result)


class MarketResearchPlanStore:
    """MarketResearchPlanStore（调研方案存储器）唯一负责方案创建、版本、确认和消费。"""

    def __init__(self, root: Path | None = None) -> None:
        """初始化方案目录；root 用于显式指定当前 demo 的市场数据根。"""
        self.root = root or Path(settings.data_dir) / "market_research"
        self.plans_dir = self.root / "plans"

    def create_draft(
        self,
        session_id: str,
        directions: list[DirectionProposal],
        filter_policy: FilterPolicy | None = None,
    ) -> ResearchPlan:
        """创建未确认方案；补齐默认城市和系统固定筛选策略。"""
        normalized_directions = self._normalize_directions(directions)
        now = datetime.now(UTC)
        plan = ResearchPlan(
            plan_id=f"plan_{uuid.uuid4().hex}",
            plan_version=1,
            status="draft",
            directions=normalized_directions,
            filter_policy=filter_policy or FilterPolicy(),
            source_session_id=session_id,
            generated_at=now,
            confirmed_at=None,
            plan_hash="",
        )
        with _plan_lock:
            self._write_plan_unlocked(plan)
        TraceWriter().emit_market(
            "market.plan.generated",
            session_id=session_id,
            detail={
                "plan_id": plan.plan_id,
                "plan_version": plan.plan_version,
                "direction_count": len(plan.directions),
                "status": plan.status,
            },
        )
        return plan

    def revise(
        self,
        plan_id: str,
        session_id: str,
        directions: list[DirectionProposal],
    ) -> ResearchPlan:
        """修改方案并递增版本；任何修改都会清空确认时间和确认哈希。"""
        normalized_directions = self._normalize_directions(directions)
        with _plan_lock:
            current = self._read_owned_plan_unlocked(plan_id, session_id)
            if current.status == "consumed":
                raise MarketResearchError(MarketResearchErrorCode.PLAN_CONSUMED)
            revised = current.model_copy(
                update={
                    "plan_version": current.plan_version + 1,
                    "status": "draft",
                    "directions": normalized_directions,
                    "confirmed_at": None,
                    "plan_hash": "",
                }
            )
            self._write_plan_unlocked(revised)
        TraceWriter().emit_market(
            "market.plan.revised",
            session_id=session_id,
            detail={
                "plan_id": revised.plan_id,
                "plan_version": revised.plan_version,
                "direction_count": len(revised.directions),
                "status": revised.status,
            },
        )
        return revised

    def confirm(self, plan_id: str, session_id: str) -> ResearchPlan:
        """重新计算方案哈希，校验归属后把方案状态改为 confirmed。"""
        with _plan_lock:
            current = self._read_owned_plan_unlocked(plan_id, session_id)
            if current.status == "consumed":
                raise MarketResearchError(MarketResearchErrorCode.PLAN_CONSUMED)
            plan_hash = self._calculate_plan_hash(current)
            confirmed = current.model_copy(
                update={
                    "status": "confirmed",
                    "confirmed_at": datetime.now(UTC),
                    "plan_hash": plan_hash,
                }
            )
            self._write_plan_unlocked(confirmed)
        TraceWriter().emit_market(
            "market.plan.confirmed",
            session_id=session_id,
            detail={
                "plan_id": confirmed.plan_id,
                "plan_version": confirmed.plan_version,
                "direction_count": len(confirmed.directions),
                "status": confirmed.status,
            },
        )
        return confirmed

    def consume(self, plan_id: str, session_id: str) -> ResearchPlan:
        """原子复核确认状态和哈希，再把方案改为 consumed 防止重复启动。"""
        with _plan_lock:
            current = self._read_owned_plan_unlocked(plan_id, session_id)
            if current.status == "consumed":
                raise MarketResearchError(MarketResearchErrorCode.PLAN_CONSUMED)
            if current.status != "confirmed" or current.confirmed_at is None:
                raise MarketResearchError(MarketResearchErrorCode.PLAN_NOT_CONFIRMED)
            current_hash = self._calculate_plan_hash(current)
            if current_hash != current.plan_hash:
                raise MarketResearchError(MarketResearchErrorCode.PLAN_HASH_MISMATCH)
            consumed = current.model_copy(update={"status": "consumed"})
            self._write_plan_unlocked(consumed)
        return consumed

    def get(self, plan_id: str, session_id: str) -> ResearchPlan:
        """读取属于指定 Session 的完整方案预览。"""
        with _plan_lock:
            return self._read_owned_plan_unlocked(plan_id, session_id)

    def _normalize_directions(
        self, directions: list[DirectionProposal]
    ) -> tuple[DirectionPlan, ...]:
        """校验数量并把 Worker 提案转换为带默认值的冻结方向。"""
        max_directions = settings.market_research.max_directions
        if not 1 <= len(directions) <= max_directions:
            raise ValueError(f"directions must contain 1 to {max_directions} items")
        normalized: list[DirectionPlan] = []
        seen_keys: set[str] = set()
        for proposal in directions:
            parsed = DirectionProposal.model_validate(proposal)
            direction_name = _normalize_text(parsed.direction_name)
            direction_key = _normalize_direction_key(direction_name)
            if not direction_name or direction_key in seen_keys:
                raise ValueError("direction names must be non-empty and unique")
            boss_keywords = _deduplicate_texts(parsed.boss_keywords)
            trends_keywords = _deduplicate_texts(parsed.trends_keywords)
            cities = _deduplicate_texts(parsed.cities) or _DEFAULT_CITIES
            if not boss_keywords or not trends_keywords:
                raise ValueError("each direction requires BOSS and Trends keywords")
            normalized.append(
                DirectionPlan(
                    direction_name=direction_name,
                    direction_key=direction_key,
                    boss_keywords=boss_keywords,
                    trends_keywords=trends_keywords,
                    cities=cities,
                    experience_basis=parsed.experience_basis,
                    experience_min=parsed.experience_min,
                    experience_max=parsed.experience_max,
                )
            )
            seen_keys.add(direction_key)
        return tuple(normalized)

    def _calculate_plan_hash(self, plan: ResearchPlan) -> str:
        """只用用户确认的规范化业务字段计算稳定 SHA-256 方案摘要。"""
        payload: dict[str, Any] = {
            "directions": [direction.model_dump(mode="json") for direction in plan.directions],
            "filter_policy": plan.filter_policy.model_dump(mode="json"),
            "budget_seconds": plan.budget_seconds,
        }
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _plan_path(self, plan_id: str) -> Path:
        """校验方案编号并返回受控方案文件路径。"""
        if not _PLAN_ID_PATTERN.fullmatch(plan_id):
            raise MarketResearchError(MarketResearchErrorCode.PLAN_NOT_FOUND)
        return self.plans_dir / f"{plan_id}.json"

    def _read_owned_plan_unlocked(self, plan_id: str, session_id: str) -> ResearchPlan:
        """读取方案并校验来源 Session，调用方必须已经持有方案锁。"""
        path = self._plan_path(plan_id)
        if not path.exists():
            raise MarketResearchError(MarketResearchErrorCode.PLAN_NOT_FOUND)
        with path.open(encoding="utf-8") as file:
            plan = ResearchPlan.model_validate(json.load(file))
        if plan.source_session_id != session_id:
            raise MarketResearchError(MarketResearchErrorCode.PLAN_FORBIDDEN)
        return plan

    def _write_plan_unlocked(self, plan: ResearchPlan) -> None:
        """使用同目录临时文件原子写入方案，调用方必须已经持有方案锁。"""
        self.plans_dir.mkdir(parents=True, exist_ok=True)
        path = self._plan_path(plan.plan_id)
        temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        payload = plan.model_dump(mode="json")
        try:
            with temp_path.open("w", encoding="utf-8") as file:
                json.dump(payload, file, ensure_ascii=False, indent=2, sort_keys=True)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temp_path, path)
            directory_fd = os.open(self.plans_dir, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            if temp_path.exists():
                temp_path.unlink()
