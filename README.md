# AI-Optimized-Resume-V2

面向 IT 的职业规划智能体：结构化档案、Harness 动态任务、三阶段技能包（初探 / 岗位对齐 / 简历模块化）、本地网页简历。

**分支策略**：仅维护 `main`（本地与远端一致）。

```bash
# 首次（项目根）
make install
# 编辑 backend/.env：LLM_PROVIDER / LLM_API_KEY

# 空白环境（data/blank）
make dev blank
# 手测：make dev test · 演示：make dev demo
# 清空某环境数据：make clean demo
```

访问：**http://localhost:15173**

## 文档索引

| 类型 | 链接 |
|------|------|
| 产品需求 | [docs/prd/00. 职业规划 Agent PRD.md](docs/prd/00.%20职业规划%20Agent%20PRD.md)（总领）；A/B 系列子 PRD 见同目录 |
| 架构设计 | [docs/architecture/00-架构总览.md](docs/architecture/00-架构总览.md)（一主多从协调者 + **Python 单体** + SSE） |
| 实施计划 | [Career OS v0.1](docs/superpowers/plans/2026-05-31-career-os-v0.1.md) · [Worker ReAct](docs/superpowers/plans/2026-05-31-real-agent-worker-react.md) |
| 简历项目描述 | [docs/简历项目描述.md](docs/简历项目描述.md)（直贴简历用） |
| 技能包 | [.agent/README.md](.agent/README.md)（`load_skill` 索引） |
| Eval 清单 | [backend/tests/eval/CASES.md](backend/tests/eval/CASES.md) |
| 边界参考 | [docs/参考文档.md](docs/参考文档.md) |

## 当前状态（v0.1 · main）

| 模块 | 状态 |
|------|------|
| Harness 运行时 | Task / Profile / Tool / Skill / Storage 平台服务；`load_skill` + `capability_bundle` 派工 |
| 协调者 | LangGraph 编排；analyze 选人 + synthesize **LiteLLM 真流式** |
| 7 类 Worker | 全部 **ReAct**（`run_worker_react`）；无 `LLM_API_KEY` 时 L1 走 `react_mocks` |
| LLM | [LiteLLM](backend/career_os/agents/lc/providers.py) 统一路由；配置见 `backend/.env.example` |
| 前端 | React + Vite；Chat SSE（含 `gate` 事件展示） |
| 评测 | **96** pytest（L1 **90** + LLM **6**）；trace 写入各环境 `data/{demo|test}/logs/traces/` |

尚未落地或待深化：记忆索引 side-query、三档 HTML 生成顺序复用、Browser Tool 生产级降级、部分 PRD 业务流程细节（见下方「优化点」）。

## 快速开始

**环境**：Python ≥ 3.11、[uv](https://docs.astral.sh/uv/)、Node.js（前端）。

**一键启动**（后端 `:18080` + 前端 `:15173`）：

```bash
make dev blank      # 空白档案
make dev test       # 手测（data/test）
make dev demo       # 演示环境（空档案结构，无预填业务数据）
make dev sandbox    # 任意后缀，数据完全隔离
```

数据落在 `backend/data/{后缀}/`、`backend/output/{后缀}/`。启动时会创建 **`profile.json` 空结构**（无姓名、JD 等预填值）；业务数据仅在「建档」或对话落档后写入。`data/profile.example.json` 仅供文档/测试参考。

**清空某环境数据**（删除该后缀下的档案、会话、trace、HTML 产出；不影响其它后缀）：

```bash
make clean demo       # 清除 data/demo 与 output/demo
make clean test
./scripts/clean.sh blank
```

清除后重新启动：`make dev demo`。若浏览器仍连着旧会话，请无痕打开或执行 `localStorage.removeItem('session_id')`。

**分步启动**（需两个终端）：

```bash
# 1. 后端依赖
cd backend && uv sync

# 2. LLM（可选；不配 Key 时 L1 测试与 mock 路径仍可用）
cp .env.example .env
# 编辑 .env：LLM_PROVIDER / LLM_API_KEY

# 3. 启动后端（默认 18080，与前端 proxy 一致）
uv run uvicorn career_os.main:app --reload --port 18080

# 4. 另开终端：前端
cd web && npm install && npm run dev
# → http://localhost:15173
```

本地数据与产出（`backend/data/{SUFFIX}/`、`backend/output/{SUFFIX}/`，均不入 Git）：

| 后缀 | 典型用途 |
|------|----------|
| `blank` | 一次性空白验证 |
| `test` | 长期手测 |
| `demo` | 演示（与 blank 相同，档案按需产生） |

端口冲突：`BACKEND_PORT=19080 FRONTEND_PORT=16173 make dev blank`

## 仓库结构

```text
.
├── backend/career_os/     # FastAPI + Harness + 协调者/Worker + LiteLLM
├── backend/tests/         # L1 / e2e / eval（-m llm 需 Key）
├── web/                   # React Chat UI
├── .agent/skills/         # 三阶段 Skill 包（Worker Run 内 load_skill）
├── docs/prd/              # 产品规格
├── docs/architecture/     # 架构与协议
├── docs/superpowers/plans/ # 迭代实施计划
├── scripts/dev.sh         # make dev <suffix>
├── scripts/clean.sh       # make clean <suffix>
└── Makefile
```

## 测试

```bash
cd backend

# L1：确定性，无需 Key（默认）
uv run pytest tests/ -m "not llm" -q

# LLM eval：需 backend/.env 配置 LLM_API_KEY
uv run pytest tests/eval/ -m llm -v
```

## 优化点

- [x] 一份 prd 拆分为多份，一份太大了，不好优化
  - [x] prd、技术文档按需拆解，在做某一部分的代码编写的时候只看某一部分的文档
- [ ] 各业务流程细节的确认优化
  - [ ] 需要确认长期记忆都存储哪些信息，Agent 执行的时候都调用长期记忆中的哪些信息（见 [A01 机制-职业档案 PRD](docs/prd/A01.%20机制-职业档案%20PRD.md)）
  - [ ] 简历优化遵循 STAR 原则（见 [B06 流程-简历优化 PRD](docs/prd/B06.%20流程-简历优化%20PRD.md)、`resume-module-optimize` SKILL）
- [ ] career-inner-exploration skill 目前在身份智能体和能力智能体两个智能体中都使用了，需要拆分为两个 skill，或者在 skill 中设置分支，分别描述两个 agent 需要的能力
- [x] JD 后简历优化前可选深挖经历（先展示已有 bank，用户选择；见 [B06 §5.5.0](docs/prd/B06.%20流程-简历优化%20PRD.md#550-jd-后经历素材补齐可选深挖)）
- [ ] 在进行 JD 适配评测时，也可以深挖用户经历来更深度的辅助判断是否适配（B03 阶段，与 B06 优化前深挖不同）
- [ ] 如果要同时生成多种档位的 html 简历优化，应该按照保守、标准、进取的顺序进行生成，在创建细分多任务列表时，注意哪些信息可以复用（PRD 已定义多选多份与语义后缀 [B06](docs/prd/B06.%20流程-简历优化%20PRD.md)；生成顺序与 work 复用待实现）
  - [ ] 这里应该引入一个 skill
- [ ] 如何区分任务是否需要拆分为多任务列表？
- [ ] 记忆系统（主要指长期记忆）
  - [ ] 文件数多了之后，进行去重、合并、剪枝
  - [ ] 加索引，索引常驻 System Prompt，按需加载
    - [ ] 通过 side-query 将索引文件发给 llm，让 llm 选择；side-query 失败（API 错误、JSON 解析失败），降级到关键词匹配 name + description
- [ ] 当前任务过于固定，改为动态生成

## todo

- [x] 加入评测（L1 + `-m llm` 分层；清单见 [CASES.md](backend/tests/eval/CASES.md)）
- [x] Worker ReAct + LiteLLM 真推理（协调者 analyze/synthesize + 7 Worker）
- [ ] 加入监测、可审计、过程日志记录，帮助升级 Harness（trace JSONL 已有基础，待产品化）
- [ ] 引入 offer 对比、选择：规划 AI Agent 引入外包、正编、五险一金等 offer 对比功能，使用 skill 引入
- [ ] 就业城市选择、大学城市、专业选择、定居城市选择等等（要不要做呢？有点大而全了）：AI Agent 的项目其实还可以做更多东西，比如说城市选择、未来结婚的时间点、行业与城市供应链选择；从大学刚毕业或高考之后选专业、大学城市，再选行业与所在城市，以及跟对象的定居城市、长期发展城市等
- [ ] 上下文压缩：session memory 关注同一会话内的连续性；compact 之后，当前会话还需要保留哪些上下文。两者配合使用：Memory 管长期知识，session memory 管当前会话的压缩续接
- [x] Skill 管理：Python `career_os` Harness（见 [docs/architecture/02-平台服务.md](docs/architecture/02-平台服务.md)）
- [ ] 加入评测 Agent
- [ ] 引入简历模板 Skill：在创建简历 HTML 时，根据用户选择的预置风格，调用 Skill 中不同的部分，生成对应的最终简历
  - [ ] 引入模板解析 Agent：用户上传简历模板，做一个模板解析 agent，解析成对应的 html，解析出对应的模板简历风格，补充到用户自定义的简历模板 Skill 中 

## 核心

1. 如何做出随着模型能力提升而提升的 harness 产品？
   - 哪些是 harness 该管的，哪些是模型该管的。边界是什么
   - harness 应该与 **业务** 有关吗？**【详情见示例】**
     - 我们在教一个孩子的时候，会分别专门教他**分析销售数据**和**分析用户行为数据**两套逻辑吗？不会吧，如果需要分别教 llm，则说明 llm 还不够聪明，这应该是大脑负责的事情，不应该 harness 来做。
2. Agent 如何切割？Agent 的边界是什么？（类似微服务的切割）
3. 大脑才是决策。
   - 分部门分组织架构的目的就是为了将信息一层一层的精炼收集到最高层，然后让最高层决策。
   - 那我们的 Agent 架构是不是应该也是这样做？
4. ~~如果要做 GO + Python 的架构，如何切割？~~ → **已决策：v0.1 纯 Python**（见 [docs/architecture/04-应用运行时与部署.md](docs/architecture/04-应用运行时与部署.md)）

## 产品演进

- **V1**：主要功能为根据 JD 修改简历，判断是否符合职业规划为次要功能
- **V2（当前）**：长期规划，根据 JD 修改简历是其中的一个功能。产品不再只聚焦单次 JD 投递，而是长期职业记忆 + 职业资本推演 + 简历 HTML 交付的个人职业操作系统。
- **V3**：寻找自己。扩展到多行业多岗位时，才能扩展到这一步。
  - 规划的本质是找自己，向内求，每个人的自己都不一样，别人的成功不一定适合自己。
  - AI 这个项目是叫人生规划系统，其实它是一个寻找自己的系统。其实人生规划不是你要成为多成功的人，而是在寻找自己路上如何成为一个自己人在最后，无论如何都会接近，无限接近，然后成为自己的，不管是经历怎样的路程，你都会是最初自己。不管是有世俗的成功也好，或者是没有世俗的成功也好
  - 自己的偏好更重要，而不是以外界世界的成功来作为主要资料引导规划路径

## 示例

### 示例 1 Harness 应该与业务有关吗？

下面这份 Skill 的描述来自于 hello-agents，但是这个描述与业务强相关。

不应该抽取 Text -> SQL 这个抽象，然后让 LLM 这个大脑去实际填充业务吗？

这样 Harness 工程就与业务分割开，可以随着 llm 能力的提升而提升，而且可以适配多种业务场景。

```
description: >
  将中文业务问题转换为 SQL 查询并分析 MySQL employees 示例数据库。
  适用于员工信息查询、薪资统计、部门分析、职位变动历史等场景。
  当用户询问关于员工、薪资、部门的数据时使用此技能。
```
