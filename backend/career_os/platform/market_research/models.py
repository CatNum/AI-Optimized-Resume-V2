from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


KeywordTuple = Annotated[tuple[str, ...], Field(min_length=1, max_length=3)]
ProposalCityTuple = Annotated[tuple[str, ...], Field(max_length=4)]
CityTuple = Annotated[tuple[str, ...], Field(min_length=1, max_length=4)]


class ResearchStatus(StrEnum):
    """ResearchStatus（调研状态）表示市场调研主任务当前所处的生命周期状态。"""

    QUEUED = "queued"  # 已创建任务并等待后台线程执行
    RUNNING = "running"  # 后台线程正在执行调研
    WAITING_USER = "waiting_user"  # 等待用户完成登录或验证
    CANCELLING = "cancelling"  # 正在停止任务并清理临时数据
    COMPLETED = "completed"  # 所有职业方向均调研成功
    PARTIAL_COMPLETED = "partial_completed"  # 至少一个方向成功且至少一个方向失败
    FAILED = "failed"  # 没有任何职业方向调研成功
    CANCELLED = "cancelled"  # 用户取消且临时数据已经清理


class ResearchStage(StrEnum):
    """ResearchStage（调研阶段）表示后台线程当前正在执行的具体步骤。"""

    QUEUED = "queued"  # 等待后台线程开始
    STARTING_BROWSER = "starting_browser"  # 启动专用可见 Chrome
    COLLECTING_TRENDS = "collecting_trends"  # 获取搜索关注度数据
    COLLECTING_BOSS = "collecting_boss"  # 采集 BOSS 岗位详情
    EXTRACTING_SEMANTICS = "extracting_semantics"  # 使用 LLM 提取岗位语义
    CALCULATING_STATISTICS = "calculating_statistics"  # 计算确定性统计结果
    SYNTHESIZING = "synthesizing"  # 生成只读市场综合结果
    PERSISTING = "persisting"  # 原子发布正式结果
    FINISHED = "finished"  # 当前运行已经结束


class RecruiterActivity(StrEnum):
    """RecruiterActivity（招聘者活跃度）保存用户预览和确认时使用的规范值。"""

    JUST_ACTIVE = "刚刚活跃"  # 招聘者页面显示刚刚活跃
    ACTIVE_TODAY = "今日活跃"  # 招聘者页面显示今日活跃
    ACTIVE_WITHIN_THREE_DAYS = "3 日内活跃"  # 页面原始值 3日内活跃 的规范展示值


class FilterPolicy(BaseModel):
    """FilterPolicy（固定筛选策略）保存用户确认并参与方案哈希的不可变岗位准入规则。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    employment_type: Literal["full_time"] = "full_time"  # 只采集全职岗位
    allowed_recruiter_activity: tuple[RecruiterActivity, ...] = (
        RecruiterActivity.JUST_ACTIVE,
        RecruiterActivity.ACTIVE_TODAY,
        RecruiterActivity.ACTIVE_WITHIN_THREE_DAYS,
    )  # 允许进入样本的招聘者活跃度
    require_bounded_monthly_salary: Literal[True] = True  # 要求月薪上下限均可解析
    max_jobs_per_company: Literal[5] = 5  # 单方向同一公司最多保留五个岗位
    use_posted_date_filter: Literal[False] = False  # 不使用岗位发布日期过滤

    @model_validator(mode="after")
    def validate_fixed_recruiter_activity(self) -> FilterPolicy:
        """校验招聘者活跃度集合与用户确认的固定筛选规则完全一致。"""
        expected = (
            RecruiterActivity.JUST_ACTIVE,
            RecruiterActivity.ACTIVE_TODAY,
            RecruiterActivity.ACTIVE_WITHIN_THREE_DAYS,
        )
        if self.allowed_recruiter_activity != expected:
            raise ValueError("allowed_recruiter_activity must match the fixed policy")
        return self


class DirectionProposal(BaseModel):
    """DirectionProposal（方向提案）保存市场 Worker 建议但尚未补齐默认值的搜索条件。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    direction_name: str = Field(min_length=1)  # 用户看到的职业方向名称
    boss_keywords: KeywordTuple  # BOSS 搜索词，数量为一到三个
    trends_keywords: KeywordTuple  # 搜索关注度近义词，数量为一到三个
    cities: ProposalCityTuple = ()  # 用户指定城市顺序；空元组表示由 Store 补默认城市
    experience_basis: Literal["total", "related"]  # 使用总工作年限或目标方向相关年限
    experience_min: int = Field(ge=0, le=60)  # 重点工作年限下限，单位为年
    experience_max: int = Field(ge=0, le=60)  # 重点工作年限上限，单位为年

    @model_validator(mode="after")
    def validate_experience_range(self) -> DirectionProposal:
        """校验工作年限下限不能大于上限。"""
        if self.experience_min > self.experience_max:
            raise ValueError("experience_min must not exceed experience_max")
        return self


class DirectionPlan(BaseModel):
    """DirectionPlan（方向方案）保存一个职业方向的冻结搜索条件。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    direction_name: str = Field(min_length=1)  # 用户看到的职业方向名称
    direction_key: str = Field(min_length=1)  # 用于跨 Session 查找复用候选的规范化方向键
    boss_keywords: KeywordTuple  # BOSS 搜索词，数量为一到三个
    trends_keywords: KeywordTuple  # 搜索关注度近义词，数量为一到三个
    cities: CityTuple  # 实际搜索城市及严格执行顺序，数量为一到四个
    experience_basis: Literal["total", "related"]  # 使用总工作年限或目标方向相关年限
    experience_min: int = Field(ge=0, le=60)  # 重点工作年限下限，单位为年
    experience_max: int = Field(ge=0, le=60)  # 重点工作年限上限，单位为年

    @model_validator(mode="after")
    def validate_experience_range(self) -> DirectionPlan:
        """校验工作年限下限不能大于上限。"""
        if self.experience_min > self.experience_max:
            raise ValueError("experience_min must not exceed experience_max")
        return self


class ResearchPlan(BaseModel):
    """ResearchPlan（调研方案）保存用户确认后不可修改的完整调研输入。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1  # 方案结构版本
    plan_id: str = Field(pattern=r"^plan_[0-9a-f]+$")  # 方案唯一标识
    plan_version: int = Field(ge=1)  # 同一方案每次修改后的递增版本
    status: Literal["draft", "confirmed", "consumed"]  # 方案生命周期状态
    directions: Annotated[tuple[DirectionPlan, ...], Field(min_length=1, max_length=3)]  # 顺序执行的一到三个职业方向
    filter_policy: FilterPolicy  # 用户预览并确认的固定岗位筛选策略
    budget_seconds: Literal[600] = 600  # 每个方向网页与提取 LLM 共用的秒数预算
    source_session_id: str = Field(pattern=r"^sess_[0-9a-f]{32}$")  # 产生和确认方案的 Session
    generated_at: datetime  # 方案首次生成时间
    confirmed_at: datetime | None = None  # 用户最后一次明确确认时间
    plan_hash: str = Field(default="", pattern=r"^(|[0-9a-f]{64})$")  # 规范化方案内容的 SHA-256 摘要


class MarketResearchErrorPayload(BaseModel):
    """MarketResearchErrorPayload（市场错误载荷）保存可持久化和可返回给 API 的结构化错误。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    error_category: str  # 错误所属的大类
    error_code: str  # 供程序分支判断的具体机器码
    user_action: str  # 用户可以采取的下一步操作
    stage: str | None = None  # 发生错误时的调研阶段


class ResearchSnapshot(BaseModel):
    """ResearchSnapshot（调研快照）保存状态卡恢复所需的最小运行状态。"""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1  # 快照结构版本
    research_id: str = Field(pattern=r"^research_[0-9a-f]+$")  # 主调研任务唯一标识
    plan_id: str = Field(pattern=r"^plan_[0-9a-f]+$")  # 本次运行消费的冻结方案标识
    origin_session_id: str = Field(pattern=r"^sess_[0-9a-f]{32}$")  # 最初发起任务并接收报告的 Session
    status: ResearchStatus  # 主任务当前生命周期状态
    stage: ResearchStage  # 后台线程当前执行阶段
    direction_run_id: str | None = None  # 当前职业方向运行标识
    direction_name: str | None = None  # 当前职业方向显示名称
    keyword: str | None = None  # 当前正在处理的搜索词
    city: str | None = None  # 当前正在处理的城市
    candidate_count: int = Field(default=0, ge=0)  # 当前已看到的候选岗位数
    valid_job_count: int = Field(default=0, ge=0)  # 当前采集有效岗位数
    semantic_analyzed_count: int = Field(default=0, ge=0)  # 当前语义校验有效岗位数
    elapsed_seconds: float = Field(default=0.0, ge=0)  # 排除人工等待后的有效耗时秒数
    available_actions: tuple[Literal["continue", "cancel"], ...] = ()  # 当前状态允许用户执行的控制操作
    error: MarketResearchErrorPayload | None = None  # 当前终态或暂停原因对应的结构化错误
    created_at: datetime  # 主任务创建时间
    updated_at: datetime  # 快照最后更新时间
    completion_published_at: datetime | None = None  # 完成报告写入聊天的时间


class JobSemanticItem(BaseModel):
    """JobSemanticItem（岗位语义项）保存 LLM 提取并通过原文依据校验的一条结构化结论。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    label: str = Field(min_length=1)  # 规范化后的职责、要求、优先条件或岗位证据文本
    category: str | None = None  # 可选的语义分类名称


class CollectedJob(BaseModel):
    """CollectedJob（清洗岗位）保存确定性元数据和经校验的 LLM 结构化结果，不保存原始 JD。"""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1  # 岗位结构版本
    job_id: str | None = None  # BOSS 提供的稳定岗位编号
    fingerprint: str | None = None  # 无稳定编号时由确定性字段计算的岗位指纹
    job_url: str = Field(min_length=1)  # 通过官方域名校验的岗位详情 URL
    title: str = Field(min_length=1)  # 岗位标题
    matched_keywords: tuple[str, ...]  # 命中过该岗位的 BOSS 搜索词
    city: str = Field(min_length=1)  # 岗位所在城市，不包含区县或详细地点
    experience_raw: str | None = None  # 页面显示的经验要求原值
    experience_group: str  # 程序标准化后的经验分组
    education_raw: str | None = None  # 页面显示的学历要求原值
    education_group: str  # 程序标准化后的学历分组
    salary_min: int = Field(gt=0)  # 解析后的税前人民币月薪下限，单位为元
    salary_max: int = Field(gt=0)  # 解析后的税前人民币月薪上限，单位为元
    recruiter_activity: RecruiterActivity  # 规范化后的招聘者活跃度
    company_id: str | None = None  # BOSS 提供的公司唯一标识
    company_name: str = Field(min_length=1)  # 公司名称
    company_industry: str | None = None  # 公司所属行业
    company_size: str | None = None  # 页面显示或程序标准化后的公司规模
    collected_at: datetime  # 岗位详情采集时间
    collection_valid: Literal[True] = True  # 岗位已通过确定性采集准入规则
    semantic_valid: bool = False  # 岗位的 LLM 输出是否通过结构与原文依据校验
    responsibilities: tuple[JobSemanticItem, ...] = ()  # 经校验的 LLM 职责提取结果
    requirements: tuple[JobSemanticItem, ...] = ()  # 经校验的 LLM 任职要求提取结果
    preferences: tuple[JobSemanticItem, ...] = ()  # 经校验的 LLM 优先条件提取结果
    evidence_items: tuple[JobSemanticItem, ...] = ()  # 经校验的 LLM 岗位证据主题
    semantic_skills: tuple[str, ...] = ()  # 经校验的 LLM 具体技能候选

    @model_validator(mode="after")
    def validate_persistable_job(self) -> CollectedJob:
        """校验岗位身份、薪资区间和语义字段满足持久化约束。"""
        if not self.job_id and not self.fingerprint:
            raise ValueError("job_id or fingerprint is required")
        if self.salary_max < self.salary_min:
            raise ValueError("salary_max must not be lower than salary_min")
        semantic_fields = (
            self.responsibilities,
            self.requirements,
            self.preferences,
            self.evidence_items,
            self.semantic_skills,
        )
        if not self.semantic_valid and any(semantic_fields):
            raise ValueError("semantic fields require semantic_valid=true")
        return self


class TrendObservation(BaseModel):
    """TrendObservation（搜索关注度观察）保存页面直接显示的窗口比较字段。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    query: str = Field(min_length=1)  # 页面查询使用的搜索词
    geo: Literal["CN"] = "CN"  # 固定为中国地区
    time_range: Literal["past_12_months", "past_3_months"]  # 页面选择的时间窗口
    metric_kind: Literal["visible_period_comparison"] = "visible_period_comparison"  # 页面直接展示的窗口比较口径
    direction: Literal["up", "down", "flat", "unavailable", "no_data"]  # 页面方向或不可用状态
    percentage: float | None = None  # 页面直接显示的变化百分比
    comparison_label: str | None = None  # 页面直接显示的比较口径标签
    page_url: str = Field(min_length=1)  # 采集时通过白名单校验的页面 URL
    fetched_at: datetime  # 页面字段采集时间
    contract_version: str = Field(min_length=1)  # 采集时使用的页面字段契约版本


class JobReference(BaseModel):
    """JobReference（岗位引用）保存报告展示和 Harness 校验所需的最小岗位身份信息。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    job_id: str  # 被主题引用的岗位编号或确定性指纹
    title: str  # 岗位标题
    company_name: str  # 公司名称
    job_url: str  # 通过官方域名校验的岗位 URL


class ThemeSummary(BaseModel):
    """ThemeSummary（主题摘要）保存市场 Worker 归纳的主题及其岗位支持关系。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    theme: str = Field(min_length=1)  # 职责、要求、优先条件或岗位证据主题
    support_job_ids: tuple[str, ...]  # 支持该主题的完整岗位编号集合
    representative_jobs: Annotated[tuple[JobReference, ...], Field(max_length=3)] = ()  # 最多三个用户可见代表岗位


class SkillStatistic(BaseModel):
    """SkillStatistic（技能统计）保存程序确定性计算的技能岗位数与分母。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    canonical_name: str  # 技能规范名称
    aliases: tuple[str, ...] = ()  # 归并到规范名称的技能别名
    mention_job_ids: tuple[str, ...] = ()  # 全部采集有效岗位中的提及岗位编号
    required_job_ids: tuple[str, ...] = ()  # 语义有效岗位中的必需岗位编号
    preferred_job_ids: tuple[str, ...] = ()  # 语义有效岗位中的优先岗位编号
    mention_count: int = Field(ge=0)  # 技能提及岗位数
    required_count: int = Field(ge=0)  # 技能必需岗位数
    preferred_count: int = Field(ge=0)  # 技能优先岗位数
    mention_denominator: int = Field(ge=0)  # 技能提及比例使用的采集有效岗位分母
    semantic_denominator: int = Field(ge=0)  # 必需和优先比例使用的语义有效岗位分母


class SkillTaxonomy(BaseModel):
    """SkillTaxonomy（技能词表）保存本次方向冻结的规范技能、别名、来源和计数。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    direction_key: str  # 技能词表所属职业方向规范键
    skills: tuple[SkillStatistic, ...] = ()  # 至少两个岗位提及的正式技能统计
    emerging_or_isolated: tuple[SkillStatistic, ...] = ()  # 只被一个岗位提及的补充技能统计


class DirectionResultRef(BaseModel):
    """DirectionResultRef（方向结果引用）定位已发布版本中的一个不可变成功方向。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    research_id: str = Field(pattern=r"^research_[0-9a-f]+$")  # 原始市场调研任务编号
    result_version: int = Field(ge=1)  # 原始不可变正式结果版本
    direction_key: str = Field(min_length=1)  # 被引用职业方向的规范键
    direction_run_id: str = Field(pattern=r"^direction_[0-9a-f]+$")  # 产生原方向结果的运行编号


class ReferencedDirectionResult(BaseModel):
    """ReferencedDirectionResult（引用方向结果）在新版本中复用旧成功方向而不复制其数据。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    direction_name: str = Field(min_length=1)  # 被引用职业方向的显示名称
    direction_key: str = Field(min_length=1)  # 被引用职业方向的规范键
    researched_at: datetime  # 原方向完成调研的时间
    expires_at: datetime  # 原方向保持不变的过期时间
    direction_result_ref: DirectionResultRef  # 指向原正式版本中唯一方向的不可变引用

    @model_validator(mode="after")
    def validate_reference_identity(self) -> ReferencedDirectionResult:
        """校验外层方向键与不可变引用中的方向键一致。"""
        if self.direction_key != self.direction_result_ref.direction_key:
            raise ValueError("direction reference key must match direction_key")
        return self


class DirectionResult(BaseModel):
    """DirectionResult（方向结果）保存一个成功职业方向的冻结市场调研结果。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    direction_name: str  # 职业方向显示名称
    direction_key: str  # 职业方向规范键
    direction_run_id: str = Field(pattern=r"^direction_[0-9a-f]+$")  # 产生本结果的方向运行标识
    researched_at: datetime  # 方向完成调研时间
    expires_at: datetime  # 方向停止下游使用的过期时间
    boss_keywords: tuple[str, ...]  # 实际执行的 BOSS 搜索词
    trends_keywords: tuple[str, ...]  # 实际执行的搜索关注度近义词
    visited_cities: tuple[str, ...]  # 实际访问过的城市顺序
    keyword_statuses: dict[str, Literal["completed", "cutoff", "not_run"]]  # 每个 BOSS 搜索词的执行状态
    budget_seconds: int = Field(gt=0)  # 本方向网页与提取 LLM 的预算秒数
    elapsed_seconds: float = Field(ge=0)  # 排除人工等待后的有效耗时秒数
    candidate_count: int = Field(ge=0)  # 页面候选岗位数量
    valid_job_count: int = Field(ge=0)  # 采集有效岗位数量
    deduplicated_job_count: int = Field(ge=0)  # 全局去重和公司上限后的岗位数量
    semantic_analyzed_count: int = Field(ge=0)  # 语义校验有效岗位数量
    company_count: int = Field(ge=0)  # 样本中的不同公司数量
    sample_level: Literal["normal", "limited", "limited_no_reference"]  # 按有效岗位数冻结的样本等级
    career_definition: str | None = None  # 至少三条代表岗位支持的职业定义
    responsibility_themes: tuple[ThemeSummary, ...] = ()  # 职责主题及岗位支持关系
    requirement_themes: tuple[ThemeSummary, ...] = ()  # 任职要求主题及岗位支持关系
    preference_themes: tuple[ThemeSummary, ...] = ()  # 优先条件主题及岗位支持关系
    evidence_themes: tuple[ThemeSummary, ...] = ()  # 岗位证据主题及岗位支持关系
    skill_statistics: tuple[SkillStatistic, ...] = ()  # 正式技能统计
    emerging_or_isolated_skills: tuple[SkillStatistic, ...] = ()  # 单岗位技能补充区
    experience_analysis: dict[str, Any]  # 程序生成的经验分布和重点档位
    education_distribution: dict[str, int]  # 程序生成的学历分布
    salary_analysis: dict[str, Any]  # 程序生成的薪资中位数和观察区间
    industry_distribution: dict[str, int]  # 程序生成的行业分布
    company_size_distribution: dict[str, int]  # 程序生成的公司规模分布
    trend_observations: tuple[TrendObservation, ...] = ()  # 两个时间窗口的页面比较字段
    sample_limitations: tuple[str, ...] = ()  # 默认排序、个性化和小样本等限制
    representative_jobs: tuple[JobReference, ...] = ()  # 方向级代表岗位
    audit_refs: tuple[str, ...] = ()  # 正式截图和结构化审计文件引用


class FailedDirection(BaseModel):
    """FailedDirection（失败方向）保存未进入正式结果方向的最小错误信息。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    direction_name: str  # 失败职业方向显示名称
    direction_key: str  # 失败职业方向规范键
    error: MarketResearchErrorPayload  # 失败阶段、错误码和用户动作


class MarketComparison(BaseModel):
    """MarketComparison（方向对照）保存不含排名、评分或推荐的并列说明。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    summary: str  # 多方向已验证字段的并列对照文本
    direction_keys: tuple[str, ...]  # 参与对照的成功方向规范键


class MarketResearchResult(BaseModel):
    """MarketResearchResult（市场调研结果）保存一次调研原子发布的版本化顶层结果。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1  # 正式结果结构版本
    research_id: str = Field(pattern=r"^research_[0-9a-f]+$")  # 主调研任务唯一标识
    plan_id: str = Field(pattern=r"^plan_[0-9a-f]+$")  # 本次调研消费的冻结方案标识
    result_version: int = Field(ge=1)  # 不可变正式结果版本号
    origin_session_id: str = Field(pattern=r"^sess_[0-9a-f]{32}$")  # 最初发起调研的 Session
    status: Literal["completed", "partial_completed"]  # 正式结果对应的成功状态
    researched_at: datetime  # 正式结果完成时间
    expires_at: datetime  # 成功方向中最早的过期时间
    successful_directions: tuple[DirectionResult | ReferencedDirectionResult, ...]  # 新成功方向或旧版本方向引用
    failed_directions: tuple[FailedDirection, ...] = ()  # 未成功职业方向的最小错误信息
    comparison: MarketComparison | None = None  # 至少两个方向成功时的并列对照
    source_boundaries: tuple[str, ...]  # 数据来源、口径和禁止推断边界
    audit_refs: tuple[str, ...] = ()  # 正式结果、岗位、技能和截图清单引用

    @model_validator(mode="after")
    def validate_successful_directions(self) -> MarketResearchResult:
        """校验正式结果至少包含一个成功职业方向且方向键不重复。"""
        if not self.successful_directions:
            raise ValueError("at least one successful direction is required")
        direction_keys = [direction.direction_key for direction in self.successful_directions]
        if len(direction_keys) != len(set(direction_keys)):
            raise ValueError("successful direction keys must be unique")
        return self


class MarketSynthesisOutput(BaseModel):
    """MarketSynthesisOutput（市场综合输出）保存无工具 Worker 生成、等待 Harness 校验的语义结构。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    career_definition: str | None = None  # Worker 生成的职业定义候选
    career_definition_job_ids: tuple[str, ...] = ()  # 支持职业定义的岗位编号
    responsibility_themes: tuple[ThemeSummary, ...] = ()  # Worker 归纳的职责主题
    requirement_themes: tuple[ThemeSummary, ...] = ()  # Worker 归纳的任职要求主题
    preference_themes: tuple[ThemeSummary, ...] = ()  # Worker 归纳的优先条件主题
    evidence_themes: tuple[ThemeSummary, ...] = ()  # Worker 归纳的岗位证据主题
    skill_explanations: dict[str, str] = Field(default_factory=dict)  # 对冻结技能统计的文字解释
    salary_explanation: str | None = None  # 对冻结薪资统计的文字说明
    trend_explanation: str | None = None  # 对搜索关注度边界内结果的文字说明


class ResultRef(BaseModel):
    """ResultRef（结果引用）保存 Session 指向本次新调研不可变版本的最小定位信息。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    research_id: str = Field(pattern=r"^research_[0-9a-f]+$")  # 被引用的主调研标识
    result_version: int = Field(ge=1)  # 被引用的不可变结果版本


class ScreenshotManifestItem(BaseModel):
    """ScreenshotManifestItem（截图清单项）保存一张正式抽样截图的完整性信息。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    screenshot_ref: str = Field(pattern=r"^screenshots/[0-9A-Za-z._/-]+$")  # 正式版本目录内的受控相对引用
    direction_run_id: str = Field(pattern=r"^direction_[0-9a-f]+$")  # 截图所属方向运行编号
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")  # 截图文件内容的 SHA-256 摘要
    size_bytes: int = Field(ge=1)  # 截图文件字节数


class ScreenshotManifest(BaseModel):
    """ScreenshotManifest（截图清单）冻结一个正式结果版本的 10% 抽样截图集合。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1  # 截图清单结构版本
    research_id: str = Field(pattern=r"^research_[0-9a-f]+$")  # 截图所属市场调研任务编号
    result_version: int = Field(ge=1)  # 截图所属不可变结果版本
    screenshots: tuple[ScreenshotManifestItem, ...] = ()  # 通过正式版本路径可读取的抽样截图
