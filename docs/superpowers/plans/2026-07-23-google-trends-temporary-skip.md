# Google Trends 开发期临时跳过 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan step-by-step. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 保持代码默认执行 Google Trends 页面采集，通过开发环境配置显式关闭采集，同时继续执行 BOSS 采集和后续市场调研链路。

**Architecture:** 保持 `GoogleTrendsCollector.collect`（采集 Google Trends 数据）现有接口不变，把临时配置判断放在该模块内部、任何页面操作之前。关闭时复用现有 `_degraded`（构造技术降级结果）实现返回 `degraded + config_skipped`，Runner、预算、正式数据模型、存储、综合、报告和前端均不感知新分支。该 seam 保持调用方知识不变，临时运行复杂度集中在采集模块；现有真实采集测试只增加配置门控。后续删除配置字段、短路判断和测试门控即可完成退出。

**Tech Stack:** Python 3.11、Pydantic 2、pydantic-settings、DrissionPage、dotenv、pytest

**Design SSOT:** `../specs/2026-07-23-google-trends-temporary-skip-design.md`

**状态:** 待实现；仅用于当前开发阶段，不作为正式版本能力长期保留

---

## Global Constraints

- 只修改 `backend/career_os/platform/market_research/settings.py`、`backend/career_os/platform/market_research/trends.py`、`backend/.env.example` 和 `backend/tests/platform/test_market_research_trends.py`。
- 不修改 Runner、正式模型、Store、综合、报告、前端、其他文档或其他测试文件。
- 不新增 `skipped` 状态；关闭时固定产生 `source_status="degraded"` 和 `diagnostic.page_state="config_skipped"`。
- 保留 `COLLECTING_TRENDS` 阶段和单方向 600 秒共享有效预算。
- 关闭时禁止页面导航、页面读取、刷新、等待、重试和人工验证；不人为扣减预算。
- 开启时必须完整执行当前 Google Trends v2 路径，不改变既有行为。
- `trends_enabled`（是否启用趋势采集）的代码默认值必须为 `True`；当前开发环境通过 `.env` 中的 `false` 显式进入临时短路。
- 版本库只修改 `backend/.env.example`；不得修改或提交用户现有的 `backend/.env`，但交付时必须提示开发者在实际 `.env` 或进程环境中显式设置 `false`。
- 不新增 `trends_enabled=False`（关闭趋势采集）路径的自动化测试；只为现有真实采集测试增加配置门控，关闭时跳过、开启时执行原测试逻辑。
- 所有新增字段和判断注释必须解释字段或函数的含义与作用。
- 不触碰现有未跟踪的 `docs/assets/`。

## File Structure and Responsibilities

### 修改文件

```text
backend/career_os/platform/market_research/settings.py
    # 定义 trends_enabled（是否启用趋势采集）临时配置，代码默认开启

backend/career_os/platform/market_research/trends.py
    # 在 GoogleTrendsCollector.collect 的页面操作前短路并返回现有降级结果

backend/.env.example
    # 声明 MARKET_RESEARCH__TRENDS_ENABLED=false 及临时用途

backend/tests/platform/test_market_research_trends.py
    # 为调用 collect 的现有真实采集测试增加配置门控
```

### 明确不修改

```text
backend/career_os/platform/market_research/runner.py
backend/career_os/platform/market_research/models.py
backend/career_os/platform/market_research/store.py
backend/career_os/platform/market_research/synthesis.py
backend/career_os/platform/market_research/renderer.py
backend/tests/**  # test_market_research_trends.py 除外
web/**
```

---

## Task 1: 增加临时配置并在 Trends 采集接口内短路

**Files:**
- Modify: `backend/career_os/platform/market_research/settings.py:24-30`
- Modify: `backend/career_os/platform/market_research/trends.py:65-73`
- Modify: `backend/.env.example:25-29`
- Modify: `backend/tests/platform/test_market_research_trends.py`
- Reference only: `backend/career_os/platform/market_research/trend_analysis.py:80-88`
- Reference only: `backend/career_os/platform/market_research/trends.py:197-214`

**Interfaces:**
- Consumes: `settings.market_research.trends_enabled`（是否启用趋势采集）和冻结的 `DirectionPlan.trends_keywords`（方向趋势关键词）。
- Preserves: `GoogleTrendsCollector.collect(direction, page, budget)` 现有调用接口、Runner 阶段顺序和共享预算对象。
- Produces when disabled: 空周点的 `TrendResearchResult`，其 `source_status` 为 `degraded`，`diagnostic.page_state` 为 `config_skipped`。
- Produces when enabled: 当前 Google Trends v2 采集结果，不改变导航、重试、解析和确定性分析逻辑。

- [ ] **Step 1: 做实现前基线检查**

运行：

```bash
git status --short
git diff --check
```

期望：确认 `docs/assets/`、已新增 spec 和本 implementation plan 属于现有工作区状态；不得清理或覆盖它们。`git diff --check` 无格式错误。

- [ ] **Step 2: 在集中设置中加入代码默认开启的临时字段**

在 `MarketResearchSettings` 的 Trends 重试配置附近增加：

```python
trends_enabled: bool = True  # 是否启用 Google Trends 页面采集；代码默认执行正式采集路径
```

字段含义与作用：

- `trends_enabled`（是否启用趋势采集）是进程级工程配置。
- `False` 表示 `GoogleTrendsCollector.collect` 不操作页面，直接返回现有技术降级结果。
- `True` 表示执行当前完整 Google Trends v2 采集路径。
- 代码默认使用 `True`；当前开发环境必须通过 `.env` 显式配置 `False` 才进入临时跳过路径。
- 该字段不进入 `ResearchPlan`（调研方案）、`ResearchSnapshot`（运行快照）或正式结果结构。

保持 `MarketResearchSettings.model_config` 的 `extra="forbid"` 和 `frozen=True` 不变，不增加额外校验器。

- [ ] **Step 3: 先验证嵌套环境变量可以覆盖配置**

直接构造 `MarketResearchSettings`（市场调研设置）验证模型默认值，避免本地 `backend/.env` 干扰：

```bash
cd backend && uv run python -c "from career_os.platform.market_research.settings import MarketResearchSettings; print(MarketResearchSettings().trends_enabled)"
```

期望输出：

```text
True
```

运行关闭覆盖检查：

```bash
cd backend && MARKET_RESEARCH__TRENDS_ENABLED=false uv run python -c "from career_os.config import settings; print(settings.market_research.trends_enabled)"
```

期望输出：

```text
False
```

第一条命令只验证字段自身默认执行正式采集路径；第二条命令通过进程环境验证顶层 `Settings`（应用设置）可以显式关闭采集。显式进程环境优先于 `backend/.env`，不要修改或提交用户的 `backend/.env`。

- [ ] **Step 4: 在采集接口的页面操作前加入最小短路**

在 `GoogleTrendsCollector.collect` 中保留现有 query 和白名单 URL 构造，随后在 `rate_limit_attempt` 初始化和首次 `_navigate` 调用之前加入：

```python
if not settings.market_research.trends_enabled:
    return self._degraded(direction, url, "config_skipped", 1)
```

相关函数和字段含义：

- `collect`（采集 Google Trends 数据）接收冻结方向、专用 Chrome 页面和共享有效预算，返回唯一趋势调研结果。
- `_degraded`（构造技术降级结果）复用现有空 `TrendSeries`、`TrendDiagnostic` 和 `analyze_trend_series` 路径。
- `url`（趋势页面地址）仍由现有页面契约构造并经过官方 host 白名单校验，用作降级结果中非空、格式合法的 `series.page_url`。
- `config_skipped`（配置跳过）只作为内部 `diagnostic.page_state`，不增加模型枚举或报告分支。
- `attempt=1` 是满足现有 `Literal[1, 2]` 约束的临时兼容占位值；配置跳过没有发生真实页面加载，该值不表示已经执行过第一次页面尝试，也不得用于统计页面访问次数。

短路必须位于以下行为之前：

```python
self._navigate(...)
self.contract.user_action_required(...)
self._wait_for_terminal_state(...)
self._refresh(...)
self._wait(...)
```

不要修改 `_source_status`（把诊断映射为来源状态）函数：除 `partial_columns` 和 `no_data` 外的现有诊断自然映射为 `degraded`。

- [ ] **Step 5: 在示例环境文件中声明临时关闭配置**

在 `backend/.env.example` 的市场调研配置段加入：

```env
# 临时跳过 Google Trends 页面采集；恢复采集时改为 true。
MARKET_RESEARCH__TRENDS_ENABLED=false
```

保留现有 `MARKET_RESEARCH__TARGET_JOBS_PER_KEYWORD` 和 `MARKET_RESEARCH__BUDGET_SECONDS`，不要调整其他默认值或示例说明。

`backend/.env.example`（环境配置示例）只提供新安装和人工配置参考，不会覆盖已经存在的 `backend/.env`。不要修改或提交用户的实际 `.env`；实现交付时必须明确提示：当前开发实例只有在实际 `.env` 或启动进程环境中设置 `MARKET_RESEARCH__TRENDS_ENABLED=false` 后才会跳过 Google Trends，修改后还需重启后端。

- [ ] **Step 6: 为现有真实采集测试增加配置门控**

不新增关闭路径测试。在 `test_market_research_trends.py` 中导入进程级 `settings`（应用设置），定义只用于真实页面采集状态机测试的标记：

```python
from career_os.config import settings


requires_trends_enabled = pytest.mark.skipif(
    not settings.market_research.trends_enabled,
    reason="Google Trends collection is disabled by configuration",
)
```

字段和标记含义：

- `settings.market_research.trends_enabled`（是否启用趋势采集）是本次测试进程启动时读取的配置。
- `requires_trends_enabled`（要求启用趋势采集）只装饰实际调用 `GoogleTrendsCollector.collect` 的现有测试。
- 配置为 `False` 时，这些真实采集测试由 pytest 明确标记为跳过，不进入测试逻辑，也不验证关闭路径。
- 配置为 `True` 时，原有测试函数和断言完整执行。
- `_bind_keyword_headers`（按名称绑定关键词表头）等不依赖 `collect` 配置的纯解析测试继续始终执行。

不要在测试函数内部直接静默 `return`；显式 skip 能让测试报告准确区分“已验证通过”和“因开发期开关未执行”。

- [ ] **Step 7: 验证显式关闭后的测试基线**

先显式关闭配置运行现有 Trends 测试：

```bash
cd backend && MARKET_RESEARCH__TRENDS_ENABLED=false uv run pytest tests/platform/test_market_research_trends.py -v
```

期望：调用 `collect` 的真实采集测试显示为 `SKIPPED`，不依赖采集开关的纯解析测试继续通过，测试文件没有失败。

随后验证仓库标准非 LLM 测试入口在显式关闭配置下没有失败：

```bash
cd backend && MARKET_RESEARCH__TRENDS_ENABLED=false uv run pytest tests/ -m "not llm" -q
```

此步骤不测试 `trends_enabled=False` 的短路结果，只证明开发环境显式关闭采集不会破坏仓库测试基线。本次实施验收不要求再以 `trends_enabled=True` 重跑同一组 Trends 测试；真实采集路径的重新执行与验收延后到 Temporary Exit Checklist（临时方案退出清单）。

- [ ] **Step 8: 做最终范围和格式检查**

运行：

```bash
git diff --check
git status --short
git diff -- backend/career_os/platform/market_research/settings.py backend/career_os/platform/market_research/trends.py backend/.env.example backend/tests/platform/test_market_research_trends.py
```

期望：

- 代码和测试实现只修改允许的四个文件；
- 没有其他测试、Runner、模型、Store、报告或前端变更；
- `docs/assets/` 和用户其他既有改动保持原样；
- diff 无空白错误。

- [ ] **Step 9: 人工语义验收**

逐项确认：

- 配置代码默认值为 `True`；开发环境通过 `.env` 显式设置 `False`；
- 已向开发者明确说明实际 `backend/.env` 或启动进程环境必须配置 `false`，且修改后需要重启后端；
- `false` 路径在任何页面操作前返回；
- 降级结果保留冻结关键词且周点为空；现有确定性分析会为每个冻结关键词生成“数据不足”分析项；
- `source_status="degraded"`；
- `diagnostic.page_state="config_skipped"`；
- Runner 和报告无需新分支；
- 600 秒预算没有重新分配或人为扣减；
- `true` 路径仍执行原有采集实现。

- [ ] **Step 10: 建议提交信息（仅在用户另行要求 commit 时使用）**

```text
chore(market): 临时跳过 Google Trends 页面采集

- 增加代码默认开启、支持开发环境显式关闭的趋势采集配置
- 复用现有技术降级结果并继续 BOSS 调研流程
- 为现有真实采集测试增加临时配置门控
- 在环境示例中记录临时开关与恢复方式
```

本步骤只提供提交信息，不在执行计划时自动创建 commit。

---

## Completion Criteria

计划完成必须同时满足：

1. 四个允许文件完成对应修改，未扩大范围；
2. 代码默认值为 `True`，且嵌套环境变量能将配置显式覆盖为 `False`；
3. 已提示开发者在实际 `backend/.env` 或启动进程环境中显式配置 `False` 并重启后端，且没有修改或提交用户的实际 `.env`；
4. 没有新增关闭路径自动化测试；配置关闭时现有真实采集测试明确跳过且标准非 LLM 测试入口无失败；
5. 本次实施验收不以 `trends_enabled=True` 的 Trends 测试结果作为完成条件；
6. 除配置门控外没有改写现有测试逻辑或断言；
7. `git diff --check` 通过；
8. 没有触碰用户现有 `docs/assets/` 或其他无关改动。

## Temporary Exit Checklist

恢复正式 Google Trends 流程并删除临时方案时：

- [ ] 将开发环境 `MARKET_RESEARCH__TRENDS_ENABLED` 改为 `true` 并完成人工主路径验收；
- [ ] 删除 `MarketResearchSettings.trends_enabled` 字段；
- [ ] 删除 `GoogleTrendsCollector.collect` 中的配置短路；
- [ ] 删除 `backend/.env.example` 中的临时配置；
- [ ] 删除 `test_market_research_trends.py` 中的临时配置门控，恢复默认执行真实采集测试；
- [ ] 重新运行现有 Google Trends v2 测试；
- [ ] 确认无需迁移正式模型或历史结果。
