# BOSS + Google Trends Market Research Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用真实、近期、可审计的 BOSS 直聘岗位和 Google Trends 搜索关注度替换占位 `browser_fetch`，并把“用户确认方案 → Harness 冻结 → 可见 Chrome 采集 → LLM 语义提取 → 程序确定性统计 → 市场 Worker 归纳 → 普通聊天回复”接入现有市场阶段。

**Architecture:** 新增 `career_os.platform.market_research` 深模块作为唯一市场调研 seam。市场 Worker 只生成方案提案并使用已确认的 `plan_id` 启动任务；Coordinator 负责接收与编排，但不创建业务方案；Harness 管理的 `MarketResearchPlanStore` 是持久化方案的唯一创建者和写入者。模块内部拥有方案、运行状态、DrissionPage、采集器、提取器、统计器、结果版本与原子存储。FastAPI 后台线程顺序执行最多三个方向，聊天 API 和 Coordinator 只读取状态/正式结果并执行硬阻塞，前端每 2 秒轮询状态卡。下游只通过 Session artifact 中的正式结果引用解析冻结结果，不再把 `prior_results.market` 当作授权或数据真值。

**Tech Stack:** Python 3.11、FastAPI、Pydantic 2、DrissionPage、LiteLLM、React 19、TypeScript、Vite、Tailwind CSS、本地 JSON/JSONL/PNG 文件存储、Bash/Make

**Design SSOT:** `../specs/2026-07-14-market-research-boss-trends-design.md`

**状态:** 待执行

## Global Constraints

- 已确认的 spec 是唯一需求真值；实施时不得重新引入 `browser_fetch`、招聘趋势、岗位需求强弱、城市对比、用户匹配、评分或推荐。
- 首期只支持 BOSS 直聘和 Google Trends，只使用可见 Google Chrome、单标签页、单后台线程，不引入 Celery、Redis、子进程任务或无头浏览器。
- 用户已明确“测试先不考虑”。本计划不新增自动化测试或 Eval，只使用静态编译、前端构建、配置读取和人工冒烟验收；自动化测试另立 spec。
- 原始 JD 和完整 HTML 只存在于调研线程内存；不得写盘、写 Trace、进入 Prompt 日志或传给下游。职责、要求、优先条件、岗位证据和语义技能只持久化通过依据校验的 LLM 结构化提取结果，页面级原始审计证据仅保留成功岗位的 10% 完整网页截图抽样。
- 任何数字结论必须来自冻结的确定性统计；LLM 只发现技能、提取语义和归纳说明。
- `artifacts.market` 是新市场链路生命周期 SSOT；新市场链路的方案提案、异步回执、未确认结果和正式结果都不得写入 `prior_results.market`，下游每次使用前必须通过 Store 解析正式引用。
- 代码中的字段和函数要通过类型、命名、注释或 docstring 解释含义和作用，遵守仓库 `AGENTS.md`。
- 每完成一个 Task 才进入下一个 Task；每个 Task 的建议 commit 都遵循中文 conventional commit 主信息和至少两个具体分点。

---

## File Structure and Responsibilities

### 新增后端深模块

```text
backend/career_os/platform/market_research/
├── __init__.py              # 只导出 MarketResearchService 门面和公共结果类型
├── models.py                # 方案、岗位、趋势、状态、统计、结果的 Pydantic 契约
├── settings.py              # MarketResearchSettings 集中配置与校验
├── errors.py                # error_category/error_code/user_action 结构化错误
├── plans.py                 # 方案草稿、修改、确认、哈希和一次性消费
├── store.py                 # demo 级目录、原子写入、索引、版本、清理与引用
├── service.py               # start/status/continue/cancel/retry/reuse/delete 唯一应用门面
├── runner.py                # 专用后台线程、方向串行调度、预算和状态机
├── browser.py               # 专用 Chrome 生命周期、PID、单标签页与安全导航
├── page_contracts.py        # BOSS/Trends 版本化页面字段契约
├── trends.py                # Google Trends 两个时间窗口采集
├── boss.py                  # BOSS 搜索、详情采集、登录等待和低频操作
├── parsers.py               # 薪资、经验、学历、活跃度、URL 的确定性解析
├── sampling.py              # 全局去重、公司上限、关键词额度和 10% 截图抽样
├── extraction.py            # 前 10/中 10/后 10 语义提取编排与依据校验
├── skills.py                # 基础技能词表、别名归并和确定性技能计数
├── statistics.py            # 样本等级、分布、经验重点和薪资中位数
├── synthesis.py             # 无工具市场 Worker 综合与引用校验
└── renderer.py              # PlainTextMarketReportRenderer 固定纯文本章节
```

### 新增 Prompt 与 API

```text
backend/career_os/platform/prompt/market_research/
├── extraction_system.md     # 不可信 JD 的批量结构化提取约束
├── direction_system.md      # 冻结方向数据的只读综合约束
└── comparison_system.md     # 多方向并列对照约束
backend/career_os/api/market_research.py  # 方案、状态、继续、取消、复用、重试和删除接口
```

### 现有文件改造

- `backend/career_os/agents/lc/tools.py`：删除 `browser_fetch` Schema，新增仅接收 `plan_id` 的 `market_research` Schema。
- `backend/career_os/platform/tool/registry.py`：市场 Worker 获得 `market_research`；Opportunity Worker 失去浏览器工具。
- `backend/career_os/harness/executor.py`：注册新工具 Handler，并把 `session_id` 交给 Service 校验方案归属。
- `backend/career_os/agents/graphs/coordinator.py`：识别异步 accepted，不把它当市场阶段完成；正式结果确认前阻止阶段推进。
- `backend/career_os/harness/delegate.py`、`backend/career_os/harness/pipeline_routing.py`：移除以 `prior_results.market` 存在性作为授权的旧 JD-R1，改用正式结果解析器。
- `backend/career_os/harness/pipeline_jd_context.py`、`backend/career_os/agents/lc/coordinator_llm.py`：移除 `prior_results.market` 对 JD 上下文和阶段 fallback 的旧影响，改用已确认正式结果状态或已验证的 Opportunity 结果。
- `backend/career_os/harness/profile_memory.py`：停止通过通用档案记忆注入市场数据；正式精简结果改由 Harness 在 Opportunity 派工通过后专门注入。
- `backend/career_os/platform/prompt/opportunity/system.md`：读取专用 `market_research_result` 上下文，不再要求读取 `prior_results.market`。
- `backend/career_os/api/chat.py`：运行中拒绝普通聊天；完成时幂等发布普通 assistant 消息。
- `backend/career_os/platform/store/session.py`：`artifacts.market` 只保存方案、运行、确认状态和正式结果引用，不保存 Worker 提案正文或全量市场数据。
- `backend/career_os/main.py`：注册市场 API，并在启动时执行进程中断恢复。
- `web/src/pages/ChatPage.tsx`、`web/src/hooks/useChatSSE.ts`、`web/src/lib/marketResearchApi.ts`、`web/src/components/MarketResearchStatusCard.tsx`：方案预览、结构化启动动作、状态轮询、输入锁定、继续/取消、结果确认和完成消息刷新。
- `scripts/dev.sh`、`scripts/clean.sh`、`Makefile`：demo 进程登记、定向停止和市场数据清理。

---

## Task 1: 建立公共数据契约、集中配置和结构化错误

**Files:**
- Create: `backend/career_os/platform/market_research/__init__.py`
- Create: `backend/career_os/platform/market_research/models.py`
- Create: `backend/career_os/platform/market_research/settings.py`
- Create: `backend/career_os/platform/market_research/errors.py`
- Modify: `backend/career_os/config.py`
- Modify: `backend/pyproject.toml`
- Modify: `backend/uv.lock`

- [ ] **Step 1: 定义不可变方案与运行状态契约**

在 `models.py` 中使用 `ConfigDict(extra="forbid")` 禁止 LLM 或 API 混入未确认字段。核心类型至少包括：

```python
class FilterPolicy(BaseModel):
    """FilterPolicy（固定筛选策略）保存用户确认并参与方案哈希的不可变岗位准入规则。"""
    model_config = ConfigDict(extra="forbid", frozen=True)

    employment_type: Literal["full_time"] = "full_time"  # 只采集全职岗位
    allowed_recruiter_activity: tuple[Literal["刚刚活跃", "今日活跃", "3 日内活跃"], ...] = ("刚刚活跃", "今日活跃", "3 日内活跃")  # 允许的招聘者活跃度；使用用户预览和确认时展示的规范值
    require_bounded_monthly_salary: Literal[True] = True  # 要求薪资上下限均可解析为月薪
    max_jobs_per_company: Literal[5] = 5  # 单方向同一公司最多保留岗位数
    use_posted_date_filter: Literal[False] = False  # 不使用发布日期过滤


class DirectionProposal(BaseModel):
    """DirectionProposal（方向提案）保存市场 Worker 建议、但尚未补齐默认值的搜索条件。"""
    model_config = ConfigDict(extra="forbid", frozen=True)

    direction_name: str  # 用户看到的职业方向名称
    boss_keywords: tuple[str, ...]  # BOSS 搜索词，数量为 1 到 3
    trends_keywords: tuple[str, ...]  # Google Trends 近义词，数量为 1 到 3
    cities: tuple[str, ...] = ()  # 用户明确指定的城市顺序；空元组表示由 Store 补默认城市
    experience_basis: Literal["total", "related"]  # 工作年限采用总年限还是目标职业相关年限
    experience_min: int  # 重点工作年限下限，单位为年
    experience_max: int  # 重点工作年限上限，单位为年


class DirectionPlan(BaseModel):
    """DirectionPlan（方向方案）保存一个职业方向的冻结搜索条件。"""
    model_config = ConfigDict(extra="forbid", frozen=True)

    direction_name: str  # 用户看到的职业方向名称
    direction_key: str  # 规范化方向键，用于跨 Session 查找复用候选
    boss_keywords: tuple[str, ...]  # BOSS 搜索词，数量为 1 到 3
    trends_keywords: tuple[str, ...]  # Google Trends 近义词，数量为 1 到 3
    cities: tuple[str, ...]  # 实际搜索城市及严格执行顺序，数量为 1 到 4
    experience_basis: Literal["total", "related"]  # 工作年限采用总年限还是目标职业相关年限
    experience_min: int  # 重点工作年限下限，单位为年
    experience_max: int  # 重点工作年限上限，单位为年


class ResearchPlan(BaseModel):
    """ResearchPlan（调研方案）保存用户确认后不可修改的完整调研输入。"""
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1  # 方案结构版本
    plan_id: str  # 方案唯一标识
    plan_version: int  # 同一提案每次修改后的递增版本
    status: Literal["draft", "confirmed", "consumed"]  # 方案生命周期状态
    directions: tuple[DirectionPlan, ...]  # 需要顺序执行的 1 到 3 个方向
    filter_policy: FilterPolicy  # 用户预览并确认的固定岗位筛选策略
    budget_seconds: Literal[600] = 600  # 每个方向网页与提取 LLM 共用预算
    source_session_id: str  # 产生和确认方案的 Session
    generated_at: datetime  # 方案生成时间
    confirmed_at: datetime | None  # 用户明确确认时间
    plan_hash: str  # 规范化方案内容的 SHA-256 摘要
```

同时定义 `ResearchStatus`（主任务状态）、`ResearchStage`（当前执行阶段）、`ResearchSnapshot`（状态卡快照）、`CollectedJob`（清洗后可持久化岗位）、`TrendObservation`（页面趋势字段）、`DirectionResult`（单方向正式结果）和 `MarketResearchResult`（版本化顶层结果）。字段必须覆盖 spec 第 11、19 节。`CollectedJob` 的职责、要求、优先条件、岗位证据和语义技能字段只接收通过依据校验的 LLM 提取结果；`semantic_valid=false` 时这些字段为空。该模型不允许出现原始 JD、JD 片段、逐字原文依据、`district`、福利、招聘者、Cookie 或完整 HTML 字段。

- [ ] **Step 2: 定义集中配置并接入全局 Settings**

`MarketResearchSettings` 至少包含并校验：方向上限 3、关键词上限 3、城市上限 4、预算 600 秒、每关键词目标 30、公司上限 5、截图概率 0.1、点击等待 1.5～3 秒、条件等待 2～5 秒、详情/列表/Trends 重试次数、自然月有效期 6、Chrome 路径覆盖和 2 秒轮询间隔。`Settings` 新增：

```python
market_research: MarketResearchSettings = Field(default_factory=MarketResearchSettings)
# market_research（市场调研配置）集中承载浏览器、采集、预算、抽样和有效期参数。
```

把 `Settings.model_config` 增加 `env_nested_delimiter="__"`。环境变量使用嵌套分隔符，例如 `MARKET_RESEARCH__CHROME_PATH`，聊天请求不得覆盖这些工程配置。

运行时直接读取当前 demo 的 `MarketResearchSettings`，不把完整实际配置复制到 `ResearchPlan`、`ResearchSnapshot`、正式结果或 Trace 中形成逐次调研配置快照；方案只保留已明确进入用户确认与哈希范围的 `filter_policy` 和 600 秒预算。

- [ ] **Step 3: 定义结构化错误**

`MarketResearchError` 包含 `error_category`（错误类别）、`error_code`（具体机器码）、`user_action`（用户可执行的下一步）和 `stage`（出错阶段）。固定实现 `browser_failed`、`page_changed`、`trend_no_data`、`trend_comparison_unavailable`、`process_interrupted`、`storage_failed`、`plan_not_confirmed`、`plan_hash_mismatch`、`plan_consumed`、`research_conflict`。

- [ ] **Step 4: 加入 DrissionPage 依赖并刷新锁文件**

运行：

```bash
cd backend && uv add DrissionPage
```

期望：`pyproject.toml` 和 `uv.lock` 同步更新，不自动下载 Chrome。

- [ ] **Step 5: 做类型导入与配置验证**

运行：

```bash
cd backend && uv run python -c "from career_os.platform.market_research.models import ResearchPlan; from career_os.config import settings; print(settings.market_research.budget_seconds)"
```

期望输出：`600`，且导入无循环依赖。

- [ ] **Step 6: 建议提交**

```text
feat(market): 建立市场调研公共契约与配置

- 定义冻结方案、岗位、趋势、运行状态和正式结果结构
- 集中校验采集预算、数量上限、重试与 Chrome 配置
- 引入 DrissionPage 并保持系统 Chrome 为外部前置条件
```

---

## Task 2: 实现方案提案、修改、确认和 Harness 冻结

**Files:**
- Create: `backend/career_os/platform/market_research/plans.py`
- Create: `backend/career_os/api/market_research.py`
- Modify: `backend/career_os/main.py`
- Modify: `backend/career_os/agents/schemas/workers.py`
- Modify: `backend/career_os/agents/graphs/coordinator.py`
- Modify: `backend/career_os/platform/prompt/market/system.md`
- Modify: `backend/career_os/harness/profile_memory.py`
- Modify: `backend/career_os/platform/store/session.py`

- [ ] **Step 1: 实现规范化哈希与方案版本**

`MarketResearchPlanStore`（调研方案存储器）写入 `settings.data_dir/market_research/plans/<plan_id>.json`。提供：

```python
def create_draft(
    session_id: str,
    directions: list[DirectionProposal],
    filter_policy: FilterPolicy | None = None,
) -> ResearchPlan:
    """创建未确认方案；补齐默认城市和系统固定筛选策略。"""

def revise(plan_id: str, session_id: str, directions: list[DirectionProposal]) -> ResearchPlan:
    """修改方案并递增 plan_version；任何修改都会清空 confirmed_at。"""

def confirm(plan_id: str, session_id: str) -> ResearchPlan:
    """重新计算 plan_hash，校验归属后把方案状态改为 confirmed。"""

def consume(plan_id: str, session_id: str) -> ResearchPlan:
    """原子重算并校验已确认方案哈希，再改为 consumed，防止篡改和重复启动。"""
```

`filter_policy=None` 时构造默认 `FilterPolicy`；API 和 Worker 都不能省略后改写其中的工程规则。`plan_hash` 只覆盖规范化方向、关键词、城市、经验口径、完整 `filter_policy` 和预算，不覆盖 `generated_at` 等时间字段。`consume()` 必须在同一临界区内重新规范化当前持久化内容、计算哈希并与已确认的 `plan_hash` 比较，调用方不提供可伪造或可能过期的 `expected_hash`。

- [ ] **Step 2: 收紧 MarketOutput 与市场 Prompt**

把交互式市场 Worker 的 `MarketOutput` 从旧 `topics` 收紧为只表达方案提案。后台综合使用 `career_os.platform.market_research.models.MarketSynthesisOutput`（市场综合输出），不经过 Coordinator 的同步 Worker 完成分支，避免把提案、异步启动和最终综合混成一种状态：

```python
class MarketPlanProposal(BaseModel):
    """MarketPlanProposal（市场方案提案）表示 Worker 基于初探信息建议的调研范围。"""
    directions: list[DirectionProposal]  # 尚未持久化的职业方向建议列表


class MarketOutput(BaseModel):
    """MarketOutput（交互式市场 Worker 输出）只承载尚未持久化的方案提案。"""
    mode: Literal["plan_proposal"]  # 固定输出模式，表示本轮只生成方案提案
    user_visible_summary: str  # 本轮唯一的用户可见方案摘要
    proposal: MarketPlanProposal  # 交给 Store 规范化和持久化的方案提案
```

市场 Prompt 明确：提案只读取 `exploration.*` 和 `capability.*`；最多 3 个方向；BOSS 与 Trends 关键词分开；年限口径不明确时先询问；不得自行声称已经调研或输出招聘趋势。

在 `backend/career_os/agents/graphs/coordinator.py` 中处理 `mode="plan_proposal"`：Coordinator 收到提案后只校验输出类型并把提案交给 Harness 管理的 `MarketResearchPlanStore.create_draft()`；Store 负责补齐默认值、数量限制、版本和持久化，Coordinator 不自行创建或改写 `ResearchPlan`。随后只把返回的 `plan_id` 写入 `artifacts.market.active_plan_id`。`active_plan_id`（活动方案编号）表示当前 Session 等待用户预览或确认的方案；市场 Worker 不直接写通用 `profile.market` 根节点。

该分支必须在 Coordinator 的通用 `status="completed"` 处理之前截获，并明确执行以下规则：

- 不写 `prior_results.market`，因为提案不是正式市场结果。
- 不执行通用 `{"path": "market", "value": structured_out}` Artifact 补丁，避免覆盖 `artifacts.market` 生命周期信封。
- 不调用 `phase_after_worker_segment_complete()`，不推进到 `jd_analysis`。
- 清空本轮待派发市场 Worker，并把方案预览作为本轮用户可见回复。

Task 2 完成时这条提案链路必须已经可人工验证，不延后到 Task 5。

- [ ] **Step 3: 新增方案 API**

API 提供 `PATCH /v1/market-research/plans/{plan_id}`、`POST /v1/market-research/plans/{plan_id}/confirm` 和 `GET /v1/market-research/plans/{plan_id}`。创建草稿的请求只能来自 Coordinator 接收市场 Worker 提案后的编排分支，方案实体始终由 `MarketResearchPlanStore` 创建；前端没有任意创建方案的接口。修改和确认都校验 `source_session_id`，确认响应返回完整预览所需字段。

- [ ] **Step 4: Session 只保存方案和结果引用**

`artifacts.market` 改成：

```json
{
  "schema_version": 1,
  "active_plan_id": null,
  "active_research_id": null,
  "result_ref": null,
  "reuse_ref": null,
  "market_result_confirmed": false,
  "confirmed_result_ref": null,
  "legacy_unverified": false
}
```

`result_ref`（本 Session 新调研结果引用）与 `reuse_ref`（跨 Session 复用结果引用）必须严格互斥：写入任一引用时清空另一个，并同时设置 `market_result_confirmed=false`、清空 `confirmed_result_ref`。`confirmed_result_ref`（已确认结果引用）只保存用户最后明确确认的当前唯一引用，Resolver 不接受两个当前引用同时存在。

读取旧 `artifacts.market` 且缺少 `schema_version=1` 时标记 `legacy_unverified=true`，不迁移、不传给下游。

- [ ] **Step 5: 人工验证方案冻结**

运行后端后，通过页面产生一份方案，再在浏览器 Network 面板依次检查 revise、confirm 和 get-plan 响应，验证“修改使确认失效，确认后重复读取仍得到同一个哈希”。期望响应中有 `plan_version`、`status`、`plan_hash`、方向、关键词、城市、经验口径与固定 600 秒预算；同时检查 Session：`artifacts.market.active_plan_id` 已写入、生命周期信封未被 Worker 输出覆盖、`prior_results.market` 不存在、Pipeline 仍停留在 market。

- [ ] **Step 6: 建议提交**

```text
feat(market): 实现用户确认的不可变调研方案

- 基于初探与能力信息生成并版本化职业方向提案
- 通过 Session 归属、确认状态和方案哈希约束启动输入
- 将旧市场产物标记为不可复用的 legacy_unverified
```

---

## Task 3: 建立 demo 级 Store、原子发布和结果版本

**Files:**
- Create: `backend/career_os/platform/market_research/store.py`
- Modify: `backend/career_os/platform/market_research/models.py`
- Modify: `backend/career_os/platform/store/session.py`

- [ ] **Step 1: 创建固定目录布局**

`MarketResearchStore`（市场调研存储器）以 `Path(settings.data_dir) / "market_research"` 为根，并只通过受控 ID 解析路径：

```text
market_research/
├── index.json
├── plans/
├── runs/<research_id>/status.json
├── temp/<research_id>/<direction_run_id>/screenshots/
├── staging/<research_id>/v<result_version>-<publish_token>/
├── results/<research_id>/v<result_version>/result.json
├── results/<research_id>/v<result_version>/jobs.json
├── results/<research_id>/v<result_version>/skills.json
├── results/<research_id>/v<result_version>/screenshots/
├── results/<research_id>/v<result_version>/screenshots_manifest.json
├── results/<research_id>/latest.json
├── events/<research_id>.jsonl
├── browser_profile/
└── runtime/
```

拒绝包含 `/`、`..` 或不符合 `research_<hex>`、`direction_<hex>`、`plan_<hex>` 模式的 ID。

- [ ] **Step 2: 实现版本集合原子发布**

单个状态 JSON 继续使用同目录临时文件、`flush()`、`os.fsync()`、`os.replace()`。正式结果不能逐个文件直接写入 `results/`：先把成功方向的临时截图移入同一文件系统的 staging 版本目录，再写入 `result.json`、`jobs.json`、`skills.json` 和 `screenshots_manifest.json`。`jobs.json` 只保存确定性岗位元数据和通过依据校验的 LLM 结构化提取结果，禁止保存原始 JD、JD 片段或逐字原文依据。校验所有岗位、技能、方向和截图引用后，依次 `fsync` 每个 JSON、截图文件、`screenshots/` 子目录和 staging 版本目录；把整个目录原子重命名为正式 `v<result_version>` 后，分别 `fsync staging/<research_id>` 源父目录与 `results/<research_id>` 目标父目录。`latest.json` 使用目标目录内临时文件执行 `flush + fsync + os.replace`，再 `fsync results/<research_id>`。页面级人工审计只能通过 `latest` 或明确正式版本读取 10% 抽样截图，不能直接读取 temp/staging，也不保留截图之外的页面原始证据。正式发布接口：

```python
def publish_result(
    self,
    research_id: str,
    result: MarketResearchResult,
    jobs: list[CollectedJob],
    skill_taxonomy: SkillTaxonomy,
) -> ResultRef:
    """验证 staging 版本集合后原子发布不可变版本；失败时不更新 latest 指针。"""
```

正式写入失败重试一次；仍失败返回 `storage_failed`，不能写 `completed`。失败 staging 不得占用版本号或被任何读取接口发现，启动恢复和取消负责清理；如果正式版本目录已存在，必须验证其不可变清单，禁止覆盖。

- [ ] **Step 3: 实现方向数据引用与版本合并**

首次部分成功固定 `result_version=1`。已有正式版本时，重试成功创建下一版本并通过不可变 `direction_result_ref` 引用旧成功方向；原任务全部失败、没有正式版本时，重试首次成功创建 `result_version=1`，不引用旧方向。新方向使用新 `direction_run_id`；重新计算 comparison 和整体最早过期时间，失败/取消不创建版本。

- [ ] **Step 4: 实现生命周期清理**

- 整次取消：删除该 `research_id` 全部 temp 和未发布截图，只保留最小 cancelled event。
- 方向失败：删除该方向 temp 和截图，不影响其他成功方向。
- 启动恢复：活动运行标记 `process_interrupted`，删除 temp 和浏览器锁，保留正式结果及 `browser_profile`。
- Session 删除：活动任务先走 Service cancel；已完成 Session 只删除引用。

- [ ] **Step 5: 验证目录隔离和原子写入**

运行：

```bash
cd backend && DATA_DIR=./data/plan-smoke uv run python -c "from career_os.platform.market_research.store import MarketResearchStore; print(MarketResearchStore().root)"
```

期望输出路径以 `backend/data/plan-smoke/market_research` 结尾。再通过开发验证入口模拟写完 `result.json` 后失败，确认 `results/` 与 `latest` 均不可见半成品；完整写入时四个文件和截图清单同时可见，重复发布不能覆盖既有版本。

- [ ] **Step 6: 建议提交**

```text
feat(market): 建立调研存储与不可变结果版本

- 按 demo 隔离方案、运行状态、正式结果、截图和事件
- 使用原子替换保证未完成数据不会暴露给聊天与下游
- 支持部分成功版本、方向重试合并和中断清理
```

---

## Task 4: 实现后台线程、状态机、预算时钟和单任务锁

**Files:**
- Create: `backend/career_os/platform/market_research/runner.py`
- Create: `backend/career_os/platform/market_research/service.py`
- Modify: `backend/career_os/main.py`

- [ ] **Step 1: 实现可暂停预算时钟**

`ActiveBudget`（有效预算时钟）累计 Trends、BOSS、自动等待和提取 LLM 时间；`waiting_user` 期间暂停。提供 `remaining_seconds()`（返回剩余秒数）、`pause_for_user()`（开始排除人工等待）和 `resume_from_user()`（恢复计时）。最终统计与综合不调用该时钟。

- [ ] **Step 2: 实现单线程 Runner**

`MarketResearchRunner` 只创建一个后台 `threading.Thread`，在同一线程内创建、使用和关闭 DrissionPage。核心入口：

```python
def run(self, research_id: str, plan: ResearchPlan) -> None:
    """按方案顺序执行方向；至少一个方向成功时进入统计、综合和发布。"""

def request_continue(self, research_id: str) -> None:
    """设置 continue_event，恢复人工登录或验证后的当前方向。"""

def request_cancel(self, research_id: str) -> None:
    """设置 cancel_event；Runner 在安全检查点转为 cancelling 并清理。"""
```

`MarketResearchService`（市场调研应用门面）在 FastAPI lifespan 中通过 `initialize_market_research_service()`（初始化唯一市场调研服务）创建一次；工具 Handler、市场 API 和关闭恢复流程统一调用 `get_market_research_service()`（获取已初始化的共享服务），API 可把该函数作为依赖。Service 内维护唯一 Runner 注册表和对应 continue/cancel 线程事件；未初始化时明确失败，禁止在各入口临时创建彼此独立的 Service。

方向执行顺序固定为 `Trends → BOSS → 语义提取 → 确定性统计 → 市场综合 → 持久化`。其中 Trends、BOSS 和提取 LLM 使用 600 秒预算；统计、综合、持久化不计入。

- [ ] **Step 3: 固化状态转移**

只允许：

```text
queued -> running -> waiting_user -> running
queued|running|waiting_user -> cancelling -> cancelled
running -> completed|partial_completed|failed
```

终态不可回退。每次状态变化同时原子写 `status.json` 和追加脱敏事件。状态快照包含当前方向、关键词、城市、候选数、有效数、语义有效数、阶段、有效耗时和用户动作。

- [ ] **Step 4: 实现 demo 单任务锁**

`MarketResearchService.start(plan_id, session_id)`（启动已确认调研方案）使用 Service 内进程级锁包住完整临界区：读取 `index.json` 检查活动任务 → 生成 `research_id` → 原子写入 `queued` 占位和归属 Session → 消费方案。任何一步失败都回滚占位或保持方案可诊断状态；禁止把“先检查、后另行写入”当作单任务锁。冲突时返回 `research_conflict` 和不含敏感路径的已有任务摘要，其他 Session 不获得 continue/cancel 权限。

- [ ] **Step 5: 实现超时兜底**

预算耗尽后不启动新网页或常规 LLM 请求；正在执行的操作允许结束。`llm_attempt_count`（当前方向已发起的常规岗位提取 LLM 调用次数）为 0 且至少有一条 `collection_valid` 岗位时，预算外执行一次兜底批量提取，解析失败按标准规则再重试一次。

- [ ] **Step 6: 接入 FastAPI 生命周期恢复**

在 `main.py` lifespan 启动阶段调用 `service.recover_interrupted_runs()`；关闭阶段请求当前任务取消并给线程清理机会，但不声称支持断点续跑。

- [ ] **Step 7: 编译验证**

运行：

```bash
cd backend && uv run python -m compileall career_os/platform/market_research career_os/main.py
```

期望：所有文件编译成功，且没有在 import 阶段启动 Chrome 或线程。

- [ ] **Step 8: 建议提交**

```text
feat(market): 实现调研后台线程与硬状态机

- 串行执行多方向并隔离人工等待与十分钟有效预算
- 使用线程事件支持继续、取消和幂等终态清理
- 限制每个 demo 只有一个活动调研并处理中断状态
```

---

## Task 5: 替换 browser_fetch 并接入 Harness 与 Pipeline 硬闸门

**Files:**
- Delete: `backend/career_os/platform/tool/handlers/browser_fetch.py`
- Create: `backend/career_os/platform/tool/handlers/market_research.py`
- Modify: `backend/career_os/agents/lc/tools.py`
- Modify: `backend/career_os/agents/graphs/workers/react_runner.py`
- Modify: `backend/career_os/agents/graphs/workers/react_mocks.py`
- Modify: `backend/career_os/platform/tool/registry.py`
- Modify: `backend/career_os/harness/executor.py`
- Modify: `backend/career_os/platform/trace/labels.py`
- Modify: `backend/career_os/agents/graphs/coordinator.py`
- Modify: `backend/career_os/harness/delegate.py`
- Modify: `backend/career_os/harness/pipeline_routing.py`
- Modify: `backend/career_os/harness/pipeline_phase_transition.py`
- Modify: `backend/career_os/harness/pipeline_jd_context.py`
- Modify: `backend/career_os/agents/lc/coordinator_llm.py`
- Modify: `backend/career_os/harness/profile_memory.py`
- Modify: `backend/career_os/platform/prompt/opportunity/system.md`
- Modify: `docs/architecture/01-协调者与Worker.md`
- Modify: `docs/architecture/02-平台服务.md`
- Modify: `docs/architecture/08-PRD追溯.md`
- Modify: `docs/architecture/09-Worker结构化输出.md`
- Modify: `docs/architecture/14-Harness-Tools-Schema.md`

- [ ] **Step 1: 硬删除旧工具**

删除 Handler、Schema、注册、白名单、Prompt 文案和 Trace 标签中的全部 `browser_fetch`。Opportunity Worker 的业务工具集合不再包含任何浏览器能力。

- [ ] **Step 2: 注册唯一外部工具**

Schema 固定为：

```python
"market_research": {
    "type": "object",
    "properties": {"plan_id": {"type": "string", "pattern": "^plan_[0-9a-f]+$"}},
    "required": ["plan_id"],
    "additionalProperties": False,
}
```

Handler 调用 `MarketResearchService.start(plan_id, session_id)`，返回 `accepted`、`research_id`、`plan_id`、`status`、`message` 和可选 `error_code`。它不接受关键词、城市、`action` 或任意 URL。

- [ ] **Step 3: 让 accepted 不等于市场完成**

`react_runner.py` 在工具返回 `accepted=true` 时不再把结果交给模型继续 ReAct，而是立即返回 `status="accepted_async"`，并携带经过白名单裁剪的 `research_id`、`plan_id` 和初始状态。`accepted_async`（异步任务已接受）表示后台任务已经启动、市场阶段尚未完成。

Coordinator 收到 `accepted_async` 后只把 `active_research_id`（活动调研编号）写入 `artifacts.market` 和 `session_state.market_research`，立即停止本轮继续委派；不得写入 `prior_results.market`、不得调用 `phase_after_worker_segment_complete()`、不得推进到 `jd_analysis`。同时补充 Worker mock 路径的等价返回，保证无 LLM 演示不会把 accepted 当 completed。

- [ ] **Step 4: 移除 `prior_results.market` 的旧授权语义**

当前影响面必须整体迁移，不能只修 Coordinator：

- `harness/delegate.py` 的旧 JD-R1 不再用 `"market" in prior_results` 判断 Opportunity 前置完成。
- `harness/pipeline_routing.py` 不再根据 `prior_results.market` 是否存在决定 market/opportunity 路由。
- `harness/pipeline_jd_context.py` 不再把旧 `prior_results.market` 当成 JD 上下文证据；使用 Session 中同步的已确认正式结果状态、已存在的 Opportunity 结果或真实 JD 输入。
- `agents/lc/coordinator_llm.py` 的 strategy fallback 不再要求 `prior_results` 同时存在 market；已验证的 Opportunity 结果加当前正式市场确认状态即可证明前置链完成。
- `harness/profile_memory.py` 不得把 `artifacts.market` 生命周期信封直接作为业务 market memory，也不得回退到旧 `prior_results.market`；通用 `attach_profile_memory_to_context()` 不再注入 market 数据。`harness/delegate.py` 在 Opportunity 前置校验通过后，才把 `resolve_downstream_result()` 返回的精简正式结果写入专用上下文。
- `prompt/opportunity/system.md` 改为要求读取 `context.market_research_result`（正式市场调研上下文），该字段表示 Harness 本轮重新解析并校验后的市场结果，不是 Session 中可伪造的缓存。
- 既有架构文档中的 JD-R1 和 Worker 结构化输出说明同步改成“正式结果引用解析通过且用户已确认”。旧 Session 的 `prior_results.market` 只保留为不可验证历史数据，不给新链路授权、路由或上下文证据。

正式结果发布和确认都不再回填 `prior_results.market`。结果删除或过期后，因为下游每次重新解析引用，会立即失效，不会被旧缓存绕过。

- [ ] **Step 5: 增加 Pipeline 硬阻塞**

在 delegate 和 routing 的共同前置检查中调用：

```python
def resolve_downstream_result(
    session_id: str,
    session_state: dict[str, Any],
) -> ResolvedMarketResult | HarnessError:
    """解析正式市场结果；校验确认、版本、有效期和删除状态后返回精简下游数据。"""
```

活动状态 `queued/running/waiting_user/cancelling` 返回 `market_research_in_progress`；终态结果未确认返回 `market_result_confirmation_required`；引用缺失、删除、过期或版本不匹配分别返回结构化错误。只有 `result_ref|reuse_ref` 解析有效、`market_result_confirmed=true` 且当前引用与 `confirmed_result_ref` 完全一致才允许下游，并把返回值放入 `context.market_research_result`。

- [ ] **Step 6: 验证工具可见性和旧缓存失效**

运行：

```bash
cd backend && uv run python -c "from career_os.agents.lc.tools import get_litellm_tools_for_worker; print([t['function']['name'] for t in get_litellm_tools_for_worker('market')]); print([t['function']['name'] for t in get_litellm_tools_for_worker('opportunity')])"
```

期望：market 含 `market_research` 且不含 `browser_fetch`；opportunity 两者都不含。再人工构造仅含 `prior_results.market`、但没有有效 `result_ref|reuse_ref` 的 Session，确认 Opportunity 被拒绝；构造有效正式引用时，确认 Opportunity 只收到精简 `context.market_research_result`。

- [ ] **Step 7: 建议提交**

```text
refactor(market): 用冻结方案工具替换 browser_fetch

- 将市场 Worker 外部能力收敛为 market_research(plan_id)
- 移除 Opportunity Worker 的浏览器权限和旧工具兼容路径
- 在正式结果确认前硬阻断市场阶段之后的 Worker
```

---

## Task 6: 实现专用可见 Chrome、页面契约与安全导航

**Files:**
- Create: `backend/career_os/platform/market_research/browser.py`
- Create: `backend/career_os/platform/market_research/page_contracts.py`
- Modify: `backend/career_os/platform/market_research/runner.py`

- [ ] **Step 1: 实现 Chrome 发现与独立 Profile**

`DedicatedChromeSession`（专用浏览器会话）先读取配置覆盖路径，再检查 macOS、Windows、Linux 常见 Google Chrome 路径。使用 `market_research/browser_profile`，始终可见，只创建一个浏览器和一个标签页，不附加日常 Profile。

- [ ] **Step 2: 登记并校验专用 Chrome PID**

启动后把 PID、进程启动时间、可执行路径、demo 数据根和 research_id 写入 `runtime/chrome.json`。关闭或 `make clean` 前必须再次验证这些身份字段，只终止匹配进程，禁止 `pkill Chrome` 或按名称批量杀进程。

- [ ] **Step 3: 建立版本化页面契约**

`BossPageContract` 和 `TrendsPageContract` 明确官方 HTTPS 域名、页面 URL 模板、登录标识、筛选器、列表、详情和趋势卡字段定位器。每个关键字段读取失败都抛出包含 `contract_version`、`stage` 和 `field_name` 的 `page_changed`，不保存 DOM/失败截图，也不交给 LLM 猜。

- [ ] **Step 4: 实现导航白名单**

`validate_external_url(url, allowed_hosts)` 拒绝非 HTTPS、本地 IP、`localhost`、`file:`、`javascript:`、短链和非官方 host。BOSS 岗位链接打开前再次校验；JD 正文中的链接永不点击。

- [ ] **Step 5: 实现人工登录/验证暂停**

检测到登录或验证码页面时：状态改为 `waiting_user`，暂停预算，无限等待 `continue_event` 或 `cancel_event`；继续后重新检查目标页面状态。系统不输入密码、短信码或验证码。

- [ ] **Step 6: 人工启动检查**

通过一个只创建并立即关闭专用页面的开发入口验证：Chrome 可见、使用独立 Profile、没有打开第二个标签页、关闭后日常 Chrome 不受影响。检查完成后删除开发入口，不把调试命令保留为正式 API。

- [ ] **Step 7: 建议提交**

```text
feat(market): 接入专用可见 Chrome 与页面安全契约

- 使用 demo 独立 Profile 和单标签页管理 DrissionPage 生命周期
- 通过官方域名白名单和版本化字段契约限制页面访问
- 支持人工登录验证暂停且只终止已登记专用进程
```

---

## Task 7: 采集 Google Trends 页面直接对比结果

**Files:**
- Create: `backend/career_os/platform/market_research/trends.py`
- Modify: `backend/career_os/platform/market_research/page_contracts.py`
- Modify: `backend/career_os/platform/market_research/runner.py`

- [ ] **Step 1: 实现两个固定窗口采集**

`GoogleTrendsCollector.collect(direction, page, budget)` 对每个方向先执行，中国地区固定，分别选择过去 1 年和最近 3 个月。每个关键词从“热度随时间变化的趋势”区域读取页面可见比较卡片，保存 `query`（查询词）、`geo`（固定 China）、`time_range`（当前选择窗口）、`metric_kind="visible_period_comparison"`（页面窗口同比卡片）、`direction`（页面显示的上升或下降）、`percentage`（页面显示百分比）、`comparison_label`（例如“与过去 1 年相比”）、`page_url`、`fetched_at` 和 `contract_version`。

- [ ] **Step 2: 直接读取页面比较，不自算趋势**

页面字段契约必须把比较卡片与 0～100 折线时间序列、相关搜索上升百分比区分开。比较卡片表示当前选择窗口与前一个等长窗口的页面比较；不下载 CSV，不读取或聚合折线点位，不计算均值、斜率、阈值或综合涨幅。页面正常但没有比较卡片时写 `trend_comparison_unavailable`，无数据写 `trend_no_data`，两者都允许方向继续；页面技术失败按最多两次重试后令方向失败。

- [ ] **Step 3: 生成确定性趋势摘要状态**

程序只判断：关键词方向是否一致、是否分化、长短期是否相反。最终 Worker 必须分别描述一年和三个月，统一声明“搜索关注度不代表招聘趋势”。不保存 Trends 截图。

- [ ] **Step 4: 人工页面验收**

使用 `https://trends.google.com/explore?q=agent&date=today%201-y&geo=CN` 或当时可显示比较卡片的等价页面，核对地区、时间筛选、“热度随时间变化的趋势”区域、方向、百分比和“与过去 1 年相比”标签与 `TrendObservation` 完全一致；再切换最近 3 个月验证对应窗口。隐藏或移除比较卡片时必须产生 `trend_comparison_unavailable`，不得退化为读取折线图猜测；断网后确认重试两次并产出技术失败。

- [ ] **Step 5: 建议提交**

```text
feat(market): 采集 Google Trends 搜索关注度对比

- 读取中国地区一年与三个月页面直接展示的方向和百分比
- 区分比较卡片缺失、无数据、关键词走势分化和页面技术失败
- 固定声明搜索关注度不等于岗位需求或招聘趋势
```

---

## Task 8: 实现 BOSS 全职岗位采集、确定性解析和样本准入

**Files:**
- Create: `backend/career_os/platform/market_research/boss.py`
- Create: `backend/career_os/platform/market_research/parsers.py`
- Create: `backend/career_os/platform/market_research/sampling.py`
- Modify: `backend/career_os/platform/market_research/page_contracts.py`
- Modify: `backend/career_os/platform/market_research/runner.py`

- [ ] **Step 1: 实现薪资、经验、学历和活跃度解析**

`parse_salary(raw)` 只返回税前人民币元/月的 `(salary_min, salary_max)`：双边月薪 `K` 乘 1000；双边年薪除 12，下限 floor、上限 ceil；忽略 `·13薪`；面议、单边、单数值、缺单位和时/天/周薪返回无效。

`normalize_experience(raw)` 和 `normalize_education(raw)` 同时保留原值与固定分组，新标签进入未识别；`is_allowed_recruiter_activity(raw)`（判断招聘者活跃度是否允许）先去除页面文本中的空白，将页面值 `3日内活跃` 映射为公共契约值“3 日内活跃”，再只接受“刚刚活跃”“今日活跃”“3 日内活跃”。

- [ ] **Step 2: 实现严格搜索顺序和低频操作**

每个关键词按方案城市顺序执行，先在页面设置全职；每个新增有效唯一岗位后更新状态。点击/返回随机等待 1.5～3 秒，切换城市/关键词等待 2～5 秒，连续三次滚动无新岗位进入下一城市。达到该关键词 30 条新增岗位立即停止后续城市；关键词严格串行，记录完成、截止或未执行。

使用 BOSS 页面默认排序，不设置岗位发布日期过滤，也不从发布日期得出结论。方向结果保存实际访问过的城市和每个关键词的执行状态，并在样本限制中声明默认排序、账号状态和个性化推荐可能影响本次样本。

- [ ] **Step 3: 详情页决定采集有效性**

只有详情页可访问、未关闭、含身份/URL/标题/城市、原始 JD 在内存中至少包含基本职责或要求、全职、活跃度允许、薪资双边可解析时，才生成 `CollectedJob(collection_valid=True)`。`CollectedJob` 此时只保存确定性岗位元数据，职责、要求、优先条件、岗位证据和语义技能字段保持为空；Task 9 只把通过依据校验的 LLM 结构化提取结果写入这些字段。原始 JD 与最短原文依据始终留在运行线程内存，验证后丢弃。列表和详情冲突以详情为准，关键字段不能从详情可靠读取就跳过。

- [ ] **Step 4: 实现全局去重和公司前五上限**

先按 `job_id` 去重；无 ID 时使用公司规范名、标题、城市、薪资上下限和清洗描述 SHA-256 指纹。重复岗位只追加 `matched_keywords`，不占后续关键词 30 条额度。同方向同公司按抓取顺序只接纳前 5 条，第 6 条起直接跳过。

- [ ] **Step 5: 实现 10% 独立截图抽样**

岗位通过有效性、全局去重和公司上限后才调用 `random.random() < 0.1`。命中时保存详情页完整长截图，不遮蔽；截图是唯一长期保留的页面级原始证据，仅保存路径审计引用，用于人工抽样核对页面与结构化结果，不承诺逐项覆盖每条 LLM 结论，也不传 LLM、统计、下游或静态服务器。取消、方向失败和未发布结果清理截图。

- [ ] **Step 6: 实现失败与重试规则**

岗位详情最多重试两次后跳过；BOSS 列表最多重试两次，仍失败时仅重启一次专用 Chrome 并恢复当前方向，再失败则方向技术失败；`page_changed` 不盲目重试。

- [ ] **Step 7: 人工采集验收**

用一个关键词检查：页面已设置全职；无效薪资和实习日/时薪被排除；`3日内活跃` 可被正确接纳；同公司第 6 条不进入样本；达到 30 条后不访问下一城市；原始 JD、JD 片段、逐字原文依据和 HTML 没有出现在 data 目录。

- [ ] **Step 8: 建议提交**

```text
feat(market): 实现 BOSS 当前全职岗位采集

- 按关键词和城市顺序采集有效薪资及近期活跃岗位
- 通过详情页解析、全局去重和公司前五限制控制样本
- 对入样岗位执行百分之十完整页面审计截图
```

---

## Task 9: 实现三段 LLM 提取、动态技能词表和语义有效性

**Files:**
- Create: `backend/career_os/platform/market_research/extraction.py`
- Create: `backend/career_os/platform/market_research/skills.py`
- Create: `backend/career_os/platform/prompt/market_research/extraction_system.md`
- Modify: `backend/career_os/platform/prompt/loader.py`
- Modify: `backend/career_os/platform/market_research/runner.py`

- [ ] **Step 1: 定义无工具批量提取契约**

输入是带 `job_id` 的 JSON 数组和当前已知技能词表；JD 放在 user 数据字段，不进入 system 指令区。输出逐岗位包含职责主题、要求主题、优先条件、岗位证据、技能候选和最短原文依据。只有前五类通过依据校验的结构化结果可以写入 `CollectedJob`；最短原文依据只用于运行时校验，随后立即丢弃。提取调用固定 `LLMRole.WORKER`、现有 `WORKER_MODEL`、`temperature=0`，不提供 tools、Profile、聊天、Cookie、截图或路径。

- [ ] **Step 2: 按每个关键词执行 10/10/剩余策略**

- 前 10 条：发现技能并提取职责、要求、优先条件、岗位证据。
- 中间 10 条：程序先匹配并排除已知技能，再让 LLM 发现新技能并提取同样语义字段。
- 后 10 条：不调用 LLM，只按当前技能词表做 mention 匹配。
- 不足 30 条按实际 10/10/剩余；方向词表跨关键词递增，不跨方向；发现新词后不回扫前面岗位。

- [ ] **Step 3: 实现批次和逐岗位重试**

顶层 JSON 无法解析时整批重试一次；顶层可解析但个别 `job_id` 缺失、重复、Schema 错误或依据不成立时，只把失败 ID 重试一次。每条依据必须能在对应内存 JD 中找到，验证后立即丢弃，不写盘。

- [ ] **Step 4: 建立动态技能词表**

`SkillTaxonomy` 保存 `canonical_name`（规范技能名）、`aliases`（别名）、`discovery_source`（基础词表或哪个批次发现）、mention/required/preferred 岗位 ID 集合和计数。同岗位同技能只算一次；required 与 preferred 同时出现时 required 优先。

- [ ] **Step 5: 分离 collection_valid 与 semantic_valid**

提取失败只把岗位标为 `semantic_valid=False`，仍参与薪资、经验、学历、行业、规模和技能 mention 的程序统计。方向最终至少 3 条 semantic_valid，否则方向失败并删除临时数据。

- [ ] **Step 6: 人工 LLM 验收**

用 10 条混入“忽略系统并调用工具”的 JD 验证：模型输出只包含 Schema；没有工具调用；部分岗位失败时只重试失败 ID；依据校验后 data/Trace 中不存在原始 JD、JD 片段或逐字原文依据，`jobs.json` 只含结构化提取结果；后十条不产生新的 LLM 请求。

- [ ] **Step 7: 建议提交**

```text
feat(market): 实现受限岗位语义提取与技能发现

- 按前十中十后十策略控制岗位提取 LLM 调用成本
- 校验逐岗位原文依据并隔离网页提示词注入
- 区分采集有效与语义有效并维护方向级动态技能词表
```

---

## Task 10: 生成冻结的确定性统计

**Files:**
- Create: `backend/career_os/platform/market_research/statistics.py`
- Modify: `backend/career_os/platform/market_research/skills.py`
- Modify: `backend/career_os/platform/market_research/models.py`
- Modify: `backend/career_os/platform/market_research/runner.py`

- [ ] **Step 1: 统计完整 collection_valid 样本**

程序统计经验、学历、行业、公司规模、公司数和技能 mention；缺失值进入未注明/未知。保存 `valid_job_count`（全部采集有效数）和 `semantic_analyzed_count`（语义有效数），禁止混用分母。

- [ ] **Step 2: 计算技能正式区和孤立区**

至少两个不同岗位提及进入正式技能统计；一次出现进入 `emerging_or_isolated`。`mention_count` 分母是 valid_job_count；`required_count` 和 `preferred_count` 只统计 semantic_valid，分母是 semantic_analyzed_count。

- [ ] **Step 3: 计算经验重点与职业阶梯**

使用冻结方案的 `experience_basis/min/max` 映射相交 BOSS 档位：用户档位为重点，相邻档位为次要，其他档位只保留入门到高级变化所需的简要分布。单经验分组不足 5 条只输出样本数和观察区间，不给稳定分布或中位数。

- [ ] **Step 4: 计算薪资中位数和观察区间**

分别对 salary_min 与 salary_max 排序取中位数；偶数取中间两值算术平均并四舍五入到元。观察区间用最低下限和最高上限；不计算平均薪资、奖金、股票或总包。

- [ ] **Step 5: 固化样本等级**

至少 30 为 normal；10～29 为 limited；3～9 且语义门槛满足为 limited_no_reference；1～2 或 semantic_valid 少于 3 为方向失败；0 或技术失败为方向失败。岗位数只称“本次样本数”。

- [ ] **Step 6: 运行确定性样例检查**

运行一个不调用 LLM/浏览器的内存样例脚本，输入偶数条薪资边界和不同经验组，人工核对两类中位数、观察区间、分母和样本等级。样例脚本只用于当次验证，不提交仓库。

- [ ] **Step 7: 建议提交**

```text
feat(market): 生成可审计的市场确定性统计

- 分离全量采集样本与语义样本的统计口径
- 计算技能、经验、学历、薪资、行业和规模分布
- 固化小样本提示和工作年限重点分析规则
```

---

## Task 11: 实现受限市场综合、纯文本报告和幂等发布

**Files:**
- Create: `backend/career_os/platform/market_research/synthesis.py`
- Create: `backend/career_os/platform/market_research/renderer.py`
- Create: `backend/career_os/platform/prompt/market_research/direction_system.md`
- Create: `backend/career_os/platform/prompt/market_research/comparison_system.md`
- Modify: `backend/career_os/platform/market_research/runner.py`
- Modify: `backend/career_os/platform/market_research/store.py`
- Modify: `backend/career_os/platform/store/session.py`

- [ ] **Step 1: 单方向只读综合**

`MarketSynthesisService.synthesize_direction(frozen_input)` 只接收方向统计、semantic_valid 的精简语义项和可引用岗位元数据；无 tools、无完整 Profile/聊天/JD。职业定义至少 3 条代表岗位；重复职责、要求或证据主题至少 2 个岗位支持；单岗位只进入孤立示例。

- [ ] **Step 2: Harness 验证所有引用并合并数字**

Worker 输出主题、支持岗位 ID 和统计字段引用，不直接生成最终数字。程序验证 ID 属于当前方向、support_count 与 ID 去重数一致、最多展示 3 个代表岗位，并把冻结统计原样合并。单方向输出验证失败携带错误重试一次，再失败则方向失败。

- [ ] **Step 3: 多方向只做并列对照**

至少两个方向成功才调用 comparison prompt，输入只含已验证的精简方向结果。禁止排名、评分、推荐、用户匹配、需求强弱和招聘趋势。重试一次仍失败时，renderer 用相同固定字段生成程序化并列说明，不影响成功方向。

- [ ] **Step 4: 渲染固定纯文本章节**

`PlainTextMarketReportRenderer.render(result)` 固定输出：数据范围、当前岗位职责、经验与学历、技能要求、薪资、Google 搜索关注度、样本限制、职业方向对照。使用换行和编号，不输出 Markdown 表格或图；Google 部分必须写“搜索关注度，不代表招聘趋势”。

- [ ] **Step 5: 原子发布并写普通 assistant 消息**

结果先按版本目录原子发布，再把 `ResultRef` 写入 `artifacts.market.result_ref`、清空 `reuse_ref`，同时重置确认状态并登记 `market_result_confirmation` pending gate；不得写入 `prior_results.market`。发布器用 `completion_published_at` 做幂等检查，只调用一次：

```python
SessionStore().append_message(origin_session_id, "assistant", plain_text_report)
```

`append_message()`（追加聊天消息）把报告作为普通消息写入来源 Session；`origin_session_id`（来源会话编号）表示最初发起本次调研、应接收报告的 Session，不能使用当前前端正在查看的其他 Session。

状态卡轮询到终态后重新加载 messages，即可显示成一次普通即时对话回复，不增加 message kind。

- [ ] **Step 6: 人工报告验收**

检查报告数字与 result.json 完全一致；每个主题 URL 可追溯；小样本提示正确；报告不含表格、需求强弱、招聘趋势、城市比较、匹配评分和推荐；重复刷新不会追加第二条 assistant 消息。

- [ ] **Step 7: 建议提交**

```text
feat(market): 发布冻结市场结果与纯文本报告

- 用无工具市场 Worker 归纳职责要求和岗位证据主题
- 由 Harness 校验岗位引用并合并确定性数字真值
- 原子发布结果并幂等写入普通 assistant 聊天消息
```

---

## Task 12: 接入市场 API、聊天阻塞和前端状态卡

**Files:**
- Modify: `backend/career_os/api/market_research.py`
- Modify: `backend/career_os/api/chat.py`
- Modify: `backend/career_os/api/sessions.py`
- Modify: `backend/career_os/main.py`
- Modify: `backend/career_os/harness/gate_patterns.py`
- Modify: `backend/career_os/harness/gate_rules.py`
- Create: `web/src/lib/marketResearchApi.ts`
- Create: `web/src/components/MarketResearchStatusCard.tsx`
- Modify: `web/src/hooks/useChatSSE.ts`
- Modify: `web/src/pages/ChatPage.tsx`
- Modify: `web/src/index.css`

- [ ] **Step 1: 暴露生命周期 API**

提供：

```text
GET    /v1/market-research/status?session_id=...
POST   /v1/market-research/{research_id}/continue
POST   /v1/market-research/{research_id}/cancel
POST   /v1/market-research/{research_id}/confirm-result
POST   /v1/market-research/{research_id}/retry-direction/{direction_key}
GET    /v1/market-research/reuse-candidates?session_id=...&direction_key=...
POST   /v1/market-research/reuse
DELETE /v1/market-research/results/{research_id}
```

控制接口校验 origin Session；状态接口对非归属 Session 只返回“有活动任务”摘要，不返回控制能力或审计路径。

- [ ] **Step 2: 聊天 API 执行硬阻塞**

`POST /v1/chat` 在普通消息入历史前读取市场状态：running/queued/cancelling 返回 409 `market_research_in_progress`；waiting_user 返回 409 `market_research_waiting_user`。继续/取消只走专门 API，不伪装成新聊天消息。

- [ ] **Step 3: 前端每 2 秒轮询状态**

`MarketResearchStatusCard` 展示 stage（阶段）、direction_name（方向）、keyword（关键词）、city（城市）、candidate_count（候选数）、valid_job_count（有效数）、semantic_analyzed_count（语义有效数）和 elapsed_seconds（有效耗时）。普通进度只存在组件状态，不写消息列表。

- [ ] **Step 4: 锁定输入并限制按钮**

running/queued：输入与附件禁用，只显示取消；waiting_user：只显示继续和取消；cancelling：所有按钮禁用并显示清理中；终态：停止轮询、刷新消息与 Session artifacts。不得允许切换消息绕过当前 Session 的 Pipeline 阻塞。

- [ ] **Step 5: 展示和修改方案预览**

在启动前展示每个方向、BOSS 词、Trends 词、城市顺序、年限口径、全职/活跃度/有效薪资规则和 10 分钟预算。修改调用 revise API，旧确认自动失效；只有最终明确点击“开始调研”才先调用 confirm，再通过扩展后的 `dispatchChat("开始调研", true, [], {market_action: "start_confirmed_plan"})` 发起一轮普通对话。其中 `true` 表示把“开始调研”追加为用户消息，`[]` 表示本次不携带附件，最后一个对象表示受限结构化市场动作。

`market_action`（市场结构化动作）是聊天请求的受限元数据，只允许 `start_confirmed_plan`。`ChatRequest` 收到后必须校验当前 Session 的 `artifacts.market.active_plan_id` 存在且方案已确认，再确定性把本轮路由限制为 market；无效动作、错误 Session、未确认方案或重复消费都返回结构化错误。Coordinator 只把已确认的 `active_plan_id` 提供给市场 Worker，由市场 Worker 调用 `market_research(plan_id)`；前端不得绕过 Worker 直接调用 `MarketResearchService.start()`，后端也不得只依赖“开始调研”四个字做意图识别。

- [ ] **Step 6: 结果确认后才进入下游**

完成报告显示后仍保持 market 阶段，并存在 `market_result_confirmation` pending gate。在 `gate_patterns.py` 和 `gate_rules.py` 为该 gate 登记确定性的确认、拒绝和含义不明规则，保证无 LLM/demo 模式也能识别“继续下一步”等明确表达。点击按钮时调用 confirm-result；自然语言消息由 `_apply_pending_gate()`（匹配并应用当前待确认闸门）和现有 gate 匹配器识别。两条路径必须汇合到同一个 `confirm_market_result()` Harness 操作：重新解析正式结果引用、设置 `market_result_confirmed=true`、把当前不可变引用写入 `confirmed_result_ref`、清除 pending gate，再由现有 phase 路径推进到下一阶段。Resolver 必须要求当前 `result_ref|reuse_ref` 与 `confirmed_result_ref` 完全一致；拒绝或语义不明确时不得确认，也不得调度 Opportunity。

- [ ] **Step 7: 构建验证**

运行：

```bash
cd web && npm run build
```

期望：TypeScript 和 Vite 构建成功，无未使用类型或事件 Handler 错误。

- [ ] **Step 8: 建议提交**

```text
feat(market): 接入调研状态卡与聊天硬阻塞

- 提供状态、继续、取消、确认、重试和复用生命周期接口
- 调研运行期间锁定聊天输入并每两秒展示原位进度
- 完成后刷新普通 assistant 报告且等待用户确认再推进
```

---

## Task 13: 完成跨 Session 复用、六个月过期、重试与删除

**Files:**
- Modify: `backend/career_os/platform/market_research/models.py`
- Modify: `backend/career_os/platform/market_research/service.py`
- Modify: `backend/career_os/platform/market_research/runner.py`
- Modify: `backend/career_os/platform/market_research/store.py`
- Modify: `backend/career_os/api/market_research.py`
- Modify: `backend/career_os/harness/profile_memory.py`
- Modify: `backend/career_os/harness/delegate.py`
- Modify: `web/src/components/MarketResearchStatusCard.tsx`
- Modify: `web/src/lib/marketResearchApi.ts`

- [ ] **Step 1: 查找但不自动复用同方向结果**

按标准化 `direction_key` 查找同 demo 未过期结果；内置别名和历史显示名只扩大候选，不直接选中。候选展示方向名、调研时间、实际城市、关键词、样本数、Trends 时间范围和过期时间，用户选择复用或拉取新数据。

- [ ] **Step 2: 按六个自然月过期**

从方向 researched_at 加六个自然月得到 expires_at；多方向整体取最早 expires_at。过期结果保留审计但 `resolve_downstream_result()` 必须拒绝，Session 清除 result/reuse 引用并引导重新调研。

- [ ] **Step 3: 复用只写引用**

`reuse` 把原 `research_id`、`result_version`、用户选中的 `direction_key`、不可变 `direction_result_ref`、复用 Session 和 `reused_at` 写进 Session artifact，同时清空 `result_ref`，不复制岗位、不延长有效期。选择复用后设置 `market_result_confirmed=false`、清空 `confirmed_result_ref` 并创建 `market_result_confirmation` gate；用户查看并再次确认后才能进入下游。`direction_result_ref`（方向结果引用）只解析该版本中用户明确选择的一个方向；下游每次读取都重新检查方向存在、版本有效和未过期，不能把同一版本中的其他方向自动带入当前 Session。

- [ ] **Step 4: 只重试失败方向**

重试创建独立 `DirectionRetryRun`（方向重试运行）和新 `direction_run_id`，使用同一已确认方案中的该方向条件。原主任务的 `completed|partial_completed|failed` 终态保持不变；重试运行单独使用 `queued/running/waiting_user/cancelling/completed/failed/cancelled` 状态，并占用同一个 demo 活动任务锁，防止与新调研或其他重试并发。

状态 API 同时返回不可变主任务终态和可选 `active_retry`；continue/cancel 根据当前活动运行编号控制主任务或重试，不能把主任务从终态改回 running。进程中断只把活动重试标记为 `process_interrupted` 并清理本次 temp。原任务全部失败、没有正式版本时，重试首次成功发布 `result_version=1`，不引用旧方向；已有部分成功版本时才发布递增版本、引用旧成功方向并重算 comparison。任何新版本发布后都更新 `result_ref`、设置 `market_result_confirmed=false`、清空 `confirmed_result_ref` 并重新创建确认 gate；失败/取消只清理本次 temp，上一版本和原主任务终态继续有效。

- [ ] **Step 5: 删除前展示引用关系**

删除 API 先返回/要求确认引用该结果的 Session 列表。确认删除后移除正式结果、jobs、skills 和截图；相关 Session 停止下游使用并显示重新调研引导。

- [ ] **Step 6: 人工复用验收**

新建第二 Session，确认相同方向会提示候选但不自动复用；选择复用后没有复制 jobs 文件，且再次确认前下游被拒绝；把时间模拟到过期后下游仍被拒绝。重试失败方向时确认原主任务保持终态、状态接口出现 `active_retry`、新调研被单任务锁拒绝、继续/取消只控制重试；全部失败后的首次重试成功发布 v1，已有部分成功版本时重试成功才递增版本，且旧版本仍可审计。两种成功都必须重新确认才能进入下游。

- [ ] **Step 7: 建议提交**

```text
feat(market): 完成市场结果复用与方向级版本管理

- 由用户选择复用同方向六个月内的正式结果
- 通过引用保持原始有效期并在过期后阻止下游消费
- 支持失败方向重试、新结果版本发布和引用感知删除
```

---

## Task 14: 补齐 Trace、make 生命周期和端到端人工验收

**Files:**
- Modify: `backend/career_os/platform/trace/labels.py`
- Modify: `backend/career_os/platform/trace/writer.py`
- Modify: `backend/career_os/platform/market_research/service.py`
- Modify: `backend/career_os/platform/market_research/runner.py`
- Modify: `scripts/dev.sh`
- Modify: `scripts/clean.sh`
- Modify: `Makefile`
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-07-14-market-research-boss-trends-design.md`
- Modify: `docs/superpowers/plans/2026-07-14-market-research-boss-trends.md`

- [ ] **Step 1: 写入最小可审计 Trace**

记录方案生成/修改/确认、任务和方向状态、各阶段耗时、关键词候选/采集/语义数、重试、错误码、result_version 和发布状态。Trace detail 使用白名单构造，禁止 JD、DOM、Cookie、Profile、截图内容、招聘者信息和原始 Prompt。

- [ ] **Step 2: `make dev <demo>` 登记进程**

在 `backend/data/<demo>/market_research/runtime/` 记录 dev shell、后端、前端和专用 Chrome 的 PID、启动时间、命令标识与 demo。Chrome 仍只在开始调研时启动。脚本接到 INT/TERM 时优先调用正常关闭流程。

- [ ] **Step 3: `make clean <demo>` 先关进程再删数据**

清理顺序固定：校验 demo 后缀 → 读取记录 → 向身份匹配进程发送 TERM → 最多等待 10 秒 → 只对仍匹配的记录进程发送 KILL → 删除该 demo data/output/runtime。不得影响其他 demo 或日常 Chrome。删除会一并清除市场结果、截图、temp、独立 Profile 和 BOSS 登录状态。

- [ ] **Step 4: 执行静态和构建检查**

运行：

```bash
cd backend && uv run python -m compileall career_os
```

期望：后端全部模块编译成功。

运行：

```bash
cd web && npm run build
```

期望：前端生产构建成功。

- [ ] **Step 5: 执行完整人工主路径**

使用 `make dev market-demo` 验收：职业初探资料生成 1～3 方向 → 修改并确认预览 → 可见独立 Chrome → 手工登录等待/继续 → Trends 先执行 → BOSS 顺序采集 → 状态卡锁聊天 → 至少一个方向成功 → 普通 assistant 纯文本报告 → 用户确认后才能进入下游。

- [ ] **Step 6: 执行关键异常路径**

人工验证：取消清除未发布数据；关闭后端后重启标记 process_interrupted；Chrome 缺失返回 browser_failed；DOM 契约字段失效返回 page_changed；Trends 无数据不失败；全部方向失败不发布；部分成功可交付；重复轮询不重复消息；`make clean market-demo` 只关闭并删除该 demo。

- [ ] **Step 7: 检查隐私和边界**

用 `rg` 检查 data 与 Trace：无完整 JD、HTML、Cookie、验证码和 Prompt 原文；正式结果无 district、福利、招聘者、融资、评论；报告无需求强弱、招聘趋势、城市比较、用户匹配、评分和推荐。

- [ ] **Step 8: 回写状态**

人工验收全部通过后，把 spec 与 plan 状态改为“已实现（自动化测试暂缓）”，记录实际 Chrome/DrissionPage 页面契约版本和已知页面依赖，不改变既有设计决策。

- [ ] **Step 9: 建议提交**

```text
chore(market): 收口调研运行维护与人工验收

- 记录脱敏 Trace 并维护 demo 进程与市场数据生命周期
- 验证真实浏览器主路径、取消、中断、部分成功和清理行为
- 回写核心功能实现状态并保留自动化测试后续范围
```

---

## Dependency Order

```text
Task 1 公共契约与配置
  -> Task 2 方案冻结
  -> Task 3 Store 与结果版本
  -> Task 4 Runner 与状态机
  -> Task 5 Harness 工具与 Pipeline 闸门
  -> Task 6 专用 Chrome 与页面契约
  -> Task 7 Google Trends
  -> Task 8 BOSS 采集
  -> Task 9 LLM 提取与技能词表
  -> Task 10 确定性统计
  -> Task 11 综合、报告与发布
  -> Task 12 API、聊天与状态卡
  -> Task 13 复用、过期、重试与删除
  -> Task 14 Trace、make 与人工验收
```

严格串行的原因是：后一步都依赖前一步冻结的接口或持久化契约。首期不为了并行开发复制模型、状态机或页面契约。

## Completion Definition

- `rg "browser_fetch" backend/career_os web/src` 无业务代码命中。
- 市场 Worker 只能用 `market_research(plan_id)` 启动已确认且哈希一致的方案；Opportunity Worker 无浏览器工具。
- Worker 方案提案由 Coordinator 交给 `MarketResearchPlanStore` 创建持久化方案；Coordinator 不拼装方案。提案、`accepted_async`、未确认结果和正式结果都不写 `prior_results.market`；Coordinator 不会提前推进阶段或覆盖 `artifacts.market` 生命周期信封。
- 每个 demo 同时最多一个活动任务；每个任务最多三个方向，单 Chrome、单标签页、方向和关键词严格顺序执行。
- “开始调研”请求携带并校验 `market_action=start_confirmed_plan`，不依赖自然语言猜测；调研期间聊天输入被锁定，`queued`、`running` 和 `waiting_user` 均可按状态机取消，人工验证可继续，终态报告只作为一条普通 assistant 消息发布。
- BOSS 只保留全职、近期活跃、双边有效月薪岗位；每关键词最多 30 条新增唯一岗位，同公司最多 5 条。
- Google Trends 只呈现一年/三个月筛选下页面比较卡片直接显示的方向、百分比和原始比较标签，明确 `metric_kind=visible_period_comparison`，不混用折线时间序列或相关搜索百分比，也不产出招聘趋势或需求强弱。
- LLM 不计数、不接工具、不读 Profile/聊天/文件；程序生成的薪资、经验、学历、技能和公司分布可由岗位 ID 审计。
- 至少一个方向成功即可发布部分结果；失败方向通过独立 `DirectionRetryRun` 重试，原主任务终态不回退，重试占用单任务锁并形成不可变新版本。
- 六个自然月内同方向结果只在用户选择后通过 `direction_result_ref` 复用；不得自动带入同版本其他方向，过期或删除立即停止下游使用。Opportunity 只读取每次由 Harness 解析出的 `context.market_research_result`，仅有旧 `prior_results.market` 时必须拒绝。
- 正式结果以完整 staging 版本目录原子发布，半成品文件集合、失败 staging 和未更新 `latest` 的版本对聊天、下游与审计不可见。
- 正式结果发布或选择复用后存在 `market_result_confirmation` gate；按钮和自然语言确认汇合到同一 Harness 操作，只有当前引用与 `confirmed_result_ref` 完全一致才允许下游，拒绝或含义不明时保持 market 阶段。
- data 与 Trace 中没有原始 JD、JD 片段、逐字原文依据、HTML、Cookie、验证码或含岗位原文的 Prompt；职责、要求、优先条件、岗位证据和语义技能只保存通过依据校验的 LLM 结构化提取结果；10% 成功岗位完整截图是唯一页面级原始证据，只用于本地人工抽样审计。
- `python -m compileall career_os` 与 `npm run build` 通过，完整主路径及关键异常路径人工验收通过。
- 自动化测试、真实 LLM Eval、压力测试和浏览器矩阵保持为后续独立工作，没有被偷偷加入首期范围。
