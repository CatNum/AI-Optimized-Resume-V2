# Career OS Agent Guide

## 项目概览

Career OS 是一个本地优先的职业规划 AI Agent：它围绕职业初探、市场调研、JD 分析、简历优化与 HTML 简历交付，保存本地会话、档案、任务、产物与 Trace。它不是生产级 SaaS；任何“已实现”描述都必须能回到当前代码、测试、运行记录、截图或 Trace。

当前仓库只有本地开发、测试和演示环境，没有连接线上用户、生产流量或生产数据的部署。本地代码、Prompt 和 Skill 变更不会影响任何外部生产环境。Spec/Plan 中的“生产路径”“生产 Runner”或“生产 Adapter”仅指本仓库当前默认运行路径、真实实现和非 fake Adapter，用于区别最终目标实现、测试 fixture 与 mock；不得把它解释为已上线系统，也不得仅以“保护线上生产”为理由阻止本地重构。

## v2.2 一次性系统重写原则

`WorkerInvocation`（Worker 结构化调用契约）、`ExecutionPlan`（执行计划）、全局失败机制以及后续纯规划链 pipeline 改造采用一次性系统重写，不采用需要长期兼容旧架构的渐进迁移：

- 实施过程中不要求每个中间 Task、提交或工作树状态保持现有 API、页面和旧测试可运行；允许在完成最终切换前存在不可运行的中间态。
- 不得仅为迁移过程建立兼容投影、双写、双读、旧新 Runner 并行 seam、临时 API Adapter 或保留旧测试契约。旧接口、旧页面调用、旧状态模型和只验证旧架构的测试可以在同次改造中直接重写或删除。
- 本次重写不迁移旧 `DATA_DIR` 中的 Session、Task、Artifact 或其他本地运行数据，也不提供旧格式的运行时兼容读取或一次性离线迁移器；新系统从干净数据目录开始验收，旧运行目录只作为可丢弃的历史数据，不得混入新格式测试。
- Spec/Plan 应直接描述最终唯一事实源、最终 API、最终页面契约、最终 Runner/Operation 执行 seam 和最终测试体系，不再把“迁移期持续可运行”作为任务拆分、模块边界或持久化设计的约束。
- 一次性重写不降低最终质量要求：完成改造时必须恢复完整可运行性，执行目标架构对应的后端测试、前端构建、类型检查和跨模块回归，并如实记录失败、跳过或未执行项。
- 不得以“一次性重写”为理由删除仍属于产品目标的业务能力、数据安全约束或验收要求；需要取消或改变业务行为时，仍须获得用户明确确认并同步 Spec、Plan 与 Roadmap。

核心分工如下：

- `web/` 是 React + Vite 前端，负责收集用户输入、展示会话/任务/产物，并消费 SSE（Server-Sent Events，服务端事件流）中的 `token`（增量正文）和 `done`（本轮结束）事件。`ChatPage`（聊天页面组件，位于 `web/src/pages/ChatPage.tsx`）负责组织聊天界面、流程状态与用户交互；`useChatSSE`（聊天事件流 Hook，位于 `web/src/hooks/useChatSSE.ts`）负责发起聊天请求、解析 SSE 事件并把增量结果交给页面状态。
- `backend/career_os/api/` 是 FastAPI 接口层，负责 HTTP 参数校验、会话建立或续接、SSE 响应和 API 级状态检查。
- `ChatOrchestrator`（聊天运行协调器，位于 `harness/orchestrator.py`）只负责进程内单个 Session 的并发标记和上下文容量提醒；它不是进入 Coordinator 的中间层。当前 `_active_runs`（活动会话运行表）仅在正常 SSE 完成路径由 `end_chat`（清除活动运行标记）释放，异常、中断或 LLM 异常路径尚未以 `finally`（无论如何都会执行的收尾块）闭环，不能声称异常释放已经解决。
- `Coordinator`（协调者，位于 `agents/graphs/coordinator.py`）负责分析意图、路由业务动作、生成 `pending_workers`（待执行 Worker 队列）、发起 Worker 委托、汇总结果并形成确定性回复草稿；Worker 之间不直接通信。
- `Harness`（受控执行层，位于 `harness/`）负责 Gate（阶段确认关卡）、Worker 委托前置条件校验、Tool（工具）可见性与授权、状态约束和 Trace 记录。Coordinator 通过 `delegate_worker`（校验并包装 Worker 委托的函数）申请委托；业务 Tool 由 Worker runner 或 `sessions.py` 中明确的 API 产物删除路径通过 `execute_tool`（按调用角色授权并执行 Tool 的函数）进入 Harness，不能把它描述成 Coordinator 直接执行 Tool。
- `Worker`（业务工作者，位于 `agents/graphs/workers/`）执行市场、JD、策略、简历等专门业务推理或工具调用；其结果由 Coordinator 合成，而不是由 Worker 相互传递。
- `platform/` 是通用平台能力，提供 Prompt、Skill、Tool、Store（本地读写）、Trace 和市场调研服务，供 Agent 与 Harness 使用。
- 本地存储由 `platform/store/` 和配置的 `DATA_DIR`、`OUTPUT_DIR` 承担：会话状态、聊天记录、档案、任务和产物保存在当前环境目录；`TraceWriter`（追踪写入器）把 JSONL 事件写入 `data/<suffix>/logs/traces/`。

关键目录的含义与作用：

- `backend/career_os/agents/`：Agent 模型编排层，包含 Coordinator 图、Worker、状态模型和 LLM 客户端；负责模型决策与业务内容生成。
- `backend/career_os/harness/`：受控执行约束层，包含 Gate、委托、Tool 授权、会话并发和阶段规则；负责让模型决策受确定性边界约束。
- `backend/career_os/platform/`：通用平台能力层，包含 Prompt、Skill、Tool、Store、Trace 和市场调研；负责复用的运行能力而非单个业务流程编排。
- `.agent/skills/`：业务 Skill 包目录；每个 `SKILL.md` 描述可加载的业务知识、模式和允许的 Worker，供 `SkillRegistry`（技能注册表）发现、索引和按权限加载。
- `backend/career_os/runtime/`：运行时传输能力；例如 `sse.py` 负责把后端结果格式化成前端可消费的 SSE 事件。
- `backend/data/<suffix>/` 与 `backend/output/<suffix>/`：按启动后缀隔离的本地运行数据和 HTML 等输出，不是可提交的源码。

## 真实请求入口链

不要把架构画成 `FastAPI → Harness → Coordinator`，也不要把 ChatOrchestrator 画成 Coordinator 的前置中间层。当前主链是：

```text
用户 → Web ChatPage/useChatSSE → POST /v1/chat（FastAPI）
  → SessionStore 建立或读取 session_id（会话标识）
  → ChatOrchestrator.begin_chat（同一 Session 并发控制与上下文提醒）
  → _chat_stream（单轮 SSE 处理函数）
  → run_coordinator_turn（执行本轮 Coordinator 图）
  → analyze（分析意图与 pending_workers，待执行 Worker 队列）
  → delegate（必要时）→ Harness.delegate_worker（校验后委托）
  → Worker runner → 受 Harness 授权的 Tool / platform 服务
  → SessionStore、TaskStore、TraceWriter 写入本地状态
  → Coordinator 的 synthesis_draft（确定性回复草稿）
  → 可用时 Coordinator LLM 润色 → SSE token / done → Web
```

`session_id` 的含义是一次本地会话的唯一标识，作用是隔离聊天历史、状态和产物；`pending_workers` 的含义是 Coordinator 选出的待执行 Worker 队列，作用是让协调者集中控制派工顺序；`synthesis_draft` 的含义是协调图形成的确定性回复草稿，作用是让最终 LLM 合成有可追溯的业务依据。修改这些字段或对应函数前，必须追踪其调用方、持久化位置和测试断言。

## 安装、启动与常用检查

下列命令均为当前仓库真实存在的命令。除特别说明外，从仓库根目录运行；不要把需要真实 LLM 的命令描述为无条件离线检查。

| 命令 | 用途 | 工作目录与前提 |
|---|---|---|
| `make install` | 同步后端依赖、安装前端依赖；若 `backend/.env` 不存在则从示例创建。 | 根目录；需要 Python 3.11+、`uv`、Node.js 与 `npm`。创建后应自行配置 `backend/.env` 的 LLM Provider/Key，且该文件不得提交。 |
| `make dev blank` | 启动空白隔离环境，后端默认 `18080`、前端默认 `15173`。 | 根目录；需要 `uv`、`npm`，脚本会同步后端依赖并加载 `backend/.env`。无 LLM Key 时仅可使用 mock/确定性路径，真实 ReAct 需要 Key。 |
| `make dev test` | 启动用于手动测试的 `test` 后缀隔离环境。 | 根目录；前提同 `make dev blank`。 |
| `make dev demo` | 启动用于演示的 `demo` 后缀隔离环境。 | 根目录；前提同 `make dev blank`。 |
| `make clean demo` | 按已登记的进程身份终止 `demo` 环境的相关进程，并删除该后缀的数据和输出。 | 根目录；会删除 `backend/data/demo/` 与 `backend/output/demo/` 中的本地运行内容，确认目标环境可清理后再运行。 |
| `make market-check` | 编译后端 Python 包并构建前端，做市场调研相关静态/构建检查。 | 根目录；先完成依赖安装；不需要 LLM Key。 |
| `(cd backend && uv run pytest tests/ -m "not llm" -q)` | 运行排除 `llm` 标记的确定性后端测试。 | 从根目录执行该子 Shell；需要后端依赖，通常不需要 LLM Key。结果必须如实记录，不以历史数字替代。 |
| `(cd backend && uv run pytest tests/eval/ -m llm -v)` | 运行真实 LLM Eval（大语言模型评测）。 | 从根目录执行该子 Shell；需要后端依赖、可用的 `backend/.env` 与 `LLM_API_KEY`，并可能需要相应外部运行条件。缺 Key 或环境限制时记录未执行、跳过或失败。 |
| `(cd web && npm run build)` | 执行 TypeScript 构建检查并生成 Vite 生产构建。 | 从根目录执行该子 Shell；需要 Node.js、`npm` 与已安装的 `web/node_modules`；不需要 LLM Key。 |

## 代码、测试与安全约束

1. 修改前先核对相关 PRD、Spec、当前代码和现有测试；Spec/Plan 是设计与实施依据，不等同于已运行的实现证据。
2. 后端改动应运行匹配的后端测试；前端改动至少运行相关检查和 `npm run build`；Skill 改动应验证 Skill 注册/加载及允许的 Worker；配置改动应验证实际读取它的启动或测试路径。
3. 测试失败、跳过、未执行或缺少外部依赖时如实记录；不得写成“通过”、全绿、生产稳定或效果提升。
4. 不提交 `backend/.env`、`backend/data/`、`backend/output/`、运行日志、HTML 简历、Trace、会话数据、缓存或任何用户隐私数据。
5. 不将 JD（职位描述）、简历、用户档案、附件、聊天记录或本地会话内容复制到公共 README、roadmap、Spec、Plan、提交信息或公开示例。
6. 不以计划文档、Prompt 或未执行的测试清单替代当前代码、测试、Trace、截图或可复现运行记录。
7. 严格遵循当前任务明确授权的文件范围；用户拥有的未跟踪文件或任务范围外文件，未经授权不得修改或暂存。某次维护计划中的临时冻结清单只约束该计划的执行过程，不形成仓库的长期禁止规则。

介绍代码字段、目录或函数时，必须同时说明其含义和作用。例如，`name` 是名称字段、用于标识对象；`getName` 是获取名称的函数、用于读取该字段。不要只罗列符号名或技术名词。

## README 维护规则

已交付能力变化时，同时检查根 `README.md`、`docs/roadmap/v2.1.md` 与相关架构文档。README 的一级章节必须保持以下十章顺序：

1. Career OS 定位与解决的问题
2. 快速开始
3. 实机演示
4. 多级仓库结构
5. 产品主链路：职业初探 → 市场调研 → JD 分析 → 简历交付
6. 系统架构与关键请求链路
7. 核心工程设计：模型决策、Harness 约束、Trace 追踪、Eval 评测
8. 测试与评测
9. 文档索引
10. 当前边界与后续演进

其他强制规则：

- 实机演示保持现有时间顺序：本地环境启动、建档与职业初探、市场调研执行、JD 分析与策略确认、最终交付、演示收尾；不得为突出最终结果而重排。
- 仓库树只展示目录、按架构价值选择性展开，最深五级；不展示文件、缓存、`node_modules`、运行数据或输出文件，并为展示的目录解释含义和作用。
- 架构图和请求图必须按当前代码校准，尤其保持 `FastAPI → Coordinator → Harness → Worker / Tool` 的真实关系与 ChatOrchestrator 边界。
- 测试数量、通过/失败/跳过结论必须重新执行验证，并绑定验证日期与完整命令；旧数字不能被无说明地沿用或删除。
- 迁移或重构 README 时建立信息去向对应关系，禁止静默删除；无法确认的信息要标记原因并迁移到合适文档。
- 无代码或运行证据的计划不得写成当前能力；产品运行截图使用 `docs/assets/screenshots/`，不得与 PRD 图片或市场审计图片混用。

## Roadmap、版本与证据规则

`docs/roadmap/` 记录版本承诺、范围、状态和验收证据；`docs/superpowers/specs/` 记录设计约束；`docs/superpowers/plans/` 记录具体实施步骤。三者必须保留边界：Spec/Plan 完成不自动证明业务代码或产品版本完成。

- 当前实现、范围或证据发生变化时同步检查并更新 `v2.2`；当前产品版本为 `v2.2（开发中）`。
- `v2.1` 已按“验收未完成”归档，只保留历史范围、证据和归档边界，不得追溯改写为已完成。
- 下一产品版本尚未确定；不能把长期候选项自动承诺给未建立的下一版本。
- 未确认版本归属的想法进入《产品规划与技术演进》，不要直接占用下一个版本。
- 版本状态变化时同步更新 roadmap 索引。版本标为“已完成”前，必须满足验收标准并附代码、自动化测试、运行截图或可复现记录等对应证据。
- 证据只描述实际执行快照；没有证据的事项只能是“规划中”或“进行中”。
- 不批量改写历史 `v0.1`：它是旧架构、PRD、Spec 或 Plan 的历史基线，不等同于当前产品路线版本。

## Git 提交信息规则

除非用户明确要求，未经用户要求不得自动 `git add`、`git commit`、推送或创建 Pull Request。

用户要求创建 commit 时，提交信息必须：

- 使用中文 Conventional Commit 主信息，例如 `feat(scope): 中文主信息`、`fix(scope): 中文主信息` 或 `docs(scope): 中文主信息`。
- 在主信息后提供至少两个具体中文分点。
- 每个分点说明实际改动和目的。
- 除非用户明确要求，不使用英文提交信息。

示例：

```text
docs(roadmap): 补充版本验收证据规则

- 明确 v2.1 状态变更需要测试或运行记录
- 区分长期候选方向与 v2.2 已确认范围
```
