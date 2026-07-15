from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Iterable

from career_os.platform.market_research.models import SkillStatistic, SkillTaxonomy


_BASE_SKILLS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Python", ("Python",)),
    ("Go", ("Go", "Golang")),
    ("Java", ("Java",)),
    ("SQL", ("SQL", "MySQL", "PostgreSQL")),
    ("Docker", ("Docker",)),
    ("Kubernetes", ("Kubernetes", "K8s")),
    ("LLM", ("LLM", "大语言模型")),
    ("AI Agent", ("AI Agent", "智能体", "Agent")),
    ("RAG", ("RAG", "检索增强生成")),
    ("LangChain", ("LangChain",)),
)


@dataclass
class _SkillEntry:
    """_SkillEntry（运行时技能项）累计别名、发现来源和去重后的岗位集合。"""

    canonical_name: str  # 稳定规范技能名
    aliases: list[str]  # 可用于程序 mention 匹配的规范名和别名
    discovery_source: str  # 基础词表或首次发现批次
    mention_job_ids: set[str] = field(default_factory=set)  # JD 直接提及该技能的岗位身份
    required_job_ids: set[str] = field(default_factory=set)  # LLM 判定为必需且依据有效的岗位身份
    preferred_job_ids: set[str] = field(default_factory=set)  # LLM 判定为优先且依据有效的岗位身份


class DynamicSkillTaxonomy:
    """DynamicSkillTaxonomy（动态技能词表）在单方向内递增发现且不回扫较早岗位。"""

    def __init__(
        self,
        direction_key: str,
        *,
        base_skills: Iterable[tuple[str, tuple[str, ...]]] = _BASE_SKILLS,
    ) -> None:
        """用基础词表创建方向级状态；不同方向必须各自构造实例。"""
        self.direction_key = direction_key  # 当前词表所属的规范职业方向键
        self._entries: dict[str, _SkillEntry] = {}  # 规范技能身份到运行时累计项
        for canonical_name, aliases in base_skills:
            self.add_skill(canonical_name, aliases, discovery_source="base")

    def add_skill(
        self,
        canonical_name: str,
        aliases: Iterable[str],
        *,
        discovery_source: str,
    ) -> str:
        """新增或合并一个规范技能；已有技能保留首次发现来源。"""
        canonical = _clean_skill_name(canonical_name)
        if not canonical:
            raise ValueError("canonical skill name is required")
        identity = canonical.casefold()
        alias_values = _deduplicate_names((canonical, *aliases))
        existing = self._entries.get(identity)
        if existing is None:
            self._entries[identity] = _SkillEntry(
                canonical_name=canonical,
                aliases=list(alias_values),
                discovery_source=discovery_source,
            )
        else:
            existing.aliases = list(_deduplicate_names((*existing.aliases, *alias_values)))
        return self._entries[identity].canonical_name

    def known_skills_payload(self) -> list[dict[str, Any]]:
        """返回传给提取模型的当前规范技能和别名，不包含岗位 ID 或用户数据。"""
        return [
            {
                "canonical_name": entry.canonical_name,
                "aliases": list(entry.aliases),
            }
            for entry in self._entries.values()
        ]

    def discover_from_output(
        self,
        skills: Iterable[Any],
        *,
        discovery_source: str,
    ) -> tuple[str, ...]:
        """把已通过原文依据校验的 LLM 技能候选合并到当前方向词表。"""
        discovered: list[str] = []
        for skill in skills:
            canonical = self.add_skill(
                skill.canonical_name,
                skill.aliases,
                discovery_source=discovery_source,
            )
            if canonical not in discovered:
                discovered.append(canonical)
        return tuple(discovered)

    def match_mentions(self, job_id: str, raw_jd: str) -> tuple[str, ...]:
        """使用当前时点词表匹配一个内存 JD；之后发现的新技能不会回扫该岗位。"""
        matched: list[str] = []
        for entry in self._entries.values():
            if any(_contains_alias(raw_jd, alias) for alias in entry.aliases):
                entry.mention_job_ids.add(job_id)
                matched.append(entry.canonical_name)
        return tuple(matched)

    def record_semantic_usage(self, job_id: str, skills: Iterable[Any]) -> tuple[str, ...]:
        """记录依据有效的技能用途；同岗位同技能 required（必需）优先于 preferred（优先）。"""
        recorded: list[str] = []
        for skill in skills:
            identity = _clean_skill_name(skill.canonical_name).casefold()
            entry = self._entries.get(identity)
            if entry is None:
                continue
            entry.mention_job_ids.add(job_id)
            if skill.usage == "required":
                entry.required_job_ids.add(job_id)
                entry.preferred_job_ids.discard(job_id)
            elif skill.usage == "preferred" and job_id not in entry.required_job_ids:
                entry.preferred_job_ids.add(job_id)
            if entry.canonical_name not in recorded:
                recorded.append(entry.canonical_name)
        return tuple(recorded)

    def freeze(self) -> SkillTaxonomy:
        """冻结正式技能统计；两个及以上岗位提及进入 skills，单岗位进入补充区。"""
        formal: list[SkillStatistic] = []
        isolated: list[SkillStatistic] = []
        for entry in self._entries.values():
            if not entry.mention_job_ids:
                continue
            statistic = SkillStatistic(
                canonical_name=entry.canonical_name,
                aliases=tuple(entry.aliases),
                discovery_source=entry.discovery_source,
                mention_job_ids=tuple(sorted(entry.mention_job_ids)),
                required_job_ids=tuple(sorted(entry.required_job_ids)),
                preferred_job_ids=tuple(sorted(entry.preferred_job_ids)),
                mention_count=len(entry.mention_job_ids),
                required_count=len(entry.required_job_ids),
                preferred_count=len(entry.preferred_job_ids),
                mention_denominator=0,
                semantic_denominator=0,
            )
            if statistic.mention_count >= 2:
                formal.append(statistic)
            else:
                isolated.append(statistic)
        return SkillTaxonomy(
            direction_key=self.direction_key,
            skills=tuple(formal),
            emerging_or_isolated=tuple(isolated),
        )


def _clean_skill_name(value: str) -> str:
    """规范技能名 Unicode 和空白，同时保留用户可读大小写。"""
    normalized = unicodedata.normalize("NFKC", value)
    return " ".join(normalized.strip().split())


def _deduplicate_names(values: Iterable[str]) -> tuple[str, ...]:
    """按大小写无关身份去重技能名和别名，并保持首次出现顺序。"""
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = _clean_skill_name(value)
        identity = cleaned.casefold()
        if cleaned and identity not in seen:
            seen.add(identity)
            result.append(cleaned)
    return tuple(result)


def _contains_alias(raw_jd: str, alias: str) -> bool:
    """中英文均执行大小写无关 mention 匹配，英文短词使用字母数字边界避免误命中。"""
    normalized_jd = unicodedata.normalize("NFKC", raw_jd).casefold()
    normalized_alias = unicodedata.normalize("NFKC", alias).casefold()
    if not normalized_alias:
        return False
    if re.fullmatch(r"[a-z0-9+#. -]+", normalized_alias):
        pattern = rf"(?<![a-z0-9]){re.escape(normalized_alias)}(?![a-z0-9])"
        return re.search(pattern, normalized_jd) is not None
    return normalized_alias in normalized_jd
