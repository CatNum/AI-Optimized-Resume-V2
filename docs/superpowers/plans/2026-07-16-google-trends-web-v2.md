# Google Trends Web v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用当前 Google Trends 页面中的周度 0～100 归一化序列替换旧比较卡片模型，确定性计算半年和逐月变化，并让 Trends 技术失败降级后继续 BOSS 调研。

**Architecture:** `GoogleTrendsCollector`（Google Trends 采集器）每个职业方向只构造一个多关键词过去 12 个月查询，受控重试始终复用该查询；版本化页面契约读取趋势组件内的无障碍表格，并按表头语义把每个数据列唯一绑定到冻结关键词。独立 `trend_analysis` 模块只接收结构化周点，是年度、月度、排序和方向概括的唯一生产者。`TrendResearchResult`（趋势调研结果）作为单一 v2 契约贯穿运行上下文、综合、Store、Harness 和纯文本报告，旧 `TrendObservation` 双窗口百分比模型直接删除。

**Tech Stack:** Python 3.11、Pydantic 2、DrissionPage 4.1.1.4、pytest、本地 JSON 结果存储

**Design SSOT:** `../specs/2026-07-16-google-trends-web-v2-design.md`

## Global Constraints

- 页面契约版本固定为 `google_trends_web_v2`；不读取、不迁移、不兼容旧 `visible_period_comparison` 结果。
- 每个职业方向只构造一个过去 12 个月查询；同页关键词数量为 1～3，`geo=CN`，`hl=zh-CN`。验证恢复或技术重试允许重新导航，但查询参数必须完全相同。
- 唯一数据读取面是“热度随时间变化的趋势”组件内部无障碍表格；禁止内部 API、CSV、SVG/Canvas、OCR、截图解析和完整 DOM/HTML 持久化。
- 年度只使用最近 52 周，前 26 周为前半年、后 26 周为后半年；超过 52 周时丢弃最早边界点，不足 52 周时年度结论为数据不足。
- 最近三个月只使用最近三个完整自然月；按周起始日期归月，每月至少 3 个有效周点；以 UTC 日期识别的当前未完成月只可作为“截至当前”参考。
- 0 是有效数据；空单元格、非数值或缺失列才是缺失数据。0 不等于绝对零次搜索，低搜索量查询可能显示为 0，结果可能包含抽样和随机噪声。
- 变化值为后期均值减前期均值，单位固定为“归一化热度点”；`>= +10` 上升、`<= -10` 下降，其余基本持平，展示保留一位小数且不得添加百分号。
- 首次页面状态等待最多 5 秒，约每 0.25 秒轮询；未就绪时只刷新一次，再等待最多 5 秒，然后以 `render_timeout` 降级。
- 明确验证页进入 `waiting_user`；普通登录按钮不阻断；明确 429 固定等待 10 秒后只重试一次。通用技术错误固定等待 5 秒并重新导航一次，不占用限流退避档位；两类重试耗尽后 Trends 均降级并继续 BOSS。
- `page_changed` 只表示趋势组件已渲染但表格结构不可解析；不得用它表示单纯未渲染。
- 只保存周度结构化序列和结构化诊断；不得保存失败截图、HTML、DOM、Cookie、账号标识、验证码或页面正文。
- 页面适配器必须依据每个数据列表头唯一绑定冻结关键词；部分表头可识别时形成 `partial`，不得按列数或位置猜测映射。
- `analyze_trend_series()` 是派生统计唯一生产者；Store 只做结构、归属和状态校验，不重新执行或比对计算结果。
- 传给市场 Worker 和 Harness 下游的 `trend_result` 必须剔除 `diagnostic`；完整诊断只进入正式审计结构和固定安全来源文案。
- 真实 Google 页面只做人工冒烟，不进入默认 CI；自动化测试使用脱敏 v2 fixture 和可控时钟。
- 所有新增字段、类型和函数必须通过中文注释或 docstring 解释含义与作用。
- 每个 Task 的建议 commit 使用中文 conventional commit 主信息，并包含至少两个具体分点。

---

## File Structure and Responsibilities

### 新增文件

```text
backend/career_os/platform/market_research/trend_analysis.py
    # 纯函数计算 52 周半年均值、完整自然月、变化方向、多数结论和相对热度排序

backend/tests/fixtures/google_trends_web_v2.py
    # 生成脱敏的 53 周、最多三序列无障碍表格 fixture，不包含真实页面源码

backend/tests/platform/test_market_research_trend_analysis.py
    # 覆盖所有年度、月度、阈值、多数结论和排序边界

backend/tests/platform/market_research_test_data.py
    # 集中构造 v2 TrendSeries、TrendResearchResult、DirectionResult 和顶层结果，避免测试各自发明字段

backend/tests/__init__.py
    # 让 tests.platform.market_research_test_data 以稳定模块路径被 platform 与 harness 测试共享

backend/tests/platform/test_market_research_runner_trends.py
    # 证明 Trends 降级后 Runner 仍调用 BOSS 阶段

backend/tests/platform/test_market_research_synthesis_trends.py
    # 证明市场 Worker 输入保留确定性趋势结果但剔除内部 diagnostic

backend/tests/platform/test_market_research_store_trends.py
    # 覆盖正式结果中的 v2 契约和旧模型拒绝规则

backend/tests/platform/test_market_research_renderer.py
    # 覆盖变化值、长期/近期解释、排序、边界声明和降级文案

backend/tests/harness/test_market_research_result_trends.py
    # 覆盖正式 v2 趋势结果进入下游精简上下文且不泄漏诊断隐私
```

### 修改文件

- `backend/career_os/platform/market_research/models.py`：删除旧 `TrendObservation`，定义周点、诊断、分析、排序和顶层 v2 趋势结果。
- `backend/career_os/platform/market_research/errors.py`：加入稳定的 `render_timeout` 和 Trends 降级错误语义。
- `backend/career_os/platform/market_research/page_contracts.py`：把 Trends v1 比较卡片契约替换为 v2 页面状态和趋势表格契约。
- `backend/career_os/platform/market_research/trends.py`：改为单查询多关键词导航、5 秒状态机、一次刷新、按表头绑定列、区分限流与通用技术错误并返回可降级结果。
- `backend/career_os/platform/market_research/runner.py`：运行上下文只记录一个 `TrendResearchResult`。
- `backend/career_os/platform/market_research/service.py`：组装刷新、人工验证、导航和 v2 Collector，并保持单标签页。
- `backend/career_os/platform/market_research/synthesis.py`：把 v2 确定性结果交给只读综合，并合并进 `DirectionResult`。
- `backend/career_os/platform/market_research/renderer.py`：展示半年、逐月变化、长期/近期信号、相对排序和降级状态。
- `backend/career_os/platform/market_research/store.py`：发布前交叉校验 v2 关键词、周点、数值范围和契约版本。
- `backend/career_os/platform/market_research/__init__.py`：导出新的公共趋势类型，移除旧类型。
- `backend/career_os/harness/market_research_result.py`：下游白名单改为 `trend_result`，保留结构化统计并剔除内部诊断。
- `backend/career_os/platform/prompt/market_research/direction_system.md`：约束 Worker 只解释冻结趋势，不复制或改写变化数字。
- `backend/tests/platform/test_market_research_page_contracts.py`：替换比较卡片断言，覆盖 v2 URL、页面状态和表格定位。
- `backend/tests/platform/test_market_research_trends.py`：替换双窗口测试，覆盖单查询采集、轮询、刷新、验证、429、通用技术错误和按表头解析。

---

### Task 1: 用 v2 数据契约替换旧趋势观察模型

**Files:**
- Modify: `backend/career_os/platform/market_research/models.py:272-288`
- Modify: `backend/career_os/platform/market_research/models.py:424-465`
- Modify: `backend/career_os/platform/market_research/errors.py:8-84`
- Modify: `backend/career_os/platform/market_research/__init__.py:1-42`
- Test: `backend/tests/platform/test_market_research_trend_analysis.py`
- Create: `backend/tests/platform/market_research_test_data.py`
- Create: `backend/tests/__init__.py`

**Interfaces:**
- Consumes: 冻结 `DirectionPlan.trends_keywords`，数量为一至三个。
- Produces: `TrendSeries`（原始趋势序列）、`TrendResearchResult`（包含确定性分析的正式趋势结果）和 `TrendDiagnostic`（无页面正文的结构化诊断）。

- [ ] **Step 1: 写旧模型必须被拒绝的失败测试**

创建 `backend/tests/platform/test_market_research_trend_analysis.py`，先锁定 v2 顶层类型及旧字段拒绝行为：

```python
from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from career_os.platform.market_research.models import TrendResearchResult


def test_v2_result_rejects_old_visible_comparison_fields() -> None:
    """v2 正式结果不再接受双窗口百分比比较卡片。"""
    with pytest.raises(ValidationError):
        TrendResearchResult.model_validate(
            {
                "contract_version": "google_trends_web_v2",
                "query": "LLM Agent",
                "time_range": "past_12_months",
                "metric_kind": "visible_period_comparison",
                "percentage": 110,
                "comparison_label": "飙升",
            }
        )
```

- [ ] **Step 2: 运行失败测试确认类型尚不存在**

Run:

```bash
cd backend && uv run pytest tests/platform/test_market_research_trend_analysis.py::test_v2_result_rejects_old_visible_comparison_fields -v
```

Expected: FAIL，导入 `TrendResearchResult` 失败。

- [ ] **Step 3: 定义 v2 Pydantic 契约**

在 `models.py` 删除 `TrendObservation`，加入以下类型。每个模型使用 `ConfigDict(extra="forbid", frozen=True)`；数值字段用 `Field(ge=0, le=100)` 约束：

```python
TrendDirection = Literal["up", "down", "flat", "insufficient_data"]
TrendSourceStatus = Literal["success", "partial", "no_data", "degraded"]


class WeeklyTrendPoint(BaseModel):
    """WeeklyTrendPoint（周度趋势点）保存周起始日期和按关键词命名的归一化热度。"""
    model_config = ConfigDict(extra="forbid", frozen=True)

    week_start: date  # Google Trends 表格中该周的起始日期
    values: dict[str, Annotated[float, Field(ge=0, le=100)]]  # 关键词到 0～100 热度的映射；0 是有效值


class TrendPeriodAverage(BaseModel):
    """TrendPeriodAverage（趋势期间均值）保存可审计的日期范围、点数和算术平均值。"""
    model_config = ConfigDict(extra="forbid", frozen=True)

    label: str  # 前半年、后半年、YYYY-MM 或截至当前等用户可见标签
    start_date: date | None  # 参与计算的首个周起始日期；无有效点时为空
    end_date: date | None  # 参与计算的最后一个周起始日期；无有效点时为空
    point_count: int = Field(ge=0)  # 参与均值的有效周点数
    mean: Annotated[float, Field(ge=0, le=100)] | None  # 未格式化均值；无有效点时为空
    complete: bool  # 是否满足 26 周或每月三周的正式判断门槛


class TrendChange(BaseModel):
    """TrendChange（趋势变化）保存后期均值减前期均值及其阈值方向。"""
    model_config = ConfigDict(extra="forbid", frozen=True)

    from_label: str  # 变化起点期间标签
    to_label: str  # 变化终点期间标签
    delta_points: float  # 归一化热度点差，不是百分比
    direction: TrendDirection  # 上升、下降、基本持平或数据不足


class KeywordTrendAnalysis(BaseModel):
    """KeywordTrendAnalysis（关键词趋势分析）保存一个关键词的年度和逐月确定性结果。"""
    model_config = ConfigDict(extra="forbid", frozen=True)

    keyword: str = Field(min_length=1)  # 冻结方案中的 Google Trends 关键词
    first_half: TrendPeriodAverage | None  # 最近 52 周前 26 周统计
    second_half: TrendPeriodAverage | None  # 最近 52 周后 26 周统计
    annual_change: TrendChange | None  # 后半年减前半年的年度变化
    recent_months: tuple[TrendPeriodAverage, ...] = ()  # 最近三个完整自然月，含数据不足月份并保持时间升序
    monthly_changes: tuple[TrendChange, ...] = ()  # 两组相邻完整月变化
    current_partial_month: TrendPeriodAverage | None = None  # 当前月截至当前参考值，不参与正式判断


class TrendRankingItem(BaseModel):
    """TrendRankingItem（相对热度排序项）保存同页关键词的均值和名次。"""
    model_config = ConfigDict(extra="forbid", frozen=True)

    keyword: str = Field(min_length=1)  # 被排序的同页关键词
    mean: float = Field(ge=0, le=100)  # 同一比较尺度下的期间均值
    rank: int = Field(ge=1)  # 按均值降序得到的名次


class TrendDiagnostic(BaseModel):
    """TrendDiagnostic（趋势诊断）只保存预定义结构，不保存页面正文或截图。"""
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: Literal["google_trends_web_v2"] = "google_trends_web_v2"
    failed_field: str | None = None  # 无法识别或校验的稳定业务字段
    page_state: str  # render_timeout、page_changed、rate_limited、transient_error 或 no_data 等状态
    attempt: Literal[1, 2]  # 首次加载或刷新后的第二次加载
    matched_markers: tuple[str, ...] = ()  # 预定义状态标记名，不含页面原文
    expected_keyword_count: int = Field(ge=1, le=3)
    actual_series_count: int = Field(ge=0, le=3)


class TrendSeries(BaseModel):
    """TrendSeries（趋势原始序列）保存同页共同时间轴和必要来源元数据。"""
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: Literal["google_trends_web_v2"] = "google_trends_web_v2"
    geo: Literal["CN"] = "CN"
    locale: Literal["zh-CN"] = "zh-CN"
    page_url: str = Field(min_length=1)
    fetched_at: datetime
    keywords: Annotated[tuple[str, ...], Field(min_length=1, max_length=3)]
    weekly_points: tuple[WeeklyTrendPoint, ...] = ()


class TrendResearchResult(BaseModel):
    """TrendResearchResult（趋势调研结果）贯穿采集、统计、存储和报告的 v2 唯一契约。"""
    model_config = ConfigDict(extra="forbid", frozen=True)

    series: TrendSeries  # 成功或部分成功时可复算的周度序列
    source_status: TrendSourceStatus  # 成功、部分数据、无数据或技术降级
    keyword_analyses: tuple[KeywordTrendAnalysis, ...] = ()
    direction_summary: Literal["up", "down", "flat", "divergent", "insufficient_data"]
    annual_ranking: tuple[TrendRankingItem, ...] = ()
    recent_ranking: tuple[TrendRankingItem, ...] = ()
    diagnostic: TrendDiagnostic | None = None
```

给 `TrendSeries` 和 `TrendResearchResult` 增加模型校验器：周日期严格升序且不重复；每个 `values` 键必须属于 `keywords`；分析关键词不得超出 `keywords`；成功结果不得携带诊断；部分数据、无数据或降级结果必须携带诊断。模型只校验结构与来源状态，不重新执行派生计算。

把 `DirectionResult.trend_observations` 替换为必填 `trend_result: TrendResearchResult`，确保 Trends 降级时也有显式来源状态，而不是空元组。

- [ ] **Step 4: 创建跨测试共享的 v2 构造器**

在 `backend/tests/platform/market_research_test_data.py` 写入完整、无网络依赖的对象工厂：

```python
from datetime import UTC, date, datetime, timedelta

from career_os.platform.market_research.models import (
    DirectionResult,
    MarketResearchResult,
    TrendDiagnostic,
    TrendResearchResult,
    TrendSeries,
    WeeklyTrendPoint,
)
from career_os.platform.market_research.trend_analysis import analyze_trend_series


def successful_trend_result(
    keywords: tuple[str, ...] = ("LLM Agent",),
) -> TrendResearchResult:
    """构造最近 52 周前半段 20、后半段 35 的成功 v2 结果。"""
    start = date(2025, 7, 14)
    series = TrendSeries(
        page_url="https://trends.google.com/trends/explore?geo=CN&hl=zh-CN",
        fetched_at=datetime(2026, 7, 16, tzinfo=UTC),
        keywords=keywords,
        weekly_points=tuple(
            WeeklyTrendPoint(
                week_start=start + timedelta(days=index * 7),
                values={
                    keyword: (20.0 + position * 5.0 if index < 26 else 35.0 + position * 5.0)
                    for position, keyword in enumerate(keywords)
                },
            )
            for index in range(52)
        ),
    )
    return analyze_trend_series(series, as_of_date=date(2026, 7, 16))


def degraded_trend_result(page_state: str = "render_timeout") -> TrendResearchResult:
    """构造不含页面正文、只有结构化诊断的降级结果。"""
    series = TrendSeries(
        page_url="https://trends.google.com/trends/explore?geo=CN&hl=zh-CN",
        fetched_at=datetime(2026, 7, 16, tzinfo=UTC),
        keywords=("LLM Agent",),
        weekly_points=(),
    )
    return TrendResearchResult(
        series=series,
        source_status="degraded",
        keyword_analyses=(),
        direction_summary="insufficient_data",
        diagnostic=TrendDiagnostic(
            page_state=page_state,
            attempt=2,
            expected_keyword_count=1,
            actual_series_count=0,
        ),
    )


def direction_result(trend_result: TrendResearchResult) -> DirectionResult:
    """构造渲染、Store 和 Harness 测试共享的最小完整方向结果。"""
    return DirectionResult(
        direction_name="LLM Agent 应用开发工程师",
        direction_key="llm agent 应用开发工程师",
        direction_run_id="direction_abc123",
        researched_at=datetime(2026, 7, 16, tzinfo=UTC),
        expires_at=datetime(2027, 1, 16, tzinfo=UTC),
        boss_keywords=("LLM Agent",),
        trends_keywords=trend_result.series.keywords,
        visited_cities=("北京",),
        keyword_statuses={"LLM Agent": "completed"},
        budget_seconds=600,
        elapsed_seconds=60.0,
        candidate_count=10,
        valid_job_count=8,
        deduplicated_job_count=8,
        semantic_analyzed_count=8,
        company_count=6,
        sample_level="limited",
        career_definition=None,
        responsibility_themes=(),
        requirement_themes=(),
        preference_themes=(),
        evidence_themes=(),
        skill_statistics=(),
        emerging_or_isolated_skills=(),
        skill_explanations={},
        experience_analysis={},
        education_distribution={},
        salary_analysis={},
        salary_explanation=None,
        industry_distribution={},
        company_size_distribution={},
        trend_result=trend_result,
        trend_explanation="以上是搜索关注度，不代表招聘趋势。",
        sample_limitations=(),
        representative_jobs=(),
        audit_refs=(),
    )


def market_result(trend_result: TrendResearchResult) -> MarketResearchResult:
    """构造只含一个成功方向的顶层市场结果。"""
    direction = direction_result(trend_result)
    return MarketResearchResult(
        schema_version=1,
        research_id="research_abc123",
        plan_id="plan_abc123",
        result_version=1,
        origin_session_id="sess_00000000000000000000000000000000",
        status="completed",
        researched_at=direction.researched_at,
        expires_at=direction.expires_at,
        successful_directions=(direction,),
        failed_directions=(),
        comparison=None,
        source_boundaries=("Google 数据仅表示搜索关注度，不代表招聘趋势。",),
        audit_refs=(),
    )
```

同时创建空的 `backend/tests/__init__.py`，后续统一使用：

```python
from tests.platform.market_research_test_data import (
    degraded_trend_result,
    direction_result,
    market_result,
    successful_trend_result,
)
```

后续测试只通过这些工厂构造正式对象，且成功 fixture 必须使用标准构造函数或 `model_validate()` 完成全部 Pydantic 校验。只有专门验证 Store 防御性校验的单个测试可以有意识地使用 `model_construct()` 制造模型层通常无法产生的非法对象，并必须在测试名和注释中说明绕过原因。

- [ ] **Step 5: 定义稳定错误码**

在 `errors.py` 删除 `TREND_COMPARISON_UNAVAILABLE`，加入：

```python
RENDER_TIMEOUT = "render_timeout"  # 两次页面状态等待后仍未进入任何终止状态
TREND_RATE_LIMITED = "trends_rate_limited"  # 有明确 429 证据且完成既定退避后仍未恢复
TREND_TRANSIENT_ERROR = "trends_transient_error"  # 通用技术错误完成一次五秒短重试后仍未恢复
```

`RENDER_TIMEOUT` 的用户动作说明重新调研或继续查看岗位结果；`TREND_RATE_LIMITED` 的用户动作说明稍后重试 Trends；`TREND_TRANSIENT_ERROR` 的用户动作说明页面组件暂时不可用。三者都只用于结构化来源诊断，不改变 BOSS 执行授权。

- [ ] **Step 6: 更新公共导出并运行模型测试**

在 `__init__.py` 移除 `TrendObservation`，导出 `WeeklyTrendPoint`、`TrendSeries`、`TrendDiagnostic`、`KeywordTrendAnalysis` 和 `TrendResearchResult`。

Run:

```bash
cd backend && uv run pytest tests/platform/test_market_research_trend_analysis.py -v
```

Expected: PASS，且旧比较卡片输入稳定触发 `ValidationError`。

- [ ] **Step 7: 建议提交**

```text
refactor(trends): 替换搜索关注度数据契约

- 删除双窗口比较卡片和百分比字段
- 定义周度序列、确定性分析与结构化诊断模型
- 约束正式结果只接受 google_trends_web_v2
```

---

### Task 2: 实现年度、逐月、方向概括和排序计算器

**Files:**
- Create: `backend/career_os/platform/market_research/trend_analysis.py`
- Modify: `backend/tests/platform/test_market_research_trend_analysis.py`

**Interfaces:**
- Consumes: `TrendSeries`。
- Produces: `analyze_trend_series(series: TrendSeries, *, as_of_date: date, diagnostic: TrendDiagnostic | None = None) -> TrendResearchResult`；`as_of_date`（统计基准日期）必须使用 UTC 日期。Collector 负责页面解析并在部分成功时传入表头绑定诊断，计算函数只负责根据结构化周点生成派生结果。

- [ ] **Step 1: 写 53 周、0 值和半年变化失败测试**

在测试文件加入固定周点生成器和年度断言：

```python
from datetime import timedelta

from career_os.platform.market_research.models import (
    TrendDiagnostic,
    TrendSeries,
    WeeklyTrendPoint,
)
from career_os.platform.market_research.trend_analysis import analyze_trend_series


def _series(values: list[float], keyword: str = "LLM Agent") -> TrendSeries:
    start = date(2025, 7, 7)
    return TrendSeries(
        page_url="https://trends.google.com/trends/explore?geo=CN",
        fetched_at=datetime(2026, 7, 16, tzinfo=UTC),
        keywords=(keyword,),
        weekly_points=tuple(
            WeeklyTrendPoint(
                week_start=start + timedelta(days=index * 7),
                values={keyword: value},
            )
            for index, value in enumerate(values)
        ),
    )


def _dated_series(rows: list[tuple[date, float]], keyword: str = "LLM Agent") -> TrendSeries:
    """构造按明确日期分布的单关键词序列，供自然月边界测试使用。"""
    return TrendSeries(
        page_url="https://trends.google.com/trends/explore?geo=CN",
        fetched_at=datetime(2026, 7, 16, tzinfo=UTC),
        keywords=(keyword,),
        weekly_points=tuple(
            WeeklyTrendPoint(week_start=week_start, values={keyword: value})
            for week_start, value in rows
        ),
    )


def _calendar_month_series() -> TrendSeries:
    """构造三个完整月和一个当前未完成月。"""
    rows = [
        *((date(2026, 4, day), 20.0) for day in (6, 13, 20)),
        *((date(2026, 5, day), 30.0) for day in (4, 11, 18)),
        *((date(2026, 6, day), 20.0) for day in (1, 8, 15)),
        *((date(2026, 7, day), 80.0) for day in (6, 13)),
    ]
    return _dated_series(rows)


def _two_point_month_series() -> TrendSeries:
    """构造中间月份只有两个周点的近期序列。"""
    rows = [
        *((date(2026, 4, day), 20.0) for day in (6, 13, 20)),
        *((date(2026, 5, day), 30.0) for day in (4, 11)),
        *((date(2026, 6, day), 40.0) for day in (1, 8, 15)),
    ]
    return _dated_series(rows)


def _three_keyword_series(
    *, first_delta: float, second_delta: float, third_delta: float
) -> TrendSeries:
    """构造三个关键词各 52 周且年度方向可控的共同尺度序列。"""
    keywords = ("LLM Agent", "AI Agent", "Agent 开发")
    starts = (50.0, 40.0, 40.0)
    deltas = (first_delta, second_delta, third_delta)
    start_date = date(2025, 7, 14)
    return TrendSeries(
        page_url="https://trends.google.com/trends/explore?geo=CN",
        fetched_at=datetime(2026, 7, 16, tzinfo=UTC),
        keywords=keywords,
        weekly_points=tuple(
            WeeklyTrendPoint(
                week_start=start_date + timedelta(days=index * 7),
                values={
                    keyword: starts[position] + (deltas[position] if index >= 26 else 0.0)
                    for position, keyword in enumerate(keywords)
                },
            )
            for index in range(52)
        ),
    )


def _one_valid_keyword_series() -> TrendSeries:
    """构造三个冻结关键词但只有一个关键词存在有效值的部分序列。"""
    series = _three_keyword_series(first_delta=20, second_delta=15, third_delta=-20)
    return series.model_copy(
        update={
            "weekly_points": tuple(
                point.model_copy(update={"values": {"LLM Agent": point.values["LLM Agent"]}})
                for point in series.weekly_points
            )
        }
    )


def test_analysis_drops_oldest_boundary_week_and_includes_zero() -> None:
    result = analyze_trend_series(
        _series([99.0, *([0.0] * 26), *([20.0] * 26)]),
        as_of_date=date(2026, 7, 16),
    )

    analysis = result.keyword_analyses[0]
    assert analysis.first_half is not None
    assert analysis.first_half.mean == 0.0
    assert analysis.second_half is not None
    assert analysis.second_half.mean == 20.0
    assert analysis.annual_change is not None
    assert analysis.annual_change.delta_points == 20.0
    assert analysis.annual_change.direction == "up"
```

- [ ] **Step 2: 写月度完整性和阈值边界失败测试**

加入以下测试，构造跨四个自然月的周点，并把 `today` 固定在第四个月中旬：

```python
def test_recent_months_exclude_current_month_and_require_three_points() -> None:
    result = analyze_trend_series(
        _calendar_month_series(), as_of_date=date(2026, 7, 16)
    )
    analysis = result.keyword_analyses[0]

    assert [month.label for month in analysis.recent_months] == [
        "2026-04", "2026-05", "2026-06"
    ]
    assert analysis.current_partial_month is not None
    assert analysis.current_partial_month.label == "2026-07（截至当前）"
    assert [change.delta_points for change in analysis.monthly_changes] == [10.0, -10.0]
    assert [change.direction for change in analysis.monthly_changes] == ["up", "down"]


def test_month_with_two_weekly_points_is_not_a_formal_month() -> None:
    result = analyze_trend_series(
        _two_point_month_series(), as_of_date=date(2026, 7, 16)
    )
    analysis = result.keyword_analyses[0]

    assert any(month.complete is False for month in analysis.recent_months)
    assert len(analysis.monthly_changes) < 2


def test_current_month_uses_explicit_utc_as_of_date() -> None:
    """统计模块只服从调用方传入的 UTC 基准日期，不读取服务器本地日期。"""
    result = analyze_trend_series(
        _calendar_month_series(), as_of_date=date(2026, 7, 1)
    )

    analysis = result.keyword_analyses[0]
    assert analysis.current_partial_month is not None
    assert analysis.current_partial_month.label == "2026-07（截至当前）"
```

- [ ] **Step 3: 写多数结论和同页排序失败测试**

```python
def test_three_keywords_use_majority_without_building_a_direction_score() -> None:
    result = analyze_trend_series(
        _three_keyword_series(first_delta=20, second_delta=15, third_delta=-20),
        as_of_date=date(2026, 7, 16),
    )

    assert result.direction_summary == "up"
    assert [item.keyword for item in result.annual_ranking] == [
        "LLM Agent", "AI Agent", "Agent 开发"
    ]
    assert [item.rank for item in result.annual_ranking] == [1, 2, 3]


def test_only_one_valid_keyword_is_direction_level_insufficient() -> None:
    series = _one_valid_keyword_series()
    result = analyze_trend_series(
        series,
        as_of_date=date(2026, 7, 16),
        diagnostic=TrendDiagnostic(
            page_state="partial_columns",
            attempt=1,
            expected_keyword_count=3,
            actual_series_count=1,
        ),
    )
    assert result.direction_summary == "insufficient_data"
```

- [ ] **Step 4: 运行测试确认计算器尚不存在**

Run:

```bash
cd backend && uv run pytest tests/platform/test_market_research_trend_analysis.py -v
```

Expected: FAIL，导入 `trend_analysis` 或目标函数失败。

- [ ] **Step 5: 实现纯函数计算器**

在 `trend_analysis.py` 实现并保持无浏览器、Store 或 LLM 依赖：

```python
CHANGE_THRESHOLD = 10.0
ANNUAL_WEEK_COUNT = 52
HALF_YEAR_WEEK_COUNT = 26
MIN_MONTH_WEEK_COUNT = 3


def classify_change(delta_points: float) -> TrendDirection:
    """按正负十个归一化热度点把变化映射为上升、下降或基本持平。"""
    if delta_points >= CHANGE_THRESHOLD:
        return "up"
    if delta_points <= -CHANGE_THRESHOLD:
        return "down"
    return "flat"


def analyze_trend_series(
    series: TrendSeries,
    *,
    as_of_date: date,
    diagnostic: TrendDiagnostic | None = None,
) -> TrendResearchResult:
    """从同页周度序列生成可复算的年度、月度、排序和方向级结果。"""
    analyses = tuple(
        _analyze_keyword(series, keyword=keyword, as_of_date=as_of_date)
        for keyword in series.keywords
    )
    source_status = _source_status(series)
    return TrendResearchResult(
        series=series,
        source_status=source_status,
        keyword_analyses=analyses,
        direction_summary=_majority_direction(analyses),
        annual_ranking=_annual_ranking(analyses),
        recent_ranking=_recent_ranking(analyses),
        diagnostic=diagnostic,
    )
```

同时定义并只在本模块内使用以下精确接口：

```python
def _analyze_keyword(
    series: TrendSeries,
    *,
    keyword: str,
    as_of_date: date,
) -> KeywordTrendAnalysis:
    """按最近 52 周和最近三个完整自然月分析一个冻结关键词。"""


def _source_status(series: TrendSeries) -> TrendSourceStatus:
    """根据冻结关键词是否至少存在一个有效值返回 success、partial 或 no_data。"""


def _majority_direction(
    analyses: tuple[KeywordTrendAnalysis, ...],
) -> Literal["up", "down", "flat", "divergent", "insufficient_data"]:
    """按三词至少两词一致、两词必须全部一致、单词不足的规则生成方向概括。"""


def _annual_ranking(
    analyses: tuple[KeywordTrendAnalysis, ...],
) -> tuple[TrendRankingItem, ...]:
    """按每个关键词最近 52 周均值降序生成稳定全年排名。"""


def _recent_ranking(
    analyses: tuple[KeywordTrendAnalysis, ...],
) -> tuple[TrendRankingItem, ...]:
    """按最近三个数据充分完整月的合并均值降序生成稳定近期排名。"""
```

这些函数必须严格实现：按日期排序；最近 52 周；26/26 分段；按 `week_start` 的年月分组；排除 UTC `as_of_date` 所在月；只看最近三个完整自然月；每月不足三点时 `complete=False`；只为相邻两个完整月份生成 `TrendChange`；相同均值时按冻结关键词顺序稳定排序；只有一个有效关键词不形成方向级结论。`_source_status(series)` 在每个冻结关键词至少有一个有效周值时返回 `success`，部分关键词整列缺失时返回 `partial`，全部无值时返回 `no_data`；年度或月度点数不足只影响对应分析结论，不把来源误判为技术降级。`source_status="success"` 时 `diagnostic` 必须为空；`partial` 或 `no_data` 时必须由调用方传入结构化诊断，否则模型校验拒绝结果。

`analyze_trend_series()` 是所有派生字段的唯一生产者。通过纯函数测试证明 52/53 周、UTC 月份边界、阈值、部分列、多数结论和排序计算正确后，Store 不再复算或逐字段比对这些派生结果。

- [ ] **Step 6: 运行纯函数测试**

Run:

```bash
cd backend && uv run pytest tests/platform/test_market_research_trend_analysis.py -v
```

Expected: PASS，覆盖 52/53 周、0 值、完整月、阈值、冲突、多数结论和排序。

- [ ] **Step 7: 建议提交**

```text
feat(trends): 实现周度趋势确定性计算

- 计算前后半年均值、年度变化和实际日期范围
- 计算最近三个完整自然月及相邻月变化
- 生成多数一致结论和同页相对热度排序
```

---

### Task 3: 建立 v2 页面契约和脱敏无障碍表格 fixture

**Files:**
- Modify: `backend/career_os/platform/market_research/page_contracts.py:186-263`
- Create: `backend/tests/fixtures/google_trends_web_v2.py`
- Modify: `backend/tests/platform/test_market_research_page_contracts.py`

**Interfaces:**
- Consumes: 一至三个冻结关键词和 DrissionPage 页面对象。
- Produces: `TrendsPageContract.build_explore_url(keywords)`、`classify_page_state(page)` 和 `read_interest_table(page)`。

- [ ] **Step 1: 创建脱敏 v2 fixture 构造器**

新增 `backend/tests/fixtures/google_trends_web_v2.py`：

```python
from datetime import date, timedelta


def build_accessible_table(
    keywords: tuple[str, ...] = ("LLM Agent", "AI Agent", "Agent 开发"),
    *,
    present_keywords: tuple[str, ...] | None = None,
    week_count: int = 53,
) -> dict[str, object]:
    """生成表头可绑定冻结关键词、并可缺失指定数据列的脱敏 v2 fixture。"""
    visible = present_keywords if present_keywords is not None else keywords
    if not set(visible).issubset(keywords) or len(visible) != len(set(visible)):
        raise ValueError("present keywords must be a unique subset of requested keywords")
    start = date(2025, 7, 7)
    return {
        "aria_label": "A tabular representation of the data in the chart.",
        "headers": ("时间", *visible),
        "requested_keywords": keywords,
        "rows": tuple(
            (
                (start + timedelta(days=index * 7)).isoformat(),
                *(
                    float((index * (keywords.index(keyword) + 3)) % 101)
                    for keyword in visible
                ),
            )
            for index in range(week_count)
        ),
    }
```

测试 FakeElement 将该结构暴露为 `eles("tag:tr")`、行元素暴露为 `eles("tag:th")` 和 `eles("tag:td")`，模拟 DrissionPage 的最小表格读取行为。表头单元格必须暴露真实关键词文本，禁止使用 `x/y1/y2` 这类无法验证归属的占位表头。

- [ ] **Step 2: 写 URL 和状态分类失败测试**

```python
def test_v2_url_contains_one_multi_keyword_12_month_request() -> None:
    url = TrendsPageContract().build_explore_url(("LLM Agent", "AI Agent"))
    parsed = parse_qs(urlsplit(url).query)

    assert parsed["q"] == ["LLM Agent,AI Agent"]
    assert parsed["date"] == ["today 12-m"]
    assert parsed["geo"] == ["CN"]
    assert parsed["hl"] == ["zh-CN"]


def test_interest_table_is_scoped_to_interest_over_time_widget() -> None:
    page = FakePage.with_accessible_table(build_accessible_table())
    contract = TrendsPageContract()

    assert contract.classify_page_state(page).state == "data_ready"
    assert contract.read_interest_table(page) is page.interest_table
```

保留已有普通登录、可见验证和隐藏 reCAPTCHA 测试；把原“技术重试标记”测试拆为两组：明确 HTTP 429、请求过多或 Too Many Requests 才返回 `rate_limited`，通用“出了点问题/稍后重试”返回 `transient_error`。两组标记不得互相命中。

- [ ] **Step 3: 运行失败测试**

Run:

```bash
cd backend && uv run pytest tests/platform/test_market_research_page_contracts.py -v
```

Expected: FAIL，旧 `build_explore_url()` 仍要求单个 query/time_range，且没有 v2 页面状态接口。

- [ ] **Step 4: 替换 Trends 页面契约**

删除 `geo_filter`、`time_filter`、`comparison_card`、`comparison_direction`、`comparison_percentage` 和 `comparison_label`。新增：

```python
@dataclass(frozen=True)
class TrendsPageState:
    """TrendsPageState（页面状态）保存预定义状态名和命中的安全标记名。"""
    state: Literal[
        "data_ready",
        "no_data",
        "verification_required",
        "rate_limited",
        "transient_error",
        "pending",
    ]
    matched_markers: tuple[str, ...] = ()


@dataclass(frozen=True)
class TrendsPageContract:
    """TrendsPageContract（搜索关注度页面契约）冻结 v2 官方地址、状态和表格读取面。"""
    contract_version: str = "google_trends_web_v2"
    allowed_hosts: frozenset[str] = frozenset({"trends.google.com"})
    explore_url_template: str = "https://trends.google.com/trends/explore"
    interest_over_time_region: PageField = PageField(
        "interest_over_time_region",
        ("css:.fe-line-chart",),
    )
    accessible_data_table: PageField = PageField(
        "accessible_data_table",
        (
            "css:.fe-line-chart div[aria-label^='A tabular representation'] table",
            "css:.fe-line-chart table",
        ),
    )

    def build_explore_url(self, keywords: tuple[str, ...]) -> str:
        """生成一个固定中国、简体中文、过去十二个月的同页比较 URL。"""
        if not 1 <= len(keywords) <= 3:
            raise ValueError("Google Trends requires one to three keywords")
        params = urlencode(
            {"q": ",".join(keywords), "date": "today 12-m", "geo": "CN", "hl": "zh-CN"}
        )
        return f"{self.explore_url_template}?{params}"
```

`classify_page_state()` 的优先级固定为：可见验证、明确 429 限流、通用技术错误、明确无数据、无障碍表格已出现、pending。明确限流标记只接受 HTTP 429、请求过多、Too Many Requests 或等价证据；“糟糕！出了点问题”“请稍后重试”等没有 429 证据的文案只能进入 `transient_error`。趋势组件已经出现但表格尚未出现仍是 `pending`，必须继续等待而不能立即报 `page_changed`。表格出现后由解析器校验行列结构；只有表格本身不可解析时才产生 `rendered_unparseable/page_changed` 诊断。`matched_markers` 只保存如 `verification_marker`、`rate_limit_marker`、`transient_error_marker`、`no_data_marker`、`interest_widget` 的预定义名称。

- [ ] **Step 5: 运行页面契约测试**

Run:

```bash
cd backend && uv run pytest tests/platform/test_market_research_page_contracts.py -v
```

Expected: PASS；旧比较卡片定位器不再出现在测试或契约中。

- [ ] **Step 6: 建议提交**

```text
refactor(trends): 升级 Google Trends 页面契约

- 固定中国简体中文的单页多关键词请求
- 只读取趋势组件内的无障碍数据表格
- 区分验证、限流、无数据、待渲染和结构变化状态
```

---

### Task 4: 重写 Collector 的状态机、表头绑定和技术重试行为

**Files:**
- Modify: `backend/career_os/platform/market_research/trends.py:1-390`
- Modify: `backend/tests/platform/test_market_research_trends.py`

**Interfaces:**
- Consumes: `DirectionPlan`、DrissionPage 页面、`ActiveBudget`、v2 `TrendsPageContract`。
- Produces: `GoogleTrendsCollector.collect(direction, page, budget) -> TrendResearchResult`。

- [ ] **Step 1: 把 FakeClock 扩展为轮询可控时钟**

保留现有 `monotonic()` 和 `sleep()`，并让测试注入 `utc_today=lambda: date(2026, 7, 16)`、`refresh_handler` 和按轮询次数变化的 FakePage。`utc_today`（UTC 当前日期函数）是月度统计基准，生产默认值必须为 `lambda: datetime.now(UTC).date()`，不得使用服务器本地 `date.today()`。所有 5 秒等待都通过 FakeClock 推进，不发生真实等待。

- [ ] **Step 2: 写单次多关键词导航和成功解析失败测试**

```python
def test_collect_navigates_once_and_returns_three_series() -> None:
    page = FakePage.with_accessible_table(build_accessible_table())
    navigated: list[str] = []
    clock = FakeClock()
    collector = GoogleTrendsCollector(
        navigate_handler=navigated.append,
        refresh_handler=page.refresh,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
        utc_today=lambda: date(2026, 7, 16),
    )

    direction = DirectionPlan(
        direction_name="LLM Agent 应用开发工程师",
        direction_key="llm agent 应用开发工程师",
        boss_keywords=("LLM Agent",),
        trends_keywords=("LLM Agent", "AI Agent", "Agent 开发"),
        cities=("北京",),
        experience_basis="related",
        experience_min=3,
        experience_max=5,
    )
    result = collector.collect(
        direction,
        page,
        ActiveBudget(600, monotonic=clock.monotonic),
    )

    assert len(navigated) == 1
    assert result.series.keywords == ("LLM Agent", "AI Agent", "Agent 开发")
    assert len(result.series.weekly_points) == 53
    assert result.source_status == "success"
```

再写参数化部分成功测试，分别从三关键词表格移除首列、中间列和末列。每种情况都必须断言：

- `result.source_status == "partial"`；
- `actual_series_count == 2`；
- 每个周点的 `values` 只包含表头实际声明的两个关键词；
- 未出现关键词的分析结论为 `insufficient_data`；
- 剩余列仍绑定原关键词，禁止按位置向前补位。

再写表头拒绝测试：未知关键词表头、同一关键词重复出现、规范化后同时匹配多个冻结关键词、时间轴表头无法识别，以及任一数据行单元格数量与已验证表头不一致，都必须返回 `rendered_unparseable/page_changed`，不得形成部分成功。

- [ ] **Step 3: 写 5 秒、一次刷新和超时诊断失败测试**

```python
def test_collect_refreshes_once_after_five_seconds_then_degrades() -> None:
    clock = FakeClock()
    page = FakePage.pending()
    collector = GoogleTrendsCollector(
        retry_times=0,
        navigate_handler=lambda url: page.set_url(url),
        refresh_handler=page.refresh,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
        jitter_factor=lambda: 1.0,
        utc_today=lambda: date(2026, 7, 16),
    )

    result = collector.collect(_direction(), page, ActiveBudget(600, monotonic=clock.monotonic))

    assert page.refresh_count == 1
    assert 10.0 <= clock.seconds <= 10.5
    assert result.source_status == "degraded"
    assert result.diagnostic is not None
    assert result.diagnostic.page_state == "render_timeout"
    assert result.diagnostic.attempt == 2
```

再写“首次超时、刷新后成功”测试，断言只刷新一次且返回成功。

- [ ] **Step 4: 改写已有验证、明确 429 与通用技术错误测试期望**

只有 FakePage 提供明确 429、请求过多或 Too Many Requests 标记时，才保留 10/30/60 秒顺序和预算检查；持续限流的最终期望改成降级结果：

```python
result = collector.collect(_direction(), page, ActiveBudget(600, monotonic=clock.monotonic))

assert [seconds for seconds in clock.sleeps if seconds >= 10.0] == [10.0, 30.0, 60.0]
assert result.source_status == "degraded"
assert result.diagnostic is not None
assert result.diagnostic.page_state == "rate_limited"
```

当剩余预算小于下一次退避时，不执行该次 sleep，直接返回 `rate_limited` 降级，保留剩余预算给 BOSS。

另写通用技术错误测试：FakePage 只显示“糟糕！出了点问题”或“请稍后重试”时，Collector 固定等待 5 秒并使用完全相同的 URL 重新导航一次；第二次仍命中则返回 `source_status="degraded"` 和 `diagnostic.page_state="transient_error"`。断言它没有执行 10/30/60 秒等待，也没有消耗 429 退避档位。剩余预算不足 5 秒时不 sleep，直接降级。

普通登录按钮仍不调用人工等待；明确验证标记调用 `user_action_handler`，返回后重新进入页面状态等待。

- [ ] **Step 5: 运行 Collector 测试确认失败**

Run:

```bash
cd backend && uv run pytest tests/platform/test_market_research_trends.py -v
```

Expected: FAIL，旧 Collector 仍发起关键词数乘两个窗口的导航，并读取不存在的比较卡片。

- [ ] **Step 6: 实现表格解析函数**

在 `trends.py` 删除 `_TIME_RANGES`、百分比正则、`_parse_percentage()` 和 `_parse_direction()`，新增：

```python
def parse_weekly_points(
    table: Any,
    keywords: tuple[str, ...],
    *,
    contract: TrendsPageContract,
) -> tuple[WeeklyTrendPoint, ...]:
    """把趋势组件内无障碍表格解析成按日期升序、按关键词命名的周度序列。"""
    rows = table.eles("tag:tr")
    if len(rows) < 2:
        raise PageChangedError(contract.contract_version, "collecting_trends", "weekly_rows")
    header_cells = rows[0].eles("tag:th") or rows[0].eles("tag:td")
    header_texts = tuple(_element_text(cell) for cell in header_cells)
    if len(header_texts) < 2 or not _is_time_axis_header(header_texts[0]):
        raise PageChangedError(contract.contract_version, "collecting_trends", "time_axis_header")
    column_keywords = _bind_keyword_headers(
        header_texts[1:],
        keywords,
        contract=contract,
    )
    points: list[WeeklyTrendPoint] = []
    for row in rows[1:]:
        cells = row.eles("tag:td")
        if len(cells) != len(header_cells):
            raise PageChangedError(contract.contract_version, "collecting_trends", "row_alignment")
        week_start = _parse_week_start(_element_text(cells[0]))
        values = {
            keyword: _parse_normalized_value(_element_text(cells[index]))
            for index, keyword in enumerate(column_keywords, start=1)
            if _element_text(cells[index]).strip() != ""
        }
        points.append(WeeklyTrendPoint(week_start=week_start, values=values))
    return tuple(sorted({point.week_start: point for point in points}.values(), key=lambda item: item.week_start))
```

`_bind_keyword_headers()`（关键词表头绑定函数）必须先对表头执行有限、可审计的规范化：只允许去除首尾空白、合并连续空白和移除页面契约明确列出的固定装饰文本，然后与冻结关键词做精确比较。每个表头必须唯一匹配一个冻结关键词，且同一关键词只能出现一次。未知表头、重复表头或歧义匹配立即抛出 `PageChangedError`；禁止模糊匹配和按位置回退。返回值保持页面实际列顺序，供每一行按已验证表头绑定数值。

请求三个关键词而 `column_keywords` 只包含其中一至两个时属于合法部分成功：周点只保存这些已验证关键词，分析器为缺失关键词生成 `insufficient_data`，最终 `source_status="partial"` 并记录 `expected_keyword_count` 与 `actual_series_count`。只有零个关键词列可绑定或表头结构不可信时才整体降级。

日期和值解析使用明确格式，不把失败原文写入异常：

```python
def _parse_week_start(value: str) -> date:
    """把 ISO、斜杠或简体中文日期转换为周起始日期。"""
    normalized = value.strip()
    for pattern in ("%Y-%m-%d", "%Y/%m/%d", "%Y年%m月%d日", "%Y年%m月%d"):
        try:
            return datetime.strptime(normalized, pattern).date()
        except ValueError:
            continue
    raise ValueError("unparseable_week_start")


def _parse_normalized_value(value: str) -> float:
    """解析 0～100 的归一化热度；空值由调用方作为缺失处理。"""
    parsed = float(value.strip())
    if not 0.0 <= parsed <= 100.0:
        raise ValueError("normalized_value_out_of_range")
    return parsed
```

无法解析的日期、超出 0～100 的数值、时间轴表头错误、关键词表头未知/重复/歧义和数据行错位分别映射为稳定 `failed_field`，不得把表头或单元格原文写入异常或诊断。

- [ ] **Step 7: 实现 5 秒状态等待和一次刷新**

Collector 构造器新增：

```python
refresh_handler: Callable[[], Any] | None = None
monotonic: Callable[[], float] = time.monotonic
poll_interval_seconds: float = 0.25
state_wait_seconds: float = 5.0
utc_today: Callable[[], date] = lambda: datetime.now(UTC).date()
```

实现 `_wait_for_terminal_state(page, budget) -> TrendsPageState | None`：每次循环先检查状态，再按 `min(0.25, deadline-now, budget.remaining_seconds())` 等待；到达 5 秒返回 `None`。`_collect_once()` 首次等待返回 `None` 时只调用一次 refresh，再等待 5 秒；第二次仍为 `None` 时返回带 `render_timeout` 诊断的 `TrendResearchResult`。

无障碍表格已经出现但 `parse_weekly_points()` 抛出 `PageChangedError` 时，转成 `rendered_unparseable/page_changed` 降级。解析成功后先从所有周点的 `values` 键集合计算至少含一个有效数值的关键词集合：若它等于冻结关键词集合，调用 `analyze_trend_series(series, as_of_date=utc_today())`；若它是冻结关键词的非空真子集，则构造 `page_state="partial_columns"`、正确关键词数量和实际有效序列数量的 `TrendDiagnostic`，再通过 `diagnostic=` 传给计算函数。明确 `no_data` 构造 `source_status="no_data"`、空周点和 `no_data` 诊断。明确 429 与 `transient_error` 分别进入 Step 4 定义的独立重试分支。

- [ ] **Step 8: 运行 Collector 与契约测试**

Run:

```bash
cd backend && uv run pytest tests/platform/test_market_research_trends.py tests/platform/test_market_research_page_contracts.py -v
```

Expected: PASS；正常成功路径导航一次，技术重试始终复用同一查询 URL，单次页面状态流程刷新最多一次，测试总耗时不包含真实等待。

- [ ] **Step 9: 建议提交**

```text
feat(trends): 按新版页面采集周度序列

- 实现五秒轮询、一次刷新和终止状态识别
- 解析趋势组件无障碍表格并生成结构化周点
- 保留验证等待与限流退避并将耗尽结果降级
```

---

### Task 5: 让 v2 结果贯穿 Runner、综合和降级执行链

**Files:**
- Modify: `backend/career_os/platform/market_research/runner.py:104-137`
- Modify: `backend/career_os/platform/market_research/service.py:678-766`
- Modify: `backend/career_os/platform/market_research/synthesis.py:40-330`
- Modify: `backend/career_os/platform/prompt/market_research/direction_system.md`
- Create: `backend/tests/platform/test_market_research_runner_trends.py`
- Create: `backend/tests/platform/test_market_research_synthesis_trends.py`

**Interfaces:**
- Consumes: `GoogleTrendsCollector.collect() -> TrendResearchResult`。
- Produces: `DirectionRunContext.record_trend_result(result)` 和包含 `trend_result` 的 `DirectionResult`。

- [ ] **Step 1: 写 Trends 降级仍进入 BOSS 的失败测试**

构造最小 Runner，所有阶段处理器只记录调用顺序；Trends 处理器写入降级结果，BOSS 处理器写入标记。测试从 `models` 导入 `FilterPolicy`（固定筛选策略），并从 `datetime` 导入 `UTC`、`datetime`，确保 `ResearchPlan` 使用标准构造函数通过完整校验：

```python
def test_degraded_trends_does_not_stop_boss_stage() -> None:
    calls: list[ResearchStage] = []

    def trends(context: DirectionRunContext) -> None:
        calls.append(ResearchStage.COLLECTING_TRENDS)
        context.record_trend_result(degraded_trend_result("render_timeout"))

    def boss(context: DirectionRunContext) -> None:
        calls.append(ResearchStage.COLLECTING_BOSS)

    def noop(_context: DirectionRunContext) -> None:
        """让非目标阶段成功返回，隔离 Trends 到 BOSS 的顺序断言。"""

    class RecordingRunner(MarketResearchRunner):
        """绕过 Store 状态写入，只执行真实阶段循环。"""

        def _check_cancelled(self, _research_id: str) -> None:
            return

        def _update_stage(self, *_args: object, **_kwargs: object) -> None:
            return

        def update_progress(self, *_args: object, **_kwargs: object) -> None:
            return

    runner = RecordingRunner(
        store=object(),
        stage_handlers={
            ResearchStage.COLLECTING_TRENDS: trends,
            ResearchStage.COLLECTING_BOSS: boss,
            ResearchStage.EXTRACTING_SEMANTICS: noop,
            ResearchStage.CALCULATING_STATISTICS: noop,
            ResearchStage.SYNTHESIZING: noop,
        },
    )
    direction = DirectionPlan(
        direction_name="LLM Agent 应用开发工程师",
        direction_key="llm agent 应用开发工程师",
        boss_keywords=("LLM Agent",),
        trends_keywords=("LLM Agent",),
        cities=("北京",),
        experience_basis="related",
        experience_min=3,
        experience_max=5,
    )
    plan = ResearchPlan(
        plan_id="plan_abc123",
        plan_version=1,
        status="consumed",
        budget_seconds=600,
        directions=(direction,),
        filter_policy=FilterPolicy(),
        source_session_id="sess_00000000000000000000000000000000",
        generated_at=datetime(2026, 7, 16, tzinfo=UTC),
        confirmed_at=datetime(2026, 7, 16, tzinfo=UTC),
        plan_hash="a" * 64,
    )
    context = DirectionRunContext(
        research_id="research_abc123",
        direction_run_id="direction_abc123",
        plan=plan,
        direction=direction,
        budget=ActiveBudget(600),
    )
    runner._run_direction(context)

    assert calls[:2] == [
        ResearchStage.COLLECTING_TRENDS,
        ResearchStage.COLLECTING_BOSS,
    ]
```

再用同一个 `RecordingRunner` 写一个测试：Trends 处理器抛出 `MarketResearchError(MarketResearchErrorCode.BROWSER_FAILED)`，使用 `pytest.raises` 断言异常原样离开 `_run_direction()` 且 BOSS 调用未发生，证明浏览器硬失败没有被吞掉。

- [ ] **Step 2: 运行 Runner 测试确认失败**

Run:

```bash
cd backend && uv run pytest tests/platform/test_market_research_runner_trends.py -v
```

Expected: FAIL，当前上下文只有 `record_trend_results(observations, summary)`。

- [ ] **Step 3: 替换运行上下文字段**

在 `DirectionRunContext` 中用以下方法替换旧方法：

```python
def record_trend_result(self, result: TrendResearchResult) -> None:
    """记录搜索关注度 v2 原始周点、确定性分析和来源状态。"""
    self.data["trend_result"] = result
```

删除 `trend_observations` 和 `trend_summary` 两个内存键，避免新旧真值并存。

- [ ] **Step 4: 更新 Service 组装**

`service.py` 的 Trends 阶段先取得当前唯一页面并注入刷新回调；刷新仍由该页面所在的 Runner 线程执行，保持单标签页所有权。Collector 返回后直接：

```python
page = direction_context.require_browser_page()
collector = GoogleTrendsCollector(
    contract=contract,
    navigate_handler=lambda url: browser_session.navigate(url, contract.allowed_hosts),
    refresh_handler=lambda: page.refresh(),
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
    page,
    direction_context.budget,
)
direction_context.record_trend_result(trend_result)
```

不得在 Service 中重复计算统计或把 `degraded/no_data/partial` 转成异常。`BROWSER_FAILED`、`STORAGE_FAILED` 和用户取消仍由现有 Runner 终态逻辑处理。

- [ ] **Step 5: 更新综合输入和结果合并**

把 `_ALLOWED_STATISTIC_REFS` 中的 `trend_observations` 替换为 `trend_result`。`_direction_input()`（构造市场 Worker 输入）必须显式剔除内部诊断：

```python
trend_payload = context.data["trend_result"].model_dump(
    mode="json",
    exclude={"diagnostic"},
)
```

只把 `trend_payload` 作为冻结趋势输入。页面正文、`failed_field`（失败字段）、`matched_markers`（命中标记）、`attempt`（页面尝试次数）和其他诊断不得进入 LLM；完整诊断只进入正式审计结构，用户和 LLM 只能看到按 `source_status` 映射的固定安全来源文案。

`_validate_and_merge()` 构造 `DirectionResult` 时使用：

```python
trend_result=TrendResearchResult.model_validate(context.data["trend_result"]),
```

Prompt 把 `trend_explanation` 约束改为：只能解释长期与近期方向是否一致、搜索关注度边界和数据不足；不得复制均值、点差、名次或添加百分号。确定性数值只由 Renderer 输出。

在 `test_market_research_synthesis_trends.py` 直接驱动 `_direction_input()`，使用带 `failed_field`、`matched_markers` 和 `attempt` 的降级结果，断言输出仍包含 `source_status`、`keyword_analyses` 和固定边界状态，但序列化结果中不存在 `diagnostic` 及其任何子字段。

- [ ] **Step 6: 运行 Runner 和纯函数回归**

Run:

```bash
cd backend && uv run pytest \
  tests/platform/test_market_research_runner_trends.py \
  tests/platform/test_market_research_synthesis_trends.py \
  tests/platform/test_market_research_trend_analysis.py -v
```

Expected: PASS；降级结果继续 BOSS，浏览器硬失败仍抛出，内部诊断不进入 LLM 输入。

- [ ] **Step 7: 建议提交**

```text
refactor(market): 接通趋势 v2 运行与综合链路

- 以单一 TrendResearchResult 替换旧观察和摘要内存键
- 让 Trends 来源降级继续执行 BOSS 阶段
- 限制市场 Worker 只解释冻结趋势而不复制数字
```

---

### Task 6: 校验、持久化并向下游安全暴露 v2 结果

**Files:**
- Modify: `backend/career_os/platform/market_research/store.py:717-817`
- Modify: `backend/career_os/harness/market_research_result.py:280-340`
- Create: `backend/tests/platform/test_market_research_store_trends.py`
- Create: `backend/tests/harness/test_market_research_result_trends.py`

**Interfaces:**
- Consumes: 正式 `DirectionResult.trend_result`。
- Produces: Store 可审计 JSON 和 Harness 白名单 `trend_result` 上下文。

- [ ] **Step 1: 写 Store v2 校验失败测试**

```python
def test_store_rejects_keyword_value_not_declared_by_series() -> None:
    original = successful_trend_result()
    result = original.model_copy(
        update={
            "series": original.series.model_copy(
                update={
                    "weekly_points": (
                        WeeklyTrendPoint(
                            week_start=date(2026, 1, 5),
                            values={"unexpected keyword": 50.0},
                        ),
                    )
                }
            )
        }
    )

    with pytest.raises(ValueError, match="trend values must match frozen keywords"):
        MarketResearchStore._validate_trend_result(result, ("LLM Agent",))
```

另外覆盖：契约版本不是 v2、正式关键词与 `DirectionResult.trends_keywords` 不一致、成功状态缺少任一关键词数据、部分状态没有形成真实子集、无数据状态仍携带数值、部分/无数据/降级缺少诊断、诊断序列数量与实际已绑定关键词数不一致，以及 0 值通过。Store 测试只验证这些结构、归属和状态不变量，不重新执行派生计算。

- [ ] **Step 2: 实现 Store 交叉校验**

在 `_validate_inline_direction()` 调用：

```python
self._validate_trend_result(direction.trend_result, direction.trends_keywords)
```

新增：

```python
@staticmethod
def _validate_trend_result(
    result: TrendResearchResult,
    frozen_keywords: tuple[str, ...],
) -> None:
    """校验趋势契约版本、冻结关键词、周点键和来源状态后才允许正式发布。"""
    if result.series.contract_version != "google_trends_web_v2":
        raise ValueError("formal trend result requires google_trends_web_v2")
    if result.series.keywords != frozen_keywords:
        raise ValueError("trend keywords must match frozen direction keywords")
    allowed = set(frozen_keywords)
    if any(not set(point.values).issubset(allowed) for point in result.series.weekly_points):
        raise ValueError("trend values must match frozen keywords")
    present = set().union(*(set(point.values) for point in result.series.weekly_points))
    if result.source_status == "success" and present != allowed:
        raise ValueError("successful trend result requires every frozen keyword")
    if result.source_status == "partial" and not (present and present < allowed):
        raise ValueError("partial trend result requires a non-empty keyword subset")
    if result.source_status in {"no_data", "degraded"} and present:
        raise ValueError("no-data or degraded trend result cannot contain values")
    if result.source_status in {"partial", "no_data", "degraded"}:
        if result.diagnostic is None:
            raise ValueError("non-success trend result requires diagnostic")
        if result.diagnostic.actual_series_count != len(present):
            raise ValueError("diagnostic series count must match bound keywords")
```

正式结果继续写入现有 `result.json`，不新增原始 HTML、截图或第二份趋势文件；周点是 `DirectionResult` 的结构化组成部分，可随不可变结果版本复算。Store 明确不调用 `analyze_trend_series()`，因为派生字段只允许由已经过纯函数测试的计算模块生成。

- [ ] **Step 3: 写 Harness 白名单失败测试**

```python
def test_compact_direction_keeps_calculations_but_drops_diagnostic() -> None:
    compact = _compact_direction(direction_result(degraded_trend_result()))

    trend = compact["trend_result"]
    assert "keyword_analyses" in trend
    assert "annual_ranking" in trend
    assert "diagnostic" not in trend
    assert "percentage" not in json.dumps(trend, ensure_ascii=False)
```

- [ ] **Step 4: 更新 Harness 精简结果**

把 `_compact_direction()` 的 `trend_observations` 列表替换为：

```python
trend_payload = direction.trend_result.model_dump(mode="json", exclude={"diagnostic"})
```

返回键固定为 `trend_result`。下游得到周点、年度/月度确定性分析和边界状态，但不得到内部失败字段、命中标记或尝试次数。删除所有对 `trend_observations` 的白名单引用。

- [ ] **Step 5: 运行 Store 与 Harness 测试**

Run:

```bash
cd backend && uv run pytest tests/platform/test_market_research_store_trends.py tests/harness/test_market_research_result_trends.py -v
```

Expected: PASS；旧模型、错关键词和非法状态被拒绝，诊断不进入下游上下文。

- [ ] **Step 6: 建议提交**

```text
feat(market): 持久化并校验趋势 v2 结果

- 发布前校验契约版本、冻结关键词和周点取值
- 将周度序列与确定性分析写入不可变正式结果
- 向下游保留趋势数据并剔除内部诊断字段
```

---

### Task 7: 在纯文本报告展示变化值、排序和来源降级

**Files:**
- Modify: `backend/career_os/platform/market_research/renderer.py:149-172`
- Create: `backend/tests/platform/test_market_research_renderer.py`

**Interfaces:**
- Consumes: `DirectionResult.trend_result`。
- Produces: 用户可见第 6 章 Google 搜索关注度纯文本。

- [ ] **Step 1: 写完整结果渲染失败测试**

```python
def test_renderer_shows_half_year_and_monthly_point_changes_without_percent() -> None:
    report = PlainTextMarketReportRenderer().render(market_result(successful_trend_result()))
    trends_section = report.split("6. Google 搜索关注度", maxsplit=1)[1].split(
        "7. 样本限制", maxsplit=1
    )[0]

    assert "前半年 2025-07-14～2026-01-05：均值 20.0" in report
    assert "后半年 2026-01-12～2026-07-06：均值 35.0" in report
    assert "年度变化 +15.0 个归一化热度点：上升" in report
    assert "2026-04：均值 35.0" in report
    assert "2026-04 → 2026-05：+0.0 个归一化热度点，基本持平" in report
    assert "长期上升，近期基本持平" in report
    assert "0 是有效指数值，但不等于绝对零次搜索" in report
    assert "低搜索量查询可能显示为 0" in report
    assert "抽样和随机噪声" in report
    assert "%" not in trends_section
```

- [ ] **Step 2: 写排序、当前月和降级失败测试**

```python
def test_renderer_labels_relative_ranking_and_partial_current_month() -> None:
    report = PlainTextMarketReportRenderer().render(
        market_result(successful_trend_result(("LLM Agent", "AI Agent", "Agent 开发")))
    )

    assert "全年相对热度：1. Agent 开发" in report
    assert "近期相对热度：1. Agent 开发" in report
    assert "2026-07（截至当前，不参与正式判断）" in report
    assert "不代表招聘岗位数量、招聘需求或岗位价值" in report


def test_renderer_keeps_trends_section_when_source_degrades() -> None:
    report = PlainTextMarketReportRenderer().render(market_result(degraded_trend_result()))

    assert "Google 搜索关注度" in report
    assert "页面在一次刷新后仍未完成渲染" in report
    assert "BOSS 岗位调研已继续执行" in report
```

- [ ] **Step 3: 运行失败测试**

Run:

```bash
cd backend && uv run pytest tests/platform/test_market_research_renderer.py -v
```

Expected: FAIL，旧 Renderer 仍读取 `time_range/percentage/comparison_label`。

- [ ] **Step 4: 替换 `_trends()` 渲染逻辑**

实现小型格式化函数，所有数字统一一位小数：

```python
def _format_delta(value: float) -> str:
    """把归一化热度点差格式化为带正负号的一位小数。"""
    return f"{value:+.1f}"


def _direction_label(value: str) -> str:
    """把稳定方向机器值转换为用户可见中文标签。"""
    return {
        "up": "上升",
        "down": "下降",
        "flat": "基本持平",
        "insufficient_data": "数据不足",
        "divergent": "走势分化",
    }[value]
```

`_trends()` 逐关键词输出前后半年、年度点差、三个完整月、两组相邻月点差、当前月参考和长期/近期关系；至少两个关键词有效时输出全年、近期排序和方向级概括。降级状态按 `diagnostic.page_state` 映射成固定安全文案，不展示 `failed_field`、标记名或页面原文。

章节末尾固定输出：

```text
Google Trends 数值是在当前比较条件下归一化到 0～100 的相对搜索关注度；变化值单位是归一化热度点，不是搜索次数或百分比，也不代表招聘趋势。0 是有效指数值，但不等于绝对零次搜索；低搜索量查询可能显示为 0，结果也可能包含抽样和随机噪声。
```

- [ ] **Step 5: 运行渲染测试**

Run:

```bash
cd backend && uv run pytest tests/platform/test_market_research_renderer.py -v
```

Expected: PASS；Google Trends 章节没有 `%`，降级仍保留章节和边界说明。

- [ ] **Step 6: 建议提交**

```text
feat(market): 展示趋势半年与逐月变化

- 输出半年均值、月均值和归一化热度点变化
- 展示长期近期信号与同页关键词相对排序
- 为无数据和技术降级提供固定安全说明
```

---

### Task 8: 全链路回归、隐私扫描和真实页面人工冒烟

**Files:**
- Verify: `docs/superpowers/specs/2026-07-16-google-trends-web-v2-design.md`
- Verify: `backend/career_os/platform/market_research/`
- Verify: `backend/tests/platform/`

**Interfaces:**
- Consumes: Tasks 1～7 的完整 v2 链路。
- Produces: 默认 CI 可重复验证结果和一次不保存截图的真实页面人工验收记录。

- [ ] **Step 1: 扫描旧模型残留**

Run:

```bash
rg -n "TrendObservation|trend_observations|visible_period_comparison|comparison_card|comparison_percentage|comparison_label|past_3_months" backend/career_os backend/tests
```

Expected: 无输出。若仍有输出，逐处改为 `TrendResearchResult` 或删除旧兼容分支后重新执行。

- [ ] **Step 2: 运行 Trends 专项测试**

Run:

```bash
cd backend && uv run pytest \
  tests/platform/test_market_research_page_contracts.py \
  tests/platform/test_market_research_trends.py \
  tests/platform/test_market_research_trend_analysis.py \
  tests/platform/test_market_research_runner_trends.py \
  tests/platform/test_market_research_synthesis_trends.py \
  tests/platform/test_market_research_store_trends.py \
  tests/platform/test_market_research_renderer.py \
  tests/harness/test_market_research_result_trends.py -v
```

Expected: 全部 PASS，无网络请求、无真实 sleep、无浏览器启动。

- [ ] **Step 3: 运行确定性全量回归**

Run:

```bash
cd backend && uv run pytest tests/ -m "not llm" -q
```

Expected: 全部 PASS；若历史测试仍构造旧 `trend_observations`，直接更新为 v2 fixture，不添加兼容适配器。

- [ ] **Step 4: 执行隐私边界扫描**

Run:

```bash
rg -n "page\.html|outerHTML|innerHTML|cookie|screenshot|save.*html|raw_dom" \
  backend/career_os/platform/market_research/{trends.py,trend_analysis.py,page_contracts.py}
```

Expected: 不存在读取或保存完整 HTML、DOM、Cookie、失败截图的实现；仅允许注释或明确禁止性文字命中。

- [ ] **Step 5: 执行真实 Google Trends 人工冒烟**

Run:

```bash
make dev test
```

服务启动后，在专用可见 Chrome 中使用无隐私关键词 `LLM Agent`、`AI Agent`、`Agent 开发` 执行一个方向。人工核对：

1. URL 同时包含三个关键词、`geo=CN`、`hl=zh-CN` 和过去 12 个月。
2. 页面在首次最多 5 秒或一次刷新后的最多 5 秒内进入终止状态。
3. 成功时 `actual_series_count=3`，每个数据列表头唯一匹配同名冻结关键词，周点约为 53 个，正式计算使用最近 52 个。
4. 报告显示前后半年日期、均值、点差、最近三个完整月、相邻月点差和边界声明。
5. 用户可见报告中没有把点差写成百分比或招聘趋势。
6. 人工验收只记录通过/失败、契约版本和结构化诊断，不保存失败截图。

- [ ] **Step 6: 检查最终差异**

Run:

```bash
git diff --check && git status --short
```

Expected: `git diff --check` 无输出；变更只覆盖本计划列出的 Trends v2 影响面和对应测试。

- [ ] **Step 7: 建议提交**

```text
test(trends): 完成新版页面回归与验收

- 覆盖页面状态、周度解析、趋势计算和降级传播
- 验证正式存储、下游上下文和用户报告契约
- 完成隐私扫描与真实页面人工冒烟记录
```

---

## Completion Criteria

- 每个职业方向只构造一个 Google Trends 多关键词过去 12 个月查询；受控重试始终复用相同参数。
- 页面通过表头逐列绑定冻结关键词；缺失首列、中间列或末列时形成可验证的部分成功，不按位置补列。
- 成功页面保存共同时间轴周点，0 值有效，最近 52 周被确定性拆为 26/26；报告说明 0 不等于绝对零次搜索以及低搜索量、抽样和噪声边界。
- 最近三个完整自然月逐月计算；使用 UTC 日期识别的当前月不参与正式判断。
- 所有变化值都使用归一化热度点和 ±10 阈值，报告不出现百分号。
- `render_timeout` 与 `page_changed` 可区分，刷新严格不超过一次。
- 验证进入 `waiting_user`；明确 429 执行 10/30/60 秒退避，通用技术错误只执行一次 5 秒短重试，两者耗尽后分别记录诊断并降级。
- Trends 无数据或技术失败不阻断 BOSS；浏览器、存储和取消硬失败仍按现有终态处理。
- `analyze_trend_series()` 独占派生计算；Store 只校验结构、归属和来源状态，不重复计算。
- 市场 Worker 与 Harness 下游输入剔除 `diagnostic`，完整诊断只保留在正式审计结构中。
- 正式结果、Store、Harness 和 Renderer 只使用 v2 契约，旧比较卡片模型无残留；成功测试 fixture 均通过标准 Pydantic 校验。
- 自动测试不访问真实 Google；真实页面人工冒烟不保存失败截图。

---

*Plan 版本 1.1.0 — 2026-07-16 — 基于已确认 Google Trends Web v2 spec 1.1.0*
