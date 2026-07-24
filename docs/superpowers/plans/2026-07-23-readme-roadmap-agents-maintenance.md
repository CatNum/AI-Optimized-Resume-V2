# README、Roadmap 与 AGENTS.md 维护 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Use checkbox (`- [ ]`) syntax to track progress and stop if a documented fact cannot be verified.

**Goal:** 在不修改业务代码、不丢失当前 README 信息的前提下，将根 README 重构为面向技术面试官和项目评审者的 Career OS 项目入口，同时建立 `docs/roadmap/` 版本文档体系与遵循 agents.md 开放格式的根级 `AGENTS.md`。

**Architecture:** 本计划采用“先快照、再承接、后重构、最后验真”的文档迁移顺序。先在根目录创建 `README.before-maintenance.md` 保存当前 README，再建立 roadmap 并迁移原 README 后半部分的规划信息，确保内容已有稳定去向；随后创建根 `AGENTS.md` 固化持续维护规则；再按确认的十章顺序重构 README，保持实机演示原顺序并加入目录树、产品链路、架构图和工程证据；最后先暂存新增目标文件，再通过快照人工对照、链接、截图、Markdown、真实测试快照和 Git diff 完成验收。

**Tech Stack:** Markdown、Mermaid、Shell、Make、pytest、TypeScript/Vite 构建、Git

**Design SSOT:** [README、Roadmap 与 AGENTS.md 维护设计规格](../specs/2026-07-23-readme-roadmap-agents-maintenance-design.md)

**Status:** 待实现

---

## Global Constraints

- 只允许修改或新增文档文件；不得修改 Python、TypeScript、Shell、JSON、环境配置或依赖锁文件。
- 允许的目标文件固定为：
  - `README.md`
  - `AGENTS.md`
  - `docs/roadmap/README.md`
  - `docs/roadmap/产品规划与技术演进.md`
  - `docs/roadmap/v2.1.md`
  - `docs/roadmap/v2.2.md`
- 允许在仓库根目录临时创建 `README.before-maintenance.md` 作为迁移快照；创建前必须确认同名文件不存在，快照不得暂存，人工对照完成后删除。
- 实施时不得修改本 Plan、Design SSOT、历史 PRD、历史架构文档或其他既有文档；发现错误只在目标文件中标注边界，另行提出修订建议。
- 保留用户已有未跟踪文件和无关改动，不暂存、不覆盖、不删除；只允许暂存本计划新建的 `AGENTS.md` 和四份 roadmap 文档。
- 强类型 Worker 调用和全局失败机制对应的四份 Spec/Plan 当前作为 `v2.2` 的本地依赖来源保留，但不纳入本计划的目标文件或暂存范围；若执行时仍未被 Git 跟踪，记录为“由用户后续加入版本库”的临时交付边界。
- 根 README 的一级章节顺序必须与 Design SSOT 完全一致。
- 实机演示内部顺序保持不变；原 14 张截图引用、截图说明、两次独立任务说明和补充截图目录链接必须保留。
- README 仓库结构只展示目录，不展示文件；选择性展开且最深五级。
- 先创建 roadmap 承接原规划信息，再删除 README 中的长篇规划原文；禁止先删后迁移。
- 当前产品文档版本为 `v2.1`，状态为“开发中”；`v2.2` 状态为“规划中”。
- 不修改 `backend/pyproject.toml` 和 `web/package.json` 中现有的包版本 `0.1.0`；本计划只维护产品文档版本。
- 旧 Spec、Plan、PRD 和架构文档中的 `v0.1` 是历史基线，不机械替换。
- `v2.2` 只承诺强类型 `WorkerInvocation`、`ExecutionPlan`、全局失败机制和跨模块系统级回归主线。
- 测试失败只记录，不修复；缺少 LLM Key 或外部依赖时如实记录未执行、跳过或失败。
- 不读取、打印或提交 `backend/.env` 中的密钥值。
- 不安装新的 Markdown 工具、测试依赖或文档生成器。
- 不创建 Git commit、不推送、不创建 Pull Request；按用户确认，只在新文件检查前暂存 `AGENTS.md` 和四份 roadmap 文档。

## Target File Structure

```text
.
├── AGENTS.md
├── README.md
└── docs/
    └── roadmap/
        ├── README.md
        ├── 产品规划与技术演进.md
        ├── v2.1.md
        └── v2.2.md
```

文件职责：

- `README.md`（人类项目入口）：说明产品价值、运行方式、真实演示、架构证据、测试结果与版本边界。
- `AGENTS.md`（编码 Agent 项目指南）：说明环境、架构边界、测试、安全、README 和 roadmap 的强制维护规则。
- `docs/roadmap/README.md`（版本索引）：说明当前版本、下一版本、版本号和状态规则。
- `docs/roadmap/产品规划与技术演进.md`（跨版本规划）：承接未确定版本归属的需求、长期愿景和设计思考。
- `docs/roadmap/v2.1.md`（当前版本）：区分已完成、进行中、证据、已知边界和非目标。
- `docs/roadmap/v2.2.md`（下一版本）：记录已确认的可靠性升级目标、范围、验收和非目标。

---

## Task 1: 建立实施前事实基线和内容迁移清单

**Files:**

- Read: `README.md`
- Read: `Makefile`
- Read: `backend/pyproject.toml`
- Read: `web/package.json`
- Read: `.agent/README.md`
- Read: `docs/architecture/00-架构总览.md`
- Read: `docs/architecture/03-系统分层.md`
- Read: `docs/architecture/05-API与流式协议.md`
- Read: `backend/tests/eval/CASES.md`
- Read: `docs/superpowers/specs/2026-07-23-readme-roadmap-agents-maintenance-design.md`

- [ ] **Step 1: 检查工作区并保护用户改动**

运行：

```bash
git status --short
git diff -- README.md
```

期望：

- 明确记录所有已有修改和未跟踪文件；
- 若 `README.md` 在执行前已有新改动，先重新读取并把新增信息补入迁移清单，不覆盖用户改动；
- 不操作与本计划无关的 `CONTEXT.md`、其他 Spec、其他 Plan 或用户文件。

- [ ] **Step 2: 在根目录创建 README 完整快照**

运行：

```bash
test ! -e README.before-maintenance.md
cp README.md README.before-maintenance.md
shasum -a 256 README.md README.before-maintenance.md
```

期望：

- 创建前同名文件不存在，避免覆盖用户文件；
- 两个文件的 SHA-256 完全一致；
- `README.before-maintenance.md` 只用于最终人工迁移对照，不暂存、不提交。

- [ ] **Step 3: 核对 README 基线结构**

运行：

```bash
wc -l README.md
rg -n '^#{1,3} ' README.md
rg -n 'docs/assets/screenshots/' README.md
```

基于 Design SSOT 的预期基线：

- README 约 403 行；
- 包含原“文档索引、当前状态、实机演示、快速开始、市场调研主路径、仓库结构、测试、规划、优化点、todo、核心、产品演进、示例”等部分；
- 实机演示引用 14 张截图。

若执行时基线已经变化，以实际工作区为准更新迁移判断，但不得擅自改变已确认的目标结构。

- [ ] **Step 4: 固定 14 张现有截图引用集合**

现有 README 必须保留以下引用：

```text
docs/assets/screenshots/00-project-startup.png
docs/assets/screenshots/13-new-session.png
docs/assets/screenshots/12-career-planning.png
docs/assets/screenshots/14-profile-intake.png
docs/assets/screenshots/01-market-research-gate.png
docs/assets/screenshots/04-market-research-progress.png
docs/assets/screenshots/05-boss-job-collection.png
docs/assets/screenshots/06-market-fit-summary.png
docs/assets/screenshots/07-jd-fit-analysis.png
docs/assets/screenshots/08-resume-strategy-confirmation.png
docs/assets/screenshots/09-resume-optimization-entry.png
docs/assets/screenshots/10-resume-generation.png
docs/assets/screenshots/11-resume-output.png
docs/assets/screenshots/15-environment-cleanup.png
```

逐个运行或批量确认文件存在。`02-market-research-report.png` 和 `03-market-research-diagnostics.png` 虽然存在于截图目录，但不是当前 README 的既有引用，本计划不要求新增。

- [ ] **Step 5: 核对需要保留的运行命令和边界**

从 README 和 Makefile 核对并记录：

```text
make install
make dev blank
make dev test
make dev demo
make dev sandbox
make clean demo
make clean test
./scripts/clean.sh blank
make market-check
(cd backend && uv sync)
(cd backend && uv run uvicorn career_os.main:app --reload --port 18080)
(cd web && npm install && npm run dev)
BACKEND_PORT=19080 FRONTEND_PORT=16173 make dev blank
```

同时保留：

- 前端默认地址 `http://localhost:15173`；
- 后端默认端口 `18080`；
- 数据和输出后缀目录；
- `profile.json` 空结构说明；
- `localStorage.removeItem('session_id')`；
- 进程身份校验、TERM、最长 10 秒等待、KILL 和隔离清理边界。

- [ ] **Step 6: 核对本地链接并记录已有断链**

重点检查当前文档索引中的每个路径：

```bash
test -e 'docs/prd/00. 职业规划 Agent PRD.md'
test -e docs/architecture/00-架构总览.md
test -e docs/简历项目描述.md
test -e .agent/README.md
test -e backend/tests/eval/CASES.md
test -e docs/参考文档.md
```

若 `docs/简历项目描述.md` 仍不存在：

- 不创建与本计划无关的简历文档；
- 不静默删除“简历项目描述”主题；
- 在新文档索引中保留该主题并标注“待补充”，不生成失效链接。

- [ ] **Step 7: 按 Design SSOT 第 6 章逐段确认迁移目的地**

确认每个原章节都有唯一主要去向：

```text
产品与状态摘要            → README 第 1、7、10 章 + v2.1
启动和环境说明            → README 第 2 章
实机演示                  → README 第 3 章
仓库结构                  → README 第 4 章
市场调研主路径            → README 第 5 章
架构说明                  → README 第 6、7 章
测试                      → README 第 8 章 + v2.1 验证证据
文档索引                  → README 第 9 章
规划/优化点/todo          → 产品规划与技术演进 + v2.1/v2.2
核心/产品演进/示例        → 产品规划与技术演进
```

完成本 Task 前不修改任何目标文件；唯一允许的新文件是已核验哈希的临时 `README.before-maintenance.md`。

---

## Task 2: 先创建 Roadmap 文档并承接原规划信息

**Files:**

- Create: `docs/roadmap/README.md`
- Create: `docs/roadmap/产品规划与技术演进.md`
- Create: `docs/roadmap/v2.1.md`
- Create: `docs/roadmap/v2.2.md`
- Reference: `README.md`
- Reference: `docs/superpowers/specs/2026-07-23-typed-worker-invocation-execution-plan-design.md`
- Reference: `docs/superpowers/specs/2026-07-23-global-failure-mechanism-design.md`
- Reference: `docs/superpowers/plans/2026-07-23-typed-worker-invocation-execution-plan.md`
- Reference: `docs/superpowers/plans/2026-07-23-global-failure-mechanism.md`

- [ ] **Step 1: 创建 roadmap 目录**

运行：

```bash
mkdir -p docs/roadmap
```

目录只承载产品和技术版本路线，不替代 `docs/superpowers/plans/` 的具体实施计划。

- [ ] **Step 2: 创建 roadmap 索引**

`docs/roadmap/README.md` 必须包含：

- 当前版本 `v2.1（开发中）`；
- 下一版本 `v2.2（规划中）`；
- `v2.1 → v2.2 → ... → v3.1` 版本号规则；
- “规划中、开发中、已完成、已归档”四种状态的含义；
- 三份 roadmap 文档入口；
- roadmap 与 Superpowers Spec/Plan 的职责边界；
- 版本状态变更和证据要求。

- [ ] **Step 3: 创建《产品规划与技术演进》**

从原 README 完整迁移：

- “规划”；
- “优化点”；
- “todo”；
- “核心”；
- “产品演进”；
- “示例”。

允许按以下结构重新分类：

```markdown
# 产品规划与技术演进

## 文档定位
## 产品愿景与代际演进
## Harness 与模型边界思考
## 长期候选能力
## 已形成设计、待实施
## 已完成或被替代的历史事项
## 设计示例
```

迁移规则：

- 保留每条独有信息；
- 可以合并重复表述；
- 已完成项标记为历史完成，不混入未来候选；
- 有 Spec 但未实现的事项标记“已形成设计，待实施”；
- 未确认版本归属的事项不进入 `v2.2`；
- 原 Harness 是否应与业务绑定的 Text-to-SQL 示例完整保留。

- [ ] **Step 4: 创建 `v2.1.md`**

使用统一版本模板：

```markdown
# Career OS v2.1

| 属性 | 内容 |
|---|---|
| 状态 | 开发中 |
| 版本目标 | ... |
| 最后更新 | 2026-07-23 |

## 版本范围
## 已完成
## 进行中
## 验收标准
## 验证证据
## 已知边界
## 非目标
## 变更记录
```

内容规则：

- “已完成”只写有代码、运行截图或现有测试支持的能力；
- 测试快照在 Task 8 实际执行后补充；
- 强类型 Worker 调用和全局失败机制放入“进行中”或“已知边界”，不得写成已完成；
- 本地优先、非生产级 SaaS、浏览器依赖和评测边界如实记录；
- 不把包版本 `0.1.0` 改写为产品版本。

- [ ] **Step 5: 创建 `v2.2.md`**

状态固定为“规划中”，版本目标固定为：

> 建立强类型 Worker 调用与全局失败机制，使 Agent 执行从依赖自然语言猜测职责升级为调用契约明确、失败行为一致、执行过程可追踪。

版本范围只包含：

1. `WorkerInvocation`；
2. `ExecutionPlan`；
3. 全局失败机制；
4. 跨模块系统级回归。

解释：

- `WorkerInvocation`（Worker 结构化调用契约）明确 Worker、业务动作、输入、权限和成功条件；
- `ExecutionPlan`（执行计划）明确节点、依赖、顺序和成功条件；
- 全局失败机制统一失败分类、传播、重试、降级、Trace 和用户错误呈现。

非目标明确列出长期记忆索引、简历模板 Skill、Offer 对比、评测 Agent 等未承诺事项。

- [ ] **Step 6: 做 roadmap 内容完整性初检**

运行：

```bash
rg -n '^#|^## ' docs/roadmap/*.md
rg -n 'Multi-Agent|记忆系统|评测 Agent|简历模板|Offer|Harness|Text.*SQL|v2\\.1|v2\\.2' docs/roadmap
```

期望：

- 四份文档结构完整；
- 原 README 的规划主题都能在 roadmap 中定位；
- `v2.2` 没有自动吸收全部 Todo；
- `v2.1` 和 `v2.2` 状态正确。

---

## Task 3: 创建遵循 agents.md 的根级 AGENTS.md

**Files:**

- Create: `AGENTS.md`
- Reference: `Makefile`
- Reference: `backend/pyproject.toml`
- Reference: `web/package.json`
- Reference: `README.md`
- Reference: `docs/roadmap/README.md`
- Reference: `docs/superpowers/specs/2026-07-23-readme-roadmap-agents-maintenance-design.md`

- [ ] **Step 1: 写项目概览和目录边界**

说明：

- Career OS 是本地优先的职业规划 AI Agent；
- Web、FastAPI、ChatOrchestrator、Coordinator、Harness、Worker、平台服务和本地存储的职责；
- FastAPI 直接调用 Coordinator；ChatOrchestrator 只负责单 Session 并发控制和上下文提醒；Coordinator 在需要委托 Worker 或执行 Tool 时进入 Harness；
- `agents`（Agent 模型编排）、`harness`（受控执行约束）、`platform`（通用平台能力）、`.agent/skills`（业务技能包）的含义与作用；
- Worker 互不直接通信，协调者负责分析、派工和合成。

- [ ] **Step 2: 写安装、启动和常用检查命令**

只记录仓库当前真实存在的命令：

```bash
make install
make dev blank
make dev test
make dev demo
make clean demo
make market-check
(cd backend && uv run pytest tests/ -m "not llm" -q)
(cd backend && uv run pytest tests/eval/ -m llm -v)
(cd web && npm run build)
```

每条命令说明用途、工作目录和前提。不得把需要 LLM Key 的命令写成无条件离线检查。

- [ ] **Step 3: 写代码、测试和安全约束**

至少包含：

- 修改代码前先核对 PRD、Spec、当前代码和测试；
- 后端、前端、Skill 和配置修改需要匹配各自测试；
- 不提交 `backend/.env`、运行数据、输出简历、Trace 或用户隐私数据；
- 不把 JD、简历、用户档案和本地会话内容复制进公共文档；
- 测试失败不得被描述为通过；
- 不以计划文档代替当前实现证据。

- [ ] **Step 4: 写 README 和 roadmap 强制维护规则**

完整写入 Design SSOT 第 8.3 和 8.4 节，包括：

- README 十章顺序；
- 实机演示原顺序；
- 仓库树只展示目录且最深五级；
- 架构图按当前代码校准；
- 测试数字绑定日期和命令；
- 信息迁移禁止静默删除；
- 当前实现变化同步检查 `v2.1`；
- 下一版本范围变化同步检查 `v2.2`；
- 未确认事项进入《产品规划与技术演进》；
- 版本完成必须有验收证据；
- 不批量改写历史 `v0.1`。

- [ ] **Step 5: 写 Git 提交信息规则**

规则固定为：

- 中文 Conventional Commit 主信息；
- 主信息之后至少两个具体中文分点；
- 分点说明实际改动和目的；
- 除非用户明确要求，不使用英文提交信息；
- 未经用户要求，不自动 commit。

- [ ] **Step 6: 校验 AGENTS.md 是标准 Markdown**

运行：

```bash
rg -n '^#|^## ' AGENTS.md
rg -n 'make install|pytest|README|roadmap|v2\\.1|v2\\.2|提交' AGENTS.md
```

期望：根 `AGENTS.md` 不依赖自定义 front matter、私有解析器或专有指令格式。

---

## Task 4: 重构 README 第 1 至第 3 章

**Files:**

- Modify: `README.md`
- Reference: `docs/roadmap/v2.1.md`
- Reference: `docs/assets/screenshots/`

- [ ] **Step 1: 重写第一屏产品定位**

使用：

```markdown
# Career OS

可控、可观测、可评测的职业规划 AI Agent。
```

第一章必须说明：

- 产品从职业初探延伸到市场调研、JD 分析和 HTML 简历交付；
- 它不是只做单次 JD 改写；
- “模型负责决策，Harness 负责约束；执行过程可追踪，最终效果可评测”；
- 仓库代号 `AI-Optimized-Resume-V2`；
- 当前产品文档版本 `v2.1（开发中）`；
- 只维护 `main` 的分支策略。

第一屏不写未经验证的测试数量、准确率、生产稳定性或性能收益。

- [ ] **Step 2: 重组快速开始的最短路径**

顺序固定为：

1. Python、uv、Node.js 环境要求；
2. `make install`；
3. 配置 `backend/.env`；
4. `make dev blank`；
5. 访问 `http://localhost:15173`。

说明 `make install`（安装命令）会同步后端和前端依赖，并在缺少时从示例创建 `.env`。

- [ ] **Step 3: 在快速开始后半保留完整运行说明**

保留：

- 四种环境后缀；
- 数据和输出位置；
- 空 `profile.json` 与示例档案边界；
- 清理命令和安全进程终止机制；
- 浏览器旧会话处理；
- 分步启动；
- 端口覆盖；
- `make market-check`。

合并重复命令，但不压缩掉任何独有行为。

分步启动命令必须从项目根目录运行，并使用独立子 Shell，避免前一条命令改变后一条命令的工作目录：

```bash
# 终端 1：后端
(cd backend && uv sync)
(cd backend && uv run uvicorn career_os.main:app --reload --port 18080)

# 终端 2：前端
(cd web && npm install && npm run dev)
```

- [ ] **Step 4: 原顺序迁移实机演示**

将当前实机演示整体移动到第三章，不改变以下顺序：

```text
本地环境启动
建档与职业初探
市场调研执行
JD 分析与策略确认
最终交付
演示收尾
```

保留：

- 原 14 张图片；
- 每张图片的标题和说明；
- “更多运行过程、诊断信息和中间状态截图”链接；
- 主流程来自 `make dev demo`、清理截图来自 `make clean demo3` 的说明。

- [ ] **Step 5: 验证前三章**

运行：

```bash
rg -n '^#|^## |^### ' README.md | sed -n '1,120p'
rg -n 'docs/assets/screenshots/' README.md
rg -c '^!\\[.*\\]\\(docs/assets/screenshots/.*\\)$' README.md
```

期望：

- 前三章顺序正确；
- 图片引用数量仍为 14；
- 实机演示内部顺序不变。

---

## Task 5: 增加多级目录树和四阶段产品主链路

**Files:**

- Modify: `README.md`
- Reference: `.agent/`
- Reference: `backend/career_os/`
- Reference: `backend/tests/`
- Reference: `web/src/`
- Reference: `docs/`
- Reference: `config/`
- Reference: `scripts/`

- [ ] **Step 1: 从当前工作区生成目录候选**

运行：

```bash
find .agent backend/career_os backend/tests web/src docs config scripts \
  -type d \
  -not -path '*/__pycache__*' \
  -not -path '*/node_modules*' \
  | sort
```

只把真实存在的目录写入 README。

- [ ] **Step 2: 编写只含目录的选择性树**

必须包含：

```text
.agent/skills/
backend/career_os/api/
backend/career_os/agents/
backend/career_os/agents/graphs/workers/
backend/career_os/harness/
backend/career_os/platform/
backend/career_os/platform/market_research/
backend/career_os/platform/prompt/
backend/career_os/platform/skill/
backend/career_os/platform/store/
backend/career_os/platform/tool/handlers/
backend/career_os/platform/trace/
backend/career_os/runtime/
backend/tests/
web/src/
docs/architecture/
docs/prd/
docs/roadmap/
docs/superpowers/
config/
scripts/
```

不得展示 `.py`、`.ts`、`.json`、`.md` 或其他文件。

- [ ] **Step 3: 为每个关键目录解释含义和作用**

注释必须使用“含义 + 作用”：

```text
agents/       # Agent 模型编排层：承载 Coordinator 与 Worker 的模型运行
harness/      # 受控执行层：负责流程 Gate、路由、授权和状态约束
platform/     # 平台能力层：提供 Prompt、Skill、Tool、Store、Trace 等通用服务
```

不要把规划中的 `operation/` 或 `run/` 目录写进当前仓库树。

- [ ] **Step 4: 添加四阶段产品主链路表**

列固定为：

```text
阶段 | 用户输入 | 系统行为 | 可验证产出 | 关键约束
```

行固定为：

```text
职业初探 | 市场调研 | JD 分析 | 简历交付
```

表后解释各列含义，避免读者把“系统行为”理解为已经通过生产验证的效果指标。

- [ ] **Step 5: 保留市场调研详细边界**

将原“市场调研主路径”迁入产品主链路扩展说明，保留：

- 方案确认和输入锁定；
- `waiting_user`；
- 安全取消；
- 报告展示和正式结果确认；
- 跨 Session 复用候选；
- 方向重试；
- 不可变结果版本；
- JD 原文不落市场 Trace；
- 10% 页面抽样截图；
- 招聘者活跃度口径；
- Google Trends 相对关注度边界。

---

## Task 6: 按当前代码校准系统架构图和关键请求时序图

**Files:**

- Modify: `README.md`
- Read: `backend/career_os/main.py`
- Read: `backend/career_os/api/chat.py`
- Read: `backend/career_os/harness/orchestrator.py`
- Read: `backend/career_os/harness/executor.py`
- Read: `backend/career_os/harness/delegate.py`
- Read: `backend/career_os/agents/graphs/coordinator.py`
- Read: `backend/career_os/agents/graphs/workers/react_runner.py`
- Read: `backend/career_os/platform/tool/registry.py`
- Read: `backend/career_os/platform/trace/writer.py`
- Read: `backend/career_os/platform/store/`
- Read: `backend/career_os/platform/market_research/`
- Read: `backend/career_os/runtime/sse.py`
- Read: `web/src/hooks/useChatSSE.ts`
- Reference: `docs/architecture/00-架构总览.md`
- Reference: `docs/architecture/03-系统分层.md`

- [ ] **Step 1: 核对单轮消息真实入口与出口**

重点确认：

- `chat`（聊天 API）接收用户请求；
- `_chat_stream`（聊天流执行函数）如何创建 SSE 事件；
- `ChatOrchestrator`（聊天编排器）如何管理单 Session 并发状态与上下文提醒，但不进入 Coordinator 或 Harness；
- `_chat_stream` 如何直接调用 `run_coordinator_turn`（运行单轮协调者）；
- `run_coordinator_turn` 如何分析、形成 Worker 队列、通过 Harness 派工并生成确定性回复草稿；
- `delegate_worker`（委托 Worker）如何构造能力包并调用 Worker；
- `run_worker_react`（运行 ReAct Worker）如何使用 Tool；
- `TraceWriter`（Trace 写入器）记录哪些运行事件；
- `format_sse`（SSE 格式化函数）如何形成前端可读事件；
- `useChatSSE`（前端 SSE Hook）如何消费事件。

当 README 提到这些函数时，必须解释函数含义和作用，不能只列函数名。

- [ ] **Step 2: 核对系统组件边界**

确认以下连接存在或由当前代码明确支持：

```text
用户 → Web → FastAPI
FastAPI → ChatOrchestrator（单 Session 并发与上下文提醒）
FastAPI → Coordinator
Coordinator → Harness delegate → Worker
Worker → Harness 授权的 Tool / 平台服务
平台服务 → Store / Trace / Browser / LLM
Coordinator 图生成确定性草稿 → FastAPI
FastAPI 以 Coordinator 角色流式调用 LLM → SSE → Web
```

若当前实现与旧架构文档冲突，以代码和测试为准，并在 README 使用当前事实。
禁止把主链画成 `FastAPI → Harness → Coordinator`。

- [ ] **Step 3: 编写精简系统架构 Mermaid**

图中必须包含：

```text
用户
Web 前端
FastAPI
ChatOrchestrator
Harness
Coordinator
Workers
平台服务
本地存储
LLM
Browser
```

图只表达组件关系，不复制详细分层图。

- [ ] **Step 4: 编写关键请求时序 Mermaid**

至少包含：

```text
用户发送消息
Web 发起请求
FastAPI 建立 SSE
FastAPI 创建或续接 Session
ChatOrchestrator 管理单 Session 运行状态与上下文提醒
Coordinator analyze
Harness delegate
Worker ReAct
Tool / Store / Trace
Coordinator 图生成确定性 synthesis draft
FastAPI 以 Coordinator 角色调用 LLM 合成最终正文
SSE token / done
Web 增量渲染
```

Worker 内部模型输出不得画成直接流向前端；当前实现先由 Coordinator 图生成确定性草稿，再由 API 以 Coordinator 角色调用 LLM，并通过 SSE 交付最终正文。

- [ ] **Step 5: 人工校验 Mermaid**

确认：

- 节点名称与当前实现一致；
- 图中没有 Go、gRPC、Worker 互调或尚未实施的 ExecutionPlan；
- 含空格、标点或括号的 Mermaid 标签使用引号；
- 详细图仍链接到架构文档。

---

## Task 7: 完成工程设计、文档索引和版本边界章节

**Files:**

- Modify: `README.md`
- Reference: `docs/roadmap/README.md`
- Reference: `docs/roadmap/v2.1.md`
- Reference: `docs/roadmap/v2.2.md`
- Reference: `docs/prd/`
- Reference: `docs/architecture/`
- Reference: `docs/superpowers/specs/`
- Reference: `docs/superpowers/plans/`
- Reference: `backend/tests/eval/CASES.md`
- Reference: `.agent/README.md`

- [ ] **Step 1: 编写核心工程设计表**

使用四列：

```text
工程问题 | 设计机制 | 代码或运行证据 | 当前边界
```

覆盖：

1. 模型如何做决策；
2. 如何防止 Agent 越权；
3. 如何追踪执行过程；
4. 如何判断效果。

每项必须满足：

- 机制有当前代码或运行证据；
- 证据链接到真实存在的文档、测试或截图；
- 尚未实现的强类型调用和失败机制明确写入边界；
- 不把框架名称当作业务成果。

- [ ] **Step 2: 编写分组文档索引**

按以下七组排列：

1. 产品设计；
2. 系统架构；
3. 版本与演进；
4. 实施记录；
5. 测试与评测；
6. 面试与项目表达；
7. Agent 技能包。

每组只提供主入口。原链接有真实替代路径时修复；没有承接文件时保留主题并标“待补充”。

- [ ] **Step 3: 编写 v2.1 当前边界**

只写当前可确认限制：

- 本地优先；
- 非生产级 SaaS；
- 强类型 Worker 调用待实施；
- 全局失败机制待实施；
- `ChatOrchestrator`（聊天运行协调器）使用进程内 `_active_runs`（活动会话运行表）阻止同一 Session 并发，但 `_chat_stream`（单轮聊天流处理函数）只在正常完成路径调用 `end_chat`（清除活动运行标记），尚未通过 `finally` 覆盖 SSE 中断或 LLM 异常，异常后可能需要重启进程解除运行标记；
- 评测和前端 E2E 边界；
- 浏览器和真实 LLM 对外部环境的依赖。

不要直接沿用旧架构文档中过时的 Session 行为。

- [ ] **Step 4: 编写 v2.2 已确认方向**

摘要链接到：

- 强类型 WorkerInvocation 与 ExecutionPlan Spec；
- 全局失败机制 Spec；
- 对应 Implementation Plan。

保持“先强类型调用、后全局失败机制、最后系统级回归”的依赖顺序。
上述四份依赖文档不由本计划暂存或提交；若仍未被 Git 跟踪，在 `v2.2.md` 中保留引用并明确记录“当前工作区已存在、由用户后续加入版本库”的临时交付边界。

- [ ] **Step 5: 编写长期候选方向**

只列少量示例并链接《产品规划与技术演进》，不在 README 展开全部 Todo。

- [ ] **Step 6: 验证 README 一级章节顺序**

运行：

```bash
rg -n '^## ' README.md
```

一级章节必须依次为：

```text
Career OS 定位与解决的问题
快速开始
实机演示
多级仓库结构
产品主链路
系统架构与关键请求链路
核心工程设计
测试与评测
文档索引
当前边界与后续演进
```

允许标题包含必要补充文字，但不得改变顺序和职责。

---

## Task 8: 运行真实验证并写入测试快照

**Files:**

- Modify: `README.md`
- Modify: `docs/roadmap/v2.1.md`
- Read only: `backend/`
- Read only: `web/`

- [ ] **Step 1: 运行非 LLM 测试**

运行：

```bash
cd backend && uv run pytest tests/ -m "not llm" -q
```

记录：

- 日期；
- 完整命令；
- passed；
- failed；
- skipped；
- deselected；
- collection error 或主要失败原因。

若命令失败，不修代码，继续完成文档并如实记录。

- [ ] **Step 2: 尝试 LLM Eval**

运行：

```bash
cd backend && uv run pytest tests/eval/ -m llm -v
```

约束：

- 不输出 `.env` 内容；
- 缺少 Key 时记录 skipped、未执行或配置限制；
- 若网络受限或真实模型调用失败，如实记录；
- 不把无 Key 下的跳过写成 LLM Eval 通过。

- [ ] **Step 3: 运行静态与前端构建检查**

运行：

```bash
make market-check
```

该命令含义：

- 后端执行 `compileall`（Python 语法编译检查）；
- 前端执行 `npm run build`（TypeScript 构建和 Vite 生产构建）。

记录实际通过或失败结果。

- [ ] **Step 4: 写入 README 最近验证快照**

表格至少包含：

```text
验证日期 | 执行命令 | 通过数 | 失败数 | 跳过/未选择数 | 备注
```

若命令不是 pytest，计数列使用 `—`，备注写实际结果。

- [ ] **Step 5: 同步 `v2.1.md` 验证证据**

只同步本轮实际运行结果。不得：

- 保留无来源的“96 个测试”；
- 写“全部通过”而省略失败；
- 把前端构建通过等同于前端 E2E 覆盖；
- 把 Session 级 token 估算写成实际请求注入成本。

---

## Task 9: 做信息完整性、链接和 Markdown 验收

**Files:**

- Verify: `README.md`
- Verify: `AGENTS.md`
- Verify: `docs/roadmap/README.md`
- Verify: `docs/roadmap/产品规划与技术演进.md`
- Verify: `docs/roadmap/v2.1.md`
- Verify: `docs/roadmap/v2.2.md`
- Reference: 原 README 内容迁移映射

- [ ] **Step 1: 先暂存需要提交的新增目标文件**

运行：

```bash
git add -- \
  AGENTS.md \
  docs/roadmap/README.md \
  docs/roadmap/产品规划与技术演进.md \
  docs/roadmap/v2.1.md \
  docs/roadmap/v2.2.md
git status --short
```

期望：

- 五个新增目标文件显示为已暂存；
- `README.md` 仍是未暂存修改；
- `README.before-maintenance.md` 保持未跟踪且不得暂存；
- 未暂存 `CONTEXT.md`、其他 Spec、其他 Plan 或任何用户文件。

- [ ] **Step 2: 验证截图集合**

运行：

```bash
rg -n 'docs/assets/screenshots/' README.md
rg -c '^!\\[.*\\]\\(docs/assets/screenshots/.*\\)$' README.md
```

期望：

- 14 张既有图片全部存在；
- 引用数量为 14；
- 顺序与 Task 1 固定集合一致；
- 截图目录补充链接仍存在。

- [ ] **Step 3: 验证运行命令与关键边界**

运行：

```bash
rg -n 'make install|make dev|make clean|make market-check|uv sync|uvicorn|npm install|npm run dev|BACKEND_PORT|localStorage' README.md
rg -n 'TERM|KILL|10 秒|profile\\.json|backend/data|backend/output|15173|18080' README.md
```

期望：Task 1 固定的命令和安全边界都有承接。

- [ ] **Step 4: 验证规划内容迁移**

运行：

```bash
rg -n 'Multi-Agent|记忆系统|评测 Agent|简历模板|Offer|上下文压缩|Harness|Text.*SQL|产品演进' docs/roadmap
```

期望：

- 原规划主题能够定位；
- README 不再展开约 150 行原始 Todo；
- `v2.2` 不包含未确认范围。

- [ ] **Step 5: 验证本地链接**

逐份提取并检查 README、AGENTS.md 和 roadmap 中的相对链接：

- 相对路径按“链接所在文件的目录”解析；
- URL 编码路径先解码或直接核对对应真实文件；
- `http://`、`https://` 和纯锚点不做本地文件检查；
- 带锚点的本地路径先移除 `#...` 再检查文件；
- 缺失路径必须修复或显式标记“待补充”。
- 对强类型 Worker 调用和全局失败机制的四份依赖 Spec/Plan 运行 `git ls-files --error-unmatch <path>` 检查跟踪状态；未跟踪时保留引用，但必须记录“由用户后续加入版本库”，不得暂存这些文件，也不得把链接描述为已随本次提交闭合。

特别确认：

```text
docs/prd/
docs/architecture/
docs/roadmap/
docs/superpowers/specs/
docs/superpowers/plans/
backend/tests/eval/CASES.md
.agent/README.md
```

- [ ] **Step 6: 检查 Markdown 和空白**

运行：

```bash
rg -n '[[:blank:]]+$' README.md AGENTS.md docs/roadmap/*.md
git diff --check
git diff --cached --check
```

期望：

- `rg` 无输出；
- 未暂存的 README diff 无空白错误；
- 已暂存的五个新增目标文件 diff 无空白错误；
- 人工检查表格列数、代码块闭合、Mermaid 块和标题层级。

- [ ] **Step 7: 对照 Design SSOT 的 20 项验收标准**

逐项勾选 Design SSOT 第 11 章。任何一项不满足都不能把计划标记完成。

---

## Task 10: 最终范围审计和人工语义验收

**Files:**

- Verify: all allowed target files
- Verify: working tree

- [ ] **Step 1: 审计最终变更范围**

运行：

```bash
git status --short
git diff -- README.md
git diff --cached -- \
  AGENTS.md \
  docs/roadmap/README.md \
  docs/roadmap/产品规划与技术演进.md \
  docs/roadmap/v2.1.md \
  docs/roadmap/v2.2.md
git diff --stat
git diff --cached --stat
```

期望：

- 最终仓库变更只包含 Global Constraints 中允许的六个目标文件；
- 五个新增目标文件已经暂存，README 修改尚未暂存；
- `README.before-maintenance.md` 仍是未暂存的临时迁移快照；
- Design Spec 和本 Plan 的既有内容未在实施阶段被改写；
- 用户原有未跟踪文件和无关修改保持原样；
- 强类型 Worker 调用和全局失败机制的四份依赖 Spec/Plan 未被本计划暂存；若仍未跟踪，最终交付明确说明它们由用户后续加入版本库；
- 没有业务代码、配置、依赖或截图变化。

- [ ] **Step 2: 使用根目录快照人工核对 README 迁移完整性**

运行：

```bash
git diff --no-index -- README.before-maintenance.md README.md
```

该命令因两个文件存在预期差异可能返回退出码 1，不表示验收失败。人工逐段确认：

- 原 README 每个一级、二级章节都有明确去向；
- 14 张截图、截图说明和两次独立任务说明完整保留；
- 所有独有命令、端口、路径、环境后缀和清理安全边界完整保留且命令已按实际工作目录修正；
- 原规划、优化点、Todo、核心思考、产品演进和 Text-to-SQL 示例均能在 README 或 roadmap 定位；
- “96 个 pytest”和“本地与远端一致”已作为过期或瞬时数据记录迁移原因，没有继续作为当前事实；
- 没有把计划能力或失败测试改写成已实现结果。

人工确认通过后，删除本计划自己创建的临时快照：

```bash
rm README.before-maintenance.md
test ! -e README.before-maintenance.md
git status --short
```

只能删除本计划在 Task 1 创建且已核验哈希的这一份快照；如果文件身份无法确认，停止并人工处理。

- [ ] **Step 3: 人工阅读 README 前三屏**

以技术面试官视角确认：

- 第一屏能理解 Career OS 是什么和解决什么问题；
- 快速开始可直接运行；
- 实机演示在第三章完整出现；
- 没有先堆砌技术框架。

- [ ] **Step 4: 人工阅读架构和工程章节**

确认：

- 图与当前代码一致；
- 主链为 FastAPI 直接调用 Coordinator，Coordinator 再通过 Harness 委托 Worker；
- ChatOrchestrator 只承担单 Session 并发控制和上下文提醒；
- Worker 不直接向前端流式输出；
- Harness、Coordinator、Worker、平台服务边界清楚；
- 字段、目录和函数在出现时解释了含义和作用；
- 计划能力没有伪装成已实现。

- [ ] **Step 5: 人工阅读 roadmap 与 AGENTS.md**

确认：

- `v2.1` 是开发中；
- `v2.2` 是规划中；
- 版本文档使用统一模板；
- roadmap 与 Superpowers Plan 边界清楚；
- AGENTS.md 能指导后续 Agent 同步维护 README 和版本文档；
- agents.md 开放格式要求得到满足。

- [ ] **Step 6: 记录未解决事项**

如果存在：

- 失效但无法修复的旧链接；
- 失败测试；
- 缺少 LLM Key；
- 架构文档与代码不一致；
- 尚无证据的 README 原声明；

在最终交付中逐项说明，不静默忽略，也不扩大范围修复。

---

## Task 11: 建议提交信息（仅在用户另行要求 commit 时使用）

```text
docs(readme): 重构 Career OS 项目说明与版本路线

- 按确认顺序重组 README 并保留完整实机演示与运行信息
- 新增 v2.1、v2.2 路线文档和跨版本产品规划
- 增加遵循 agents.md 的项目级文档维护规则
- 使用真实测试快照和代码校准架构说明
```

本 Task 只提供提交信息；Task 9 已按用户确认暂存五个新增目标文件，但本 Task 不创建 commit。

---

## Completion Criteria

计划实施完成必须同时满足：

1. 最终只修改或新增六个允许的目标文件；临时 README 快照已完成对照并删除，未触碰业务代码、配置、依赖、截图或无关文档；
2. README 使用 `Career OS` 主标题和确认的一句话定位；
3. README 一级章节严格采用确认的十章顺序；
4. 快速开始采用最短路径在前、完整运行说明在后；
5. 实机演示保持原顺序，14 张既有截图和独有说明完整保留；
6. 仓库树只展示真实目录，选择性展开且最深五级；
7. 产品主链路使用四阶段、五列表格；
8. 两张 Mermaid 图已经过当前代码调用链校准，明确 FastAPI 直接调用 Coordinator、Coordinator 通过 Harness 委托 Worker；
9. 核心工程设计采用“问题、机制、证据、边界”；
10. 测试章节使用本轮真实命令和带日期快照，不再保留无来源的“96”；
11. 文档索引按七类目的分组，断链已修复或标记待补充；
12. README 第 10 章清楚区分 v2.1、v2.2 和长期候选；
13. roadmap 四份文档存在，原规划信息能够定位；
14. `v2.1` 为“开发中”，`v2.2` 为“规划中”；
15. `v2.2` 只包含已确认的可靠性升级主线；
16. 根 `AGENTS.md` 遵循 agents.md 的标准 Markdown 开放格式；
17. README、roadmap 和 AGENTS.md 的同步维护规则已经固化；
18. 五个新增目标文件已先暂存并通过 `git diff --cached --check`，README 通过 `git diff --check`，本地链接、截图引用和 Markdown 结构检查通过；
19. 测试或环境限制已如实记录，没有顺带修复业务代码；
20. 已使用 `README.before-maintenance.md` 完成人工逐段对照并删除快照；五个新增目标文件保持已暂存，未创建 commit、未推送。

---

*Plan 结束*
