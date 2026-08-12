# ExecutionPlan 与受控执行生命周期 Implementation Plan

> **状态：已确认，待实施。** 本 Plan 是一次性系统重写的第二阶段；完成时必须恢复完整产品主链可运行性，并成为全局失败机制的直接实施前置。

**Goal:** 将前置强类型 Invocation、Outcome、Contract 和 Runner 接入唯一 ExecutionPlan 主链，统一 Session、Gate、operation 授权、产物索引、API、SSE 与前端生命周期，并删除旧事实来源。

**Architecture:** `ExecutionPlanBuilder/Executor` 管理依赖、结果、推进与认领；`OperationRegistry` 管理 operation 定义与唯一 handler；`ExecutionPlanRequestService` 管理 Session 聚合事务。Coordinator 和 Handler 只返回不可变 transition，API 只构造请求，Store 只通过命名 CAS 发布状态。

**Design SSOT:** `../specs/2026-07-23-execution-plan-controlled-lifecycle-design.md`

**Required predecessor:** `2026-07-23-typed-worker-invocation-contract.md` 已全部实施并通过定向测试与 Pyright，且提供完整 15 类型目录、Registry、Contract、Runner、暂停现场、continuation 和 operation 调用端口。

**Direct successor:** `2026-07-23-global-failure-mechanism.md`

---

## Global Constraints

- 直接切换最终唯一主链，不建立旧新 Coordinator、Runner、Session 或 API 兼容层。
- 允许实施中间 Task 不可运行，但最终必须恢复后端测试、Pyright、前端构建和跨模块回归。
- 只消费前置契约模块，不复制 Definition、Invocation、Outcome、Contract 或 Runner 类型。
- Harness 定义依赖、binding、Gate 和授权；LLM 只提议目标阶段与 InvocationProposal。
- `advance()` 不 dispatch；只有 `claim_next()` 能原子绑定 Worker Run 并生成 PlanDispatch。
- 同步 Plan 不进入 CurrentExecution；授权暂停与真正异步执行使用不同分支。
- 所有 Session 写入由 `ExecutionPlanRequestService` 通过 revision CAS 提交；Handler/API 不直接写 Store。
- `OperationRegistry.resolve()` 是 Definition/handler 唯一绑定入口；ToolRegistry 不拥有 handler。
- 不迁移旧 DATA_DIR；从干净目录验收。
- 不提前实现全局 Failure 分类、重试、Judge、Run Store、授权 TTL 或 Trace exactly-once。
- 所有字段、类型和函数使用中文注释或 docstring 解释含义与作用。
- 不修改用户无关工作区改动、`docs/assets/`、`.env`、运行数据或隐私文件。
- 不运行真实 LLM Eval，除非用户另行明确授权。

## Public Test Seams

| seam | 验证目标 |
|------|----------|
| `ExecutionPlanBuilder.build()` | 合法 Proposal 如何形成完整 Plan，非法输入如何整体拒绝 |
| `ExecutionPlanExecutor.advance()` | 新结果如何验证、持久化、fan-in 和物化下游 |
| `ExecutionPlanExecutor.claim_next()` | 唯一节点如何原子认领并生成 dispatch |
| `OperationRegistry.resolve()/validate_startup()` | operation、授权、ledger 与 handler 是否唯一绑定 |
| `run_execution_plan_turn()` / Resume Handler | 无持久化 Turn/Resume 如何形成闭合 transition |
| `ExecutionPlanRequestService.handle()` | Session 聚合如何加载、提交并返回已提交结果 |
| SessionStore 命名 CAS | 授权、claim、receipt、恢复、reject 和重启收敛是否幂等 |
| `OutputIndexStore` | 稳定 output_id、版本、登记和删除是否一致 |
| `PlanResultPresenter.render()` | 是否只从 Plan 终态与 VerifiedOutcome 展示结果 |

## Target File Structure

### 新增

```text
backend/career_os/platform/worker/
├── bindings.py
├── plan.py
├── requests.py
├── transitions.py
└── presentation.py
backend/career_os/platform/operation/
├── models.py
├── canonical.py
├── ledger.py
├── registry.py
├── output_index_ledger.py
└── __init__.py
backend/career_os/platform/output/models.py
backend/career_os/platform/store/
├── execution_state.py
└── writer_lease.py
backend/career_os/agents/lc/invocation_analyze.py
backend/career_os/agents/graphs/execution_plan_coordinator.py
backend/career_os/api/execution_plan_requests.py
backend/tests/platform/test_execution_plan.py
backend/tests/platform/test_operation_registry.py
backend/tests/platform/test_durable_result_ledger.py
backend/tests/platform/test_plan_result_presenter.py
backend/tests/platform/test_output_index.py
backend/tests/agents/test_coordinator_execution_plan.py
backend/tests/api/test_execution_plan_requests.py
backend/tests/api/test_outputs_api.py
```

### 重点修改

```text
backend/career_os/agents/graphs/coordinator.py
backend/career_os/agents/state/coordinator.py
backend/career_os/agents/lc/coordinator_llm.py
backend/career_os/agents/lc/tools.py
backend/career_os/harness/{delegate,executor,gate}.py
backend/career_os/harness/pipeline_*.py
backend/career_os/harness/session_activity.py
backend/career_os/harness/chat_attachments.py
backend/career_os/api/{chat,sessions,market_research}.py
backend/career_os/runtime/sse.py
backend/career_os/platform/store/{session,output,__init__}.py
backend/career_os/platform/tool/registry.py
backend/career_os/platform/tool/handlers/outputs.py
backend/career_os/platform/market_research/{models,plans}.py
backend/career_os/main.py
web/src/hooks/useChatSSE.ts
web/src/pages/ChatPage.tsx
web/src/components/{OutputsPanel,TaskProgress}.tsx
web/src/lib/{chatAttachments,sessionsApi}.ts
```

### 最终删除

```text
backend/career_os/agents/graphs/workers/react_runner.py
backend/career_os/agents/schemas/workers.py
backend/career_os/platform/store/task.py
config/workers.registry.json
旧 Worker system Prompt 和旧 loader 读取路径
旧路径查看/删除产物路由
```

具体旧文件只有在调用方已迁移、负向搜索和测试覆盖后删除。

## Task 1: 建立 Outcome binding 与 ExecutionPlan 核心

**Files:**

- Create: `backend/career_os/platform/worker/bindings.py`
- Create: `backend/career_os/platform/worker/plan.py`
- Modify: `backend/career_os/platform/worker/registry.py`
- Create: `backend/tests/platform/test_execution_plan.py`
- Modify: `backend/typecheck/worker_invocation_contracts.py`

### Step 1: 写 resume → asset Plan 红灯测试

验证：

- Builder 创建 resume ready Invocation 与 asset blocked Node Spec；
- asset 在 delivery Outcome 绑定前 `invocation=None`；
- `RequiredOutcome` 只保存 source node、binding ID 和 minimum，不使用目标字段字符串；
- 空 delivery、错误来源节点、错误 Outcome 类型或跨 Plan 结果不能物化 asset；
- `PlanBuildRejected` 不携带 partial Plan，也不推进阶段。

### Step 2: 实现泛型 OutcomeBinding 和 Node Spec

实现 `OutcomeBinding[TOutcome, TPrepared, TInput]`、`RequiredOutcome` 与 15 个具体 Node Spec。binding 是纯函数，创建新 Input，不修改 PreparedInput/Outcome。

### Step 3: 实现 PlanBuilder

Builder 消费 Proposal、SessionRoutingFacts 和前置 Registry；Harness 代码补依赖、scope 和 binding。无依赖节点物化 Invocation 并 ready，有依赖节点保持 blocked。

### Step 4: 写 advance/claim 红灯测试

覆盖：

- `advance()` 只接受本批新结果，fan-in 从 Plan 已完成节点读取；
- plan/node/worker_run/mapping key/running 状态/重复结果任一错配返回原 Plan；
- 上游 success 且 Outcome 兼容时下游物化并 ready；其他终态下游 blocked_by_upstream；
- `advance()` 不返回 dispatch；
- `claim_next()` 原子执行唯一 ready→running、绑定未使用 worker_run_id 并返回同一结果中的新 Plan/PlanDispatch；
- 已有 running 节点时不能认领第二个节点。

### Step 5: 实现 Executor 与闭合结果

实现 `PlanBuilt/PlanBuildRejected`、`PlanAdvanceApplied/PlanAdvanceRejected`、`PlanClaimed/PlanNotClaimed` 和 `PlanDispatch`。调用方必须先采用结果中的新 Plan，再执行 dispatch。

### Step 6: 运行核心检查

```bash
cd backend && uv run pytest tests/platform/test_execution_plan.py -q
cd backend && uv run pyright typecheck/worker_invocation_contracts.py
```

## Task 2: 建立 OperationRegistry、durable ledger 与 delegate

**Files:**

- Create: `backend/career_os/platform/operation/{models,canonical,ledger,registry,__init__}.py`
- Modify: `backend/career_os/platform/tool/registry.py`
- Modify: `backend/career_os/harness/delegate.py`
- Modify: `backend/career_os/harness/executor.py`
- Modify: `backend/career_os/agents/lc/tools.py`
- Create: `backend/tests/platform/test_operation_registry.py`
- Create: `backend/tests/platform/test_durable_result_ledger.py`
- Modify: `backend/tests/harness/test_delegate_rules.py`
- Modify: `backend/tests/harness/test_delegate_capability_bundle.py`
- Modify: `backend/tests/agents/test_lc_tools.py`

### Step 1: 写 Registry/ledger 红灯测试

验证：

- `resolve(name)` 返回唯一冻结 Definition/handler；未知名称拒绝；
- 名称重复、缺 handler、多 handler、授权字段非法、ledger 缺失或非持久化时启动校验失败；
- 全部 Worker Definition 的 allowed operations 都能解析；
- ToolRegistry 只保存模型 Schema，不保存或执行 handler；
- durable ledger 只查询/保存已提交规范化结果，不拥有首次副作用执行权。

### Step 2: 实现 OperationRegistry 与 ledger Adapter

将现有业务 handler 注册到代码 Registry。调用方只能传 operation request，不能临时传 handler。为有副作用 operation 配置 durable ledger；读操作按定义明确无 ledger。

### Step 3: 写并实现 delegate_invocation

`delegate_invocation()` 接收具体 Invocation、授权事实投影、RuntimeContext 和 Preloader。验证角色、scope、operation、Skill 与执行策略；required Skill 成功后才返回 DelegatedInvocation。旧 `delegate_worker(worker_id, task, context)` 不再进入新路径。

### Step 4: 接入前置 operation 端口

实现生产 `HarnessOperationInvoker` Adapter，只通过 OperationRegistry 解析 handler。当前阶段负责授权与 `authorization_id` 幂等；全局失败机制再由 OperationExecutor 包装相同 Registry。

### Step 5: 运行 Registry/delegate 检查

```bash
cd backend && uv run pytest \
  tests/platform/test_operation_registry.py \
  tests/platform/test_durable_result_ledger.py \
  tests/harness/test_delegate_rules.py \
  tests/harness/test_delegate_capability_bundle.py \
  tests/agents/test_lc_tools.py -q
```

## Task 3: 重写 Coordinator analyze 为 InvocationProposal

**Files:**

- Create: `backend/career_os/agents/lc/invocation_analyze.py`
- Modify: `backend/career_os/agents/lc/coordinator_llm.py`
- Create: `backend/career_os/platform/prompt/coordinator/invocation_analyze_system.md`
- Modify: `backend/career_os/harness/pipeline_routing.py`
- Modify: `backend/career_os/harness/pipeline_phase_advance.py`
- Modify: `backend/career_os/harness/explore_closure.py`
- Modify: Coordinator 与 pipeline 相关测试

### Step 1: 写 analyze 红灯测试

验证：

- 输出为目标 `pipeline_phase + invocations`，没有字符串 workers；
- selectable phases 包含当前阶段，只在 Harness 前置条件和 Gate 允许时包含前向阶段；
- 模型动作索引只包含目标可选阶段允许的 Definition；
- 计算索引和解析 LLM/fallback 不写 Session、Task 或 Artifact；
- LLM 提交依赖、Tool、Skill、Contract 或非法阶段时结构化拒绝；
- fallback 只能选择显式规则定义的 Worker/Run Kind，并记录来源。

### Step 2: 拆分纯计算与状态提交

阶段可选性、动作索引和 Proposal 解析保持纯函数；只有 Builder 成功后的 state transition 才允许包含阶段推进。

### Step 3: 迁移 Coordinator Prompt

Prompt 只说明如何选择目标阶段和动作；删除旧 `pending_workers`、角色说明合成和控制事实猜测。

### Step 4: 运行 analyze 检查

```bash
cd backend && uv run pytest tests/agents/test_coordinator_routing.py tests/agents/test_coordinator_analyze.py tests/agents/test_coordinator_explore_phase.py tests/harness/test_pipeline_routing_phase.py tests/harness/test_pipeline_phase_advance.py -q
```

## Task 4: 建立 ExecutionPlan Coordinator、结果展示与最终聚合 Schema

**Files:**

- Create: `backend/career_os/agents/graphs/execution_plan_coordinator.py`
- Create: `backend/career_os/platform/worker/{requests,transitions,presentation}.py`
- Create: `backend/career_os/platform/store/execution_state.py`
- Modify: `backend/career_os/agents/state/coordinator.py`
- Create: `backend/tests/agents/test_coordinator_execution_plan.py`
- Create: `backend/tests/platform/test_plan_result_presenter.py`

### Step 1: 先发布最终请求、Transition 与 Session Schema

定义：

- `ExecutionPlanRequest` 闭合联合；
- `NewExecutionPlanTurnRequest`、授权确认和删除请求具体类型；
- `SessionTaskState`、各阶段 `SessionArtifactState`；
- 三类闭合 `SessionPendingGate`；
- `NoCurrentExecution | AsynchronousExecution | AuthorizationSuspendedExecution`；
- `SessionExecutionState` 初始工厂与窄事实投影。

Task 1–3 使用的事实对象改为只能从该聚合投影生成；它们不持久化，也不成为第二事实源。

### Step 2: 写 Turn 编排红灯测试

通过 `run_execution_plan_turn()` 验证 resume→asset、fan-in、单节点 running、Contract 映射、失败阻断、market async accepted 和 reuse gate transition。Handler 只返回尚未提交的 transition，不写 Store。

### Step 3: 实现唯一 Plan 循环

循环只能按 `build → claim → delegate/run → contract → PlanNodeResult → advance` 推进。授权等待返回包含完整暂停现场的 transition；同步终结返回 `NoCurrentExecution`。

### Step 4: 写并实现 PlanResultPresenter

Presenter 只读取终态 Plan/Result/Outcome，生成确定性 draft/artifact refs。不读取旧 summary、prior_results 或角色说明；非 success 不渲染为成功。

### Step 5: 运行 Coordinator/Presenter 检查

```bash
cd backend && uv run pytest tests/agents/test_coordinator_execution_plan.py tests/platform/test_plan_result_presenter.py -q
```

## Task 5: 建立 SessionStore、Gate 与 RequestService 事务

**Files:**

- Modify: `backend/career_os/platform/store/session.py`
- Create: `backend/career_os/platform/store/writer_lease.py`
- Modify: `backend/career_os/platform/store/__init__.py`
- Modify: `backend/career_os/harness/{gate,pipeline_gates}.py`
- Modify: 其他 pipeline 状态模块
- Create: `backend/career_os/api/execution_plan_requests.py`
- Create: `backend/tests/api/test_execution_plan_requests.py`
- Modify: Session、Gate、API 相关测试

### Step 1: 写 Session 聚合/CAS 红灯测试

验证初始 revision/phase/task/artifact/gate/current execution；revision 冲突、Artifact 版本倒退、跨 Session 引用和非法联合组合拒绝。聚合 JSON 使用临时文件、flush/fsync、原子 replace 和父目录同步发布。

### Step 2: 实现单写进程与聚合 Store

每个 DATA_DIR 只允许一个 `DataDirectoryWriterLease`。SessionStore 只读写 `execution-state.json`，不读取或迁移旧 Task/Artifact 数据。

### Step 3: 写并实现三类 Gate 生命周期

覆盖四类 Workflow reject、Additional Input 新 Turn、`reuse_confirm` 三选一和 Operation Authorization 原 Plan 恢复。旧 gate_id 不复用，Worker/Contract/mock 不创建 Gate。

### Step 4: 实现 ExecutionPlanRequestService

RequestService 集中加载聚合、调用无持久化 Handler、消费 transition 并 CAS 提交。普通 Turn 一次 CAS；授权 confirmation 使用命名多步 CAS。API 不预读 Session 或活动 Plan。

### Step 5: 运行 Store/Gate/RequestService 检查

运行所有新增 execution_state、Gate 与 execution_plan_requests 定向测试，并记录真实命令与结果。

## Task 6: 实现授权暂停、恢复、SSE 与前端确认

**Files:**

- Modify: `backend/career_os/platform/store/execution_state.py`
- Modify: `backend/career_os/platform/store/session.py`
- Modify: `backend/career_os/agents/graphs/execution_plan_coordinator.py`
- Modify: `backend/career_os/api/{chat,execution_plan_requests}.py`
- Modify: `backend/career_os/runtime/sse.py`
- Modify: `backend/career_os/main.py`
- Modify: `web/src/hooks/useChatSSE.ts`
- Modify: `web/src/pages/ChatPage.tsx`
- Modify: `web/src/lib/sessionsApi.ts`
- Modify/Create: 授权暂停、恢复、API、SSE 与前端测试

### Step 1: 写授权状态机红灯测试

覆盖：

- 先持久化 AuthorizationSuspendedExecution，再发送 SSE；
- confirmation 与 Session/Plan/node/worker_run/invocation/operation/参数摘要完全绑定；
- 相同 claim 唯一，跨实例或错配拒绝；
- operation 已提交/receipt 未写和 receipt 已写/Runner 未继续两个窗口均不重放副作用；
- ReAct 剩余 Tool Call 保持原顺序并逐项重新授权；
- deterministic 只从 committed receipt 完成；
- reject 形成 cancelled、阻断下游且不执行 handler；
- 快照清除后的重复请求返回终态 receipt。

### Step 2: 实现命名状态迁移与恢复 Handler

实现 `suspend/authorize/reject/claim/commit/resuspend/finalize`。Resume Handler 只在 receipt 已提交后运行，不重新 analyze、不重新调用 LLM、不重新生成 Tool Call。

### Step 3: 实现启动扫描最小收敛

新 runtime instance 取得 writer lease 后：rejected 收敛为 cancelled/rejected；其他旧活动快照收敛为 interrupted；两者保存终态 Plan/receipt、阻断下游并清除快照。重复扫描幂等，不接管 continuation。

### Step 4: 接入 API/SSE/前端

- Chat API 只构造具体 request 并调用 RequestService；
- SSE 新增结构化 `operation_confirmation_required`，`done` 只表示 HTTP 交付结束；
- 前端显示明确批准/拒绝控件并提交 confirmation_id/decision；
- 自然语言“同意”继续作为普通聊天输入，不产生授权。

### Step 5: 运行授权与前端构建

```bash
cd backend && uv run pytest tests/api/test_execution_plan_requests.py -q
cd web && npm run build
```

## Task 7: 引入稳定产物 ID、全局索引和授权删除

**Files:**

- Create: `backend/career_os/platform/output/models.py`
- Create: `backend/career_os/platform/operation/output_index_ledger.py`
- Modify: `backend/career_os/platform/store/output.py`
- Modify: `backend/career_os/platform/tool/handlers/outputs.py`
- Modify: `backend/career_os/platform/operation/registry.py`
- Modify: `backend/career_os/api/{sessions,execution_plan_requests}.py`
- Modify: `backend/career_os/harness/chat_attachments.py`
- Modify: `backend/career_os/agents/lc/tools.py`
- Modify: `web/src/components/OutputsPanel.tsx`
- Modify: `web/src/lib/chatAttachments.ts`
- Create: `backend/tests/platform/test_output_index.py`
- Create: `backend/tests/api/test_outputs_api.py`
- Modify: 产物 Store、Harness 和 e2e 测试

### Step 1: 写索引身份与 CAS 红灯测试

验证：

- 唯一文件是 `settings.data_dir / "outputs-index.json"`，干净目录初始化 schema v2；
- output_id 全局唯一且路径/显示名变化不改变身份；
- 全局 index_version 对所有 Session 写入严格递增；
- register 只接受 verified deliveries 和 expected version；
- 相同删除授权绑定重放返回首次 receipt 且版本不再递增；
- 不同绑定、跨 Session、旧版本或路径伪造拒绝；
- 进程重建后 ledger 仍能读取首次提交结果。

### Step 2: 实现 OutputIndexStore 与 ledger Adapter

Store 管理真实索引和领域 handler；ledger Adapter 只映射已提交结果，不制造 receipt。登记/删除快照原子写入。

### Step 3: 实现深 RequestService 删除接口

API 只传 `session_id + output_id + expected_index_version`。RequestService 解析目标、冻结 confirmation binding、校验确认快照并调用 Registry handler；API 不预读索引或传 frozen path。

### Step 4: 迁移公开接口与前端

列表、查看、拖拽、附件和删除只使用 output_id；公开 DTO 不返回内部 path；删除旧 view-by-path 和 path-delete 路由。

### Step 5: 运行索引/产物检查

```bash
cd backend && uv run pytest tests/platform/test_output_index.py tests/api/test_outputs_api.py tests/e2e/test_asset_register.py -q
cd web && npm run build
```

## Task 8: 最终主链切换、启动校验与旧事实源清除

**Files:**

- Modify: `backend/career_os/agents/graphs/coordinator.py`
- Modify: `backend/career_os/agents/state/coordinator.py`
- Modify: `backend/career_os/api/{chat,sessions}.py`
- Modify: `backend/career_os/runtime/sse.py`
- Modify: `backend/career_os/main.py`
- Modify: `backend/career_os/platform/{worker,operation,tool}/**`
- Modify: `web/src/components/TaskProgress.tsx`
- Delete: 目标结构中列出的旧文件和配置
- Modify/Delete: 只验证旧架构的测试

### Step 1: 将真实入口切到 RequestService

真实链路必须成为：FastAPI Session 建立 → ChatOrchestrator begin_chat → `_chat_stream` → ExecutionPlanRequestService → analyze/build/claim/delegate/Runner/Contract/advance → committed transition → Presenter → SSE。ChatOrchestrator 仍只负责同 Session 并发标记与上下文提醒，不成为 Coordinator 的前置中间层。

### Step 2: 启用完整启动校验

应用启动前验证：

- 15 个 Definition/Prompt/Skill/Contract/Adapter 完整；
- 全部 allowed operation 可由唯一 OperationRegistry 解析；
- 每项 operation 恰有一个 handler，授权与 ledger 组合合法；
- OutputIndex、Session 聚合和 DATA_DIR writer lease 配置可用；
- 任一失败阻止启动，不降级到旧路径。

### Step 3: 删除旧事实来源

删除字符串 `pending_workers/current_worker_id`、四参数 Runner、旧 Worker 通用 Schema、旧 summary 增强入口、旧 TaskStore、`config/workers.registry.json`、路径产物身份和 `list_type="plan"` 执行旁路。不存在 legacy Adapter 或 fallback。

### Step 4: 重写测试到新接口

删除只验证旧浅模块内部状态的测试；保留业务行为并改到新深模块接口。fake 必须注册到同一 Registry/Store seam，不绕开 Harness。

## Task 9: 全量验收与范围审计

### Step 1: 负向搜索旧接口

```bash
rg -n 'pending_workers|current_worker_id|runner\(worker_id|build_stub_worker_runner\(|workers\.registry\.json|get_litellm_tools_for_worker' backend config
rg -n 'WORKER_SCHEMAS|validate_structured_output|enhance_worker_summary_with_llm|user_visible_summary|session_state: dict\[str, Any\]' backend/career_os
rg -n 'target_input_field|inputs: BaseModel|verified_outcomes: Mapping\[str, Any\]|OutcomeBinding\[Any' backend/career_os/platform/worker backend/typecheck
rg -n 'handler[=:]|ToolDefinition\([^)]*handler|ToolRegistry.*execute' backend/career_os/platform/tool
rg -n 'TaskStore|platform\.store\.task|list_type="plan"|LegacyCareerPlanAdapter' backend/career_os web/src backend/tests
rg -n 'view\?path|encoded_path|attachment\.path|delivery_id|delete_output\([^)]*path' web/src backend/career_os backend/tests
rg -n 'profile\.outputs_index|ProfileStore.*outputs_index|frozen_target' backend/career_os backend/tests
```

期望：默认代码与最终测试 fixture 不命中旧接口。负向测试文字和历史文档不作为运行时命中。

### Step 2: 运行定向回归

运行本 Plan 全部新增测试，以及 Coordinator、Harness、Session、Gate、market、resume/asset、API、SSE、产物和前端相关测试。每条失败必须先判断是目标行为缺失还是旧契约测试未迁移，不能通过恢复兼容层解决。

### Step 3: 运行完整验收

```bash
cd backend && uv run pytest tests/ -m "not llm" -q
cd backend && uv run pyright
cd web && npm run build
```

真实 LLM Eval 不在默认验收中；只有用户明确授权且 Provider/Key 可用时才执行，并单独记录外部运行结果。

### Step 4: 干净环境行为检查

使用新的 DATA_DIR 验证：初始 Session 聚合、resume→asset 成功与空 delivery 阻断、授权暂停/批准/拒绝、重启最小收敛、市场启动接收、产物登记/查看/删除和重复请求幂等。该检查只证明本规格行为，不替代全局失败机制的最终 Bug 系统回归。

### Step 5: 文档与版本证据

完成后检查根 README、`docs/roadmap/v2.2.md` 和相关架构文档。只有代码、测试和可复现运行证据支持的能力才能写为已实现；测试命令、日期、失败和跳过均如实记录。

## Completion Criteria

1. 前置 15 类契约通过唯一 ExecutionPlan 主链投入运行。
2. Plan Builder、advance、claim、dispatch 和 Outcome binding 满足设计规格。
3. Coordinator、Session、Gate、授权、API、SSE 与前端只使用新类型化接口。
4. OperationRegistry、ledger、handler 和 Tool Schema 各自职责唯一，无第二执行 seam。
5. OutputIndex 使用稳定 output_id、全局版本和幂等删除 receipt。
6. 旧字符串队列、旧 Runner、旧 Task/Session 事实、路径产物身份和 legacy 纯规划旁路删除。
7. 全部非 LLM 测试、Pyright 和前端构建通过，或如实记录阻塞；未通过不得称为完成。
8. 新系统从干净数据目录验收，不迁移旧运行数据。
9. 没有提前实现全局 Failure、重试、Judge、Run Store、授权 TTL 或 Trace exactly-once。
10. 全局失败机制可以直接消费 PlanDispatch、PlanNodeResult、ExecutionPlan、OperationRegistry 和授权状态机，无需兼容 Adapter 或重新编号。

## Suggested Commit

仅在用户另行要求创建 commit 时使用：

```text
refactor(plan): 接入执行计划与受控生命周期

- 通过 ExecutionPlan 管理依赖绑定、节点认领和已验证结果传播
- 统一 Session、Gate、operation 授权和产物索引的持久化状态
- 完成 Coordinator、API、SSE 与前端主链切换并清除旧事实来源
```
