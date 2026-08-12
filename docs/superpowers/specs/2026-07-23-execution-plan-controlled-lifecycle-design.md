# ExecutionPlan 与受控执行生命周期设计规格

| 属性 | 内容 |
|------|------|
| 状态 | **已确认，待实施** |
| 版本 | **1.0.0** |
| 日期 | 2026-07-23 |
| 直接前置规格 | [强类型 WorkerInvocation 与结果契约](./2026-07-23-typed-worker-invocation-contract-design.md) |
| 直接后续规格 | [全局失败机制](./2026-07-23-global-failure-mechanism-design.md) |
| 实施计划 | [ExecutionPlan 与受控执行生命周期 Implementation Plan](../plans/2026-07-23-execution-plan-controlled-lifecycle.md) |
| 领域语言 | [CONTEXT.md](../../../CONTEXT.md) |

---

## 1. 背景与定位

前置规格定义了“某次 Worker 调用是什么”和“什么业务结果可以被信任”，但没有回答调用如何进入当前产品主链。当前代码仍使用字符串 `pending_workers`、`current_worker_id`、四参数 Runner、分散的 Session/Task/Artifact Store、路径产物身份和多个授权入口；上游失败后，下游仍可能从摘要、上下文或默认值继续。

本规格是一次性系统重写的第二阶段。它把前置契约模块接入唯一产品主链，回答四个问题：

1. Harness 如何冻结节点、依赖和结果绑定；
2. Coordinator 如何在一次只运行一个节点的前提下推进 Plan；
3. Session、Gate、授权暂停与 operation receipt 如何跨请求保持唯一事实；
4. API、SSE 和前端如何只消费已经提交的执行状态。

本规格完成并通过全部验收后，才满足全局失败机制的实施前置。

## 2. 设计原则

1. **Harness 定义依赖**：LLM 只提议 Worker/Run Kind 和目标阶段，不提供依赖、Outcome binding、Tool、Skill、Contract 或失败策略。
2. **先验证再发布**：Plan 构建、推进和 Session 更新都返回闭合结果；失败不得发布部分 Plan 或部分聚合。
3. **认领是唯一 dispatch seam**：只有 `claim_next()` 能原子执行 `ready → running`、绑定 `worker_run_id` 并产生 `PlanDispatch`。
4. **Plan 累积结果**：finished 节点保存不可变 `PlanNodeResult`，fan-in 从 Plan 历史读取，不依赖调用方重复传旧结果。
5. **单一聚合事实源**：阶段、Gate、当前 Task、Artifact、CurrentExecution 和回执由一个 `SessionExecutionState` 以 revision CAS 发布。
6. **授权不重新规划**：授权确认恢复同一 Plan、节点、Invocation、Worker Run、operation call 和 continuation，不重新运行 analyze。
7. **operation 定义唯一**：`OperationRegistry.resolve()` 一次返回 Definition 与 handler 绑定；调用方不能传 handler。
8. **稳定业务身份**：产物使用 `output_id`，索引使用全局 `index_version`，删除绑定 Session、产物、operation 和预期版本。
9. **临时展示不重定义成功**：`PlanResultPresenter` 只从 Plan 终态与 VerifiedOutcome 生成草稿，后续由全局失败机制的 Turn Result Renderer 替换。
10. **最终替换而非兼容叠加**：完成时删除旧队列、旧 Runner、旧 Session/Task 状态和路径对外接口。

## 3. 目标与非目标

### 3.1 目标

- 建立强类型 Outcome binding、Plan Node Spec、ExecutionPlan、PlanDispatch、PlanNodeResult 和推进结果。
- 让 `ExecutionPlanBuilder.build()` 只返回完整 `PlanBuilt` 或结构化 `PlanBuildRejected`。
- 让 `ExecutionPlanExecutor.advance()` 与 `claim_next()` 成为计划推进和认领唯一接口。
- 将 Coordinator analyze 改为 InvocationProposal，建立唯一 ExecutionPlan 主链。
- 建立 `SessionExecutionState`、闭合 Gate、当前执行分支与单写进程 CAS 持久化。
- 建立 `OperationRegistry`、durable result ledger、授权暂停/恢复和幂等 receipt。
- 建立稳定产物 ID、全局版本索引与授权删除。
- 完成 API、SSE 和前端迁移，清除旧事实来源。

### 3.2 非目标

- Failure 分类、策略级重试、降级、补偿、断路器、语义 Judge 和最终 Run 状态；
- Trace exactly-once 投递、授权 TTL 或 confirmation 自动过期；
- 应用重启后接管旧执行；旧实例的未完成状态只做最小 interrupted/rejected 收敛；
- Turn 内并发 Worker；第一版一次只有一个节点 running；
- 正式 Job Run 与 Job ExecutionPlan；`market.start_research` 只验收后台 Job 已持久化且启动被接受；
- 旧 DATA_DIR 的 Session、Task、Artifact 或输出索引迁移；新系统从干净目录验收；
- `strategy.career_plan` 纯规划链；不保留 `list_type="plan"` 旁路；
- 当前 Bug 的最终全局失败回归；该回归在全局失败机制完成后执行。

## 4. 前置契约与模块接口

本规格只消费前置规格提供的闭合 Definition、Invocation、WorkerStructuredOutput、VerifiedOutcome、ContractEvaluation、统一 Runner、暂停现场、continuation 和 operation 调用端口，不复制这些类型或契约 handler。

本阶段形成以下深模块接口：

| 模块接口 | 含义 | 作用 |
|----------|------|------|
| `ExecutionPlanBuilder.build()` | 计划构建接口 | 将合法 Proposal 和 Session 投影转换为完整 Plan 或结构化拒绝 |
| `ExecutionPlanExecutor.advance()` | 计划推进接口 | 验证新节点结果、持久化到 Plan 并物化满足依赖的下游 Invocation |
| `ExecutionPlanExecutor.claim_next()` | 节点认领接口 | 原子绑定唯一 Worker Run 身份并生成不可变 dispatch |
| `OperationRegistry.resolve()` | operation 解析接口 | 返回唯一冻结 Definition/handler 绑定 |
| `ExecutionPlanRequestService.handle()` | 请求事务接口 | 加载 Session 聚合、运行 Turn/Resume Handler、CAS 提交并返回已提交结果 |
| `OutputIndexStore` | 产物索引接口 | 管理稳定 output_id、全局版本和幂等登记/删除 |

API、页面和测试都只通过这些接口，不预读内部 Store 或拼装运行快照。

## 5. Outcome binding 与节点规格

### 5.1 OutcomeBinding

`OutcomeBinding[TOutcome, TPreparedInput, TInput]`（结果绑定定义）用泛型静态关联上游具体 Outcome、下游准备输入和完整输入。

| 字段 | 含义 | 作用 |
|------|------|------|
| `binding_id` | 稳定绑定编号 | 让 Plan 快照引用代码中的唯一绑定函数 |
| `source` | 上游具体 OutcomeDefinition | 限定允许消费的命名结果及类型 |
| `prepared_input_model` | 下游准备输入类型 | 限定绑定前已经冻结的事实 |
| `input_model` | 下游完整输入类型 | 限定绑定后可交给 Registry.resolve 的模型 |
| `bind` | 纯绑定函数 | 根据 PreparedInput 与具体 Outcome 创建新的完整 Input |

`RequiredOutcome`（必需结果）只保存 `source_node_id`、`binding_id` 与可选 `minimum`。`source_node_id` 是来源节点编号，用于阻止跨节点或跨 Plan 结果注入；`minimum` 是列表类结果的最小数量，用于阻止空集合满足依赖。禁止使用 `target_input_field: str` 动态写字段。

`resume.generate_optimized_resume → asset.register_outputs` 必须使用具体 `bind_verified_html_deliveries(prepared, outcome)`；只有 `VerifiedHtmlDeliveriesOutcome` 能创建完整 `RegisterOutputsInput`。

### 5.2 ExecutionPlanNodeSpec

`ExecutionPlanNodeSpec[TPreparedInput]`（计划节点规格）是 Harness 在 Plan 创建时冻结的执行意图，不是 Invocation，不能交给 Runner。

| 字段 | 含义 | 作用 |
|------|------|------|
| `node_id` | 节点编号 | 关联依赖、结果、Worker Run 和 Trace |
| `definition_id` | 动作定义编号 | 证明节点使用哪个前置 Definition |
| `worker_id` / `run_kind` | 具体动作 discriminator | 缩窄 PreparedInput 和后续 Invocation 类型 |
| `goal` | 本节点业务目标 | 向 Worker 说明动作，不代替控制字段 |
| `prepared_inputs` | 深冻结准备输入 | 保存 Plan 创建时已有事实 |
| `required_outcomes` | 依赖结果集合 | 指定来源节点、绑定函数和最小数量 |
| 能力与契约快照 | operation、Skill、执行策略、Contract、Judge 模式 | 防止运行中 Registry 变化改写已批准节点 |

存在 RequiredOutcome 的节点在 Plan 创建时只能保存 Node Spec，`invocation=None`；不得构造输入不完整的 Invocation。

## 6. ExecutionPlan 模型

### 6.1 节点与结果

`ExecutionPlanNode`（执行计划节点）包含 `spec`、可选 `invocation`、`status`、依赖编号、可选 `worker_run_id` 与可选终态 `result`。

节点状态为：

- `blocked`：依赖尚未完成；
- `ready`：Invocation 已物化且可认领；
- `running`：已经由 `claim_next()` 绑定 Worker Run；
- `waiting_authorization`：当前 Worker Run 暂停等待 operation 授权；
- `success` / `failed` / `cancelled` / `interrupted`：终态；
- `blocked_by_upstream`：上游未以兼容 VerifiedOutcome 成功完成，永不 dispatch。

`PlanNodeResult`（计划节点结果）是 Worker 执行结果经确定性 Contract 验收后的最小计划投影，包含 `plan_id + node_id + worker_run_id + status + verified_outcomes + error`。它不保存 Worker 用户摘要，也不自行分类全局 Failure。

### 6.2 ExecutionPlan

`ExecutionPlan`（执行计划）是节点、依赖、当前状态与累积结果的不可变唯一事实源。

| 字段 | 含义 | 作用 |
|------|------|------|
| `plan_id` | 计划编号 | 关联 Turn、节点、授权、Trace 和后续 Run |
| `session_id` | 会话编号 | 隔离 Session 状态和产物 |
| `revision` | Plan 修订号 | 保证更新基于最新快照 |
| `scope` | pipeline 阶段范围 | 限定本 Plan 可以包含的动作 |
| `nodes` | 不可变节点 tuple | 保存顺序、Invocation、Worker Run 和终态结果 |
| `status` | Plan 状态 | 表示 pending/running/waiting/terminal，而非用户消息状态 |

Plan 深冻结；调用方必须采用 Builder/Executor 返回的新 Plan，不能修改原对象或只保存 dispatch。

### 6.3 PlanBuilder

`ExecutionPlanBuilder.build()`（构建执行计划）执行：

1. 校验 Proposal 的目标阶段是否在 Harness 计算的 selectable phases；
2. 用前置 Registry 创建具体 Node Spec；
3. 由 Harness 补充依赖和 RequiredOutcome；
4. 校验 DAG、来源节点、binding 类型、scope 和能力快照；
5. 为无依赖节点解析 Invocation 并置为 ready；有依赖节点保持 blocked；
6. 返回 `PlanBuilt(plan, state_transition)` 或 `PlanBuildRejected(errors)`。

拒绝结果不得携带部分 Plan，也不得提前推进阶段或写 Store。

### 6.4 advance 与 claim_next

`advance(plan, new_results)`（推进计划）只消费本批新结果：

- 先验证 plan/node/worker_run 身份、running 状态、重复结果和结果类型；任一错误返回原 Plan；
- 验证通过后把结果持久化到 finished 节点；
- 从 Plan 中读取全部历史 finished 结果完成 fan-in；
- 只有来源节点 success 且 Outcome 名称、类型、数量满足 RequiredOutcome，才调用 binding 创建完整 Input 并通过 Registry 物化下游 Invocation；
- 上游失败、取消、中断或契约不满足时，下游置为 `blocked_by_upstream`；
- `advance()` 只产生 ready 节点，不 dispatch。

`claim_next(plan, worker_run_id)`（认领下一个节点）是唯一 dispatch seam：

- 当前已有 running/waiting 节点时返回未认领结果；
- 选择唯一 ready 节点，验证 Worker Run 编号非空且未被本 Plan 使用；
- 在同一个不可分割结果中返回新 Plan 与 `PlanDispatch`；
- `PlanDispatch` 冻结 `plan_id + node_id + worker_run_id + invocation`，Runner 和后续全局失败机制必须完整消费该包络。

## 7. Coordinator 与 Turn 编排

### 7.1 analyze

Coordinator LLM 只输出：

- `pipeline_phase`：目标阶段提议；
- `invocations`：`InvocationProposal` tuple。

Harness 根据当前 `SessionExecutionState` 纯计算 selectable phases 和模型动作索引。LLM 不得提交依赖、Tool、Skill、Contract、Gate 或授权。非法提议返回结构化计划拒绝；只有显式规则 fallback 能替代 LLM 提议，Trace 必须记录来源。

### 7.2 delegate 与运行

`delegate_invocation()`（委托 Invocation）接收具体 Invocation、授权事实投影、RuntimeContext 与 RequiredSkillPreloader。它校验角色、阶段、operation/Skill 包络并完成 required Skill 预加载，成功后返回 `DelegatedInvocation`；失败不调用 Runner。

`run_execution_plan_turn()`（运行 ExecutionPlan 本轮）是无持久化 Handler：构建 Plan、反复 claim 唯一 ready 节点、委托并运行、用 Contract 将终态执行结果映射为 PlanNodeResult、advance Plan，直到终结或等待授权。它返回尚未提交的 `ExecutionPlanStateTransition`，不能直接写 Session。

同步工作只在当前请求内运行，不放入 `CurrentExecution`。只有真正跨请求异步 Plan 和授权暂停 Plan进入 Session 的当前执行槽位。

### 7.3 临时 PlanResultPresenter

`PlanResultPresenter.render()`（展示计划结果）只从终态 Plan、PlanNodeResult 和 VerifiedOutcome 生成确定性 `synthesis_draft + artifact_refs`：

- 不读取旧 Worker summary、`prior_results` 或角色说明；
- 不把 failed/cancelled/interrupted/blocked_by_upstream 渲染为成功；
- 只引用已验证并已提交的产物；
- 作为临时展示模块，由全局失败机制的 Turn Result Renderer 替换，不改变 Plan/Contract/Outcome 成功语义。

## 8. SessionExecutionState 聚合

`SessionExecutionState`（会话执行状态）是阶段、Gate、当前 Task、Artifact、执行暂停和回执的唯一持久化聚合。

| 字段 | 含义 | 作用 |
|------|------|------|
| `session_id` | 会话编号 | 隔离本地会话状态 |
| `revision` | 聚合修订号 | 通过 CAS 阻止丢失更新 |
| `pipeline_phase` | 当前产品阶段 | 决定合法前向动作 |
| `task_state` | 当前任务控制状态 | 为 `/v1/tasks` 提供当前投影，不保留旧任务事实源 |
| `artifacts` | 各阶段 Artifact 引用与版本 | 让 Worker 输入只读取已提交事实，并阻止版本倒退 |
| `pending_gate` | 唯一当前 Gate | 保存闭合 Gate 类型及身份 |
| `current_execution` | 唯一当前跨请求执行 | 区分无执行、异步执行和授权暂停 |
| `last_terminal_execution_plan` | 最近终态 Plan | 供页面、恢复幂等和审计读取 |
| `operation_confirmation_receipts` | confirmation 终态回执集合 | 快照清除后仍幂等返回原决定 |

初始工厂固定 revision 0、phase explore、task not_started、空 Artifact、无 Gate、`NoCurrentExecution`。不读取或迁移旧 Session/Task/Artifact 数据。

`CurrentExecution`（当前跨请求执行）是闭合联合：

- `NoCurrentExecution`：没有跨请求执行；
- `AsynchronousExecution`：未来真正跨请求且不等待授权的 Plan；当前 market 后台 Job 不使用该分支；
- `AuthorizationSuspendedExecution`：保存完整 Plan、SuspendedWorkerRun、OperationContinuation 和 AuthorizationWait。

## 9. Gate 生命周期

三类 Gate 使用不同模型和生命周期，不能复用裸 `gate_id + gate_type + payload dict`：

1. `WorkflowTransitionGate`：控制阶段前进；reject 后按具体 Gate 规则停留或重新开放前一阶段。
2. `AdditionalInputGate`：收集执行所需业务输入，例如优化档位或 `reuse_confirm` 三选一；选择在新 Turn 创建新 Plan，不恢复旧 Plan。
3. `OperationAuthorizationGate`：授权当前已冻结 operation；确认恢复同一 Plan 和 Worker Run，不重新 analyze。

四类 Workflow reject 语义固定：重新开放 explore、停留 market 不启动研究、创建市场结果后续选择 Gate、停留策略阶段不执行优化。旧 Gate ID 不复用。

`reuse_confirm` 必须由 Harness 从 `ReuseRecommendationOutcome` 创建，包含 `reuse_existing / regenerate / cancel` 三个闭合选项；Worker、Contract、mock 或 LLM 不得创建 Gate、默认选择或后续 Proposal。

## 10. OperationRegistry 与持久化结果账本

### 10.1 OperationDefinition

`OperationDefinition`（操作定义）集中保存 operation 名称、授权要求和 durable ledger 绑定。

| 字段 | 含义 | 作用 |
|------|------|------|
| `operation_name` | 稳定操作名称 | 关联 Tool、授权、receipt、Trace 和后续策略 |
| `requires_authorization` | 是否需要用户授权 | 决定执行前是否创建授权暂停状态 |
| `durable_result_ledger_id` | 持久化账本编号 | 为有副作用 operation 提供提交结果查询与幂等重放 |

`OperationRegistry.resolve(name)`（解析 operation）返回唯一冻结 `ResolvedOperation(definition, handler)`。Registry 不接受调用方临时注册 handler；`ToolRegistry` 只保存模型可见名称、角色与参数 Schema，不拥有或执行 handler。

`validate_startup()`（启动校验）验证名称唯一、每项恰有一个同名 handler、授权字段组合合法、声明的 ledger 存在且持久化，以及全部 Worker Definition 的 allowed operations 都可解析。

### 10.2 DurableResultLedgerRegistry

`DurableResultLedgerRegistry`（持久化结果账本目录）只提供 `load_committed_result()` 与 `save_committed_result()`，用于查询和保存已提交的规范化 operation 结果。Ledger 不拥有业务副作用首次执行权，也不是领域 handler。

当前 Harness 通过 `HarnessOperationInvoker` 调用 Registry 解析出的 handler，并以 `authorization_id` 保证幂等。全局失败机制的唯一 `OperationExecutor` 必须继续调用同一个 `OperationRegistry.resolve()`，不得建立第二条执行 seam。

## 11. 授权暂停、恢复与崩溃收敛

### 11.1 暂停

需要授权时，普通 Turn 在发送 SSE 前必须先把以下对象一次 CAS 持久化：

- 当前 Plan 与 running 节点；
- `SuspendedWorkerRun` 与闭合 `OperationContinuation`；
- `OperationAuthorizationWait`，包含 confirmation、operation call、参数摘要、Plan/节点/Worker Run/Invocation 身份；
- `AuthorizationSuspendedExecution` 作为唯一 `current_execution` 分支。

随后 API 才发送结构化 `operation_confirmation_required` SSE。自然语言“同意”不授予权限，前端必须通过明确控件提交 `{confirmation_id, decision}`。

### 11.2 恢复状态机

`SessionStore` 提供命名状态迁移：`suspend → authorize/reject → claim → commit_authorized_operation_result → resuspend/finalize`。

- confirmation 必须与 Session、Plan、节点、Worker Run、Invocation、operation call 和参数摘要全部匹配；
- claim 是相同授权恢复权的唯一占用；重复 claim 或跨实例 claim 拒绝；
- 底层 handler 以 `authorization_id` 幂等；operation 已提交但 receipt 尚未写入时从 ledger 补写，不能重放副作用；
- receipt 已写入但 Runner 尚未继续时，只调用 `resume_worker_invocation()`；
- ReAct continuation 对每个剩余 Tool Call 在执行前重新校验 operation、参数、资源状态、预算、策略与授权；下一授权点使用新 confirmation 再次暂停；
- deterministic continuation 只消费 committed receipt 完成原 Adapter；
- 用户 reject 把当前节点以原身份收敛为 cancelled，下游 blocked_by_upstream，不执行 operation。

### 11.3 重启收敛

每个 DATA_DIR 只允许一个 `DataDirectoryWriterLease` 持有者写入。新实例取得 lease 后扫描旧 `runtime_instance_id`：

- 已持久化 rejected 的快照继续收敛为 `cancelled/rejected`；
- 其他未完成快照收敛为 `interrupted`；
- 两者都阻断下游，保存终态 Plan 和 confirmation receipt，并清除 active snapshot；
- 重复扫描或重复 confirmation 幂等返回同一终态身份；
- 不接管旧 continuation，不实现授权 TTL，Trace exactly-once 留给全局失败机制。

## 12. OutputIndex 与删除授权

`settings.data_dir / "outputs-index.json"` 是跨 Session 的全局 schema v2 索引唯一事实源。干净目录首次创建空索引，不读取或迁移旧 `profile.outputs_index`。

| 字段 | 含义 | 作用 |
|------|------|------|
| `output_id` | 稳定产物编号 | 对外查看、附件、拖拽和删除的唯一身份；路径变化不改变编号 |
| `session_id` | 所属会话编号 | 阻止跨 Session 访问和删除 |
| `index_version` | 全局索引版本 | 通过 expected version CAS 阻止并发丢失更新 |
| 内部规范路径 | 本地产物位置 | 只在 Store 内解析，不通过公开列表或前端传递 |

`OutputIndexStore.read_snapshot()`（读取索引快照）可返回全部或按 Session 过滤的条目，但版本始终是同一个全局版本。`register()`（登记产物）只接受 verified deliveries 和预期版本，生成稳定 output_id 并使版本 +1。

删除采用两步授权：

1. 请求只提交 `session_id + output_id + expected_index_version`；`ExecutionPlanRequestService` 解析目标并冻结 `DeleteOutputConfirmationBinding`。
2. confirm URL 携带 output_id/confirmation，RequestService 交叉校验快照中的全部身份，再通过 `OperationRegistry.resolve("delete_output")` 执行一次幂等 handler。

`OutputDeletionReceipt` 绑定 `authorization_id + session_id + output_id + operation + expected_index_version`。相同绑定重试返回首次结果且不递增版本；不同绑定、跨 Session 或版本冲突明确拒绝。API 不预读索引或拼装 `frozen_target`。

前端和聊天附件只传 output_id；公开列表不返回内部 path，旧 `/outputs/view?path=...` 与路径删除接口必须删除。

## 13. RequestService、API 与 SSE

`ExecutionPlanRequestService.handle(request)`（处理执行计划请求）是唯一 Session 持久化事务接口：

1. 加载 `SessionExecutionState`；
2. 把具体 NewTurn/Confirmation/Delete 请求交给无持久化 Handler；
3. 执行命名 CAS 序列；
4. 只返回已经提交的状态、Plan 展示结果和 SSE 事件。

普通 Turn 使用一次聚合 CAS；confirmation 因底层 operation 提交事实需要使用命名多步 CAS。Handler、Coordinator 和 API 都不能直接写 Session。

API 只负责 HTTP 参数校验和 Request 构造，不预读 Session、OutputIndex 或活动 Plan。SSE 区分：

- `token`：已提交结果的增量正文；
- `operation_confirmation_required`：已经持久化的授权请求；
- `done`：本次 HTTP 交付结束，不等同于业务 Plan success。

前端根据结构化事件展示确认控件和执行状态；不能用自然语言消息模拟授权。

## 14. 关键流程

### 14.1 resume → asset

1. Builder 创建 resume Invocation 与 blocked asset Node Spec；
2. `claim_next()` 原子认领 resume，Runner 执行；
3. Contract 只有在 HTML delivery 确定性验证通过时产生 `VerifiedHtmlDeliveriesOutcome`；
4. `advance()` 保存 resume 结果并通过具体 binder 创建 asset 完整 Input/Invocation；
5. asset 才能变为 ready 并被下一次 claim；
6. resume failed、空 delivery、取消或中断时 asset 为 blocked_by_upstream，不创建 Worker Run、不执行 operation、不登记产物。

### 14.2 市场研究

1. propose/revise 只产生待确认方案 Outcome；
2. confirmation 持久化稳定 confirmation_id，版本变化使旧编号失效；
3. `market.start_research` 验证同一 Session/版本/摘要，持久化 Job 并由现有 Runner 接受启动；
4. Contract 产生 `JobAcceptedOutcome` 后当前节点立即 success，当前同步 Plan 终结；
5. 后台 Job 独立推进，不创建 `AsynchronousExecution`；正式 Job Run 留给全局失败机制。

### 14.3 产物复用

`asset.reuse_outputs` success 后当前 Plan 终结并由 Harness 创建 `reuse_confirm` AdditionalInputGate。用户三选一在新 Turn 创建后续 Plan，不恢复旧 Plan、不默认选择，也不把 Gate 决策交给 Worker。

## 15. 测试 seam

| seam | 必须验证的行为 |
|------|----------------|
| `ExecutionPlanBuilder.build()` | 依赖、scope、binding 和准备输入如何形成完整 Plan 或结构化拒绝 |
| `ExecutionPlanExecutor.advance()` | 新结果如何先验证后持久化，fan-in 如何读取 Plan 历史并物化下游 |
| `ExecutionPlanExecutor.claim_next()` | 唯一 ready 节点如何原子绑定 Worker Run 并生成 dispatch |
| `OperationRegistry.resolve()/validate_startup()` | operation 定义、handler、授权与 ledger 是否唯一绑定 |
| `run_execution_plan_turn()` / Resume Handler | 无持久化编排是否形成闭合 state transition |
| `ExecutionPlanRequestService.handle()` | Session 聚合是否按命名 CAS 提交并只返回已提交结果 |
| SessionStore 命名状态迁移 | 授权暂停、claim、receipt、恢复、reject 和重启收敛是否保持身份与幂等 |
| `OutputIndexStore` | 稳定 output_id、全局版本、登记/删除与崩溃重放是否一致 |
| `PlanResultPresenter.render()` | 是否只从终态 Plan 与 VerifiedOutcome 生成草稿 |
| API/SSE/前端集成 | 结构化授权、产物身份和执行/交付状态是否端到端一致 |

测试只通过公开接口和 fake Adapter，断言可观察状态与结果，不断言私有字典、锁或内部调用次数。

## 16. 验收标准

1. Plan Builder 只返回完整 Plan 或结构化拒绝，不发布 partial/invalid Plan。
2. 所有依赖使用具体 OutcomeBinding；没有动态字段写入或从摘要/default 补结果。
3. `advance()` 先验证后持久化，fan-in 从 Plan 历史读取；错误输入返回原 Plan。
4. `claim_next()` 是 ready→running、worker_run_id 绑定和 dispatch 的唯一接口，一次只有一个节点 running。
5. Runner/后续 RunEngine 完整消费 PlanDispatch，Plan/节点/Worker Run 身份端到端不变。
6. Coordinator 只输出 InvocationProposal；`pending_workers`、`current_worker_id` 和四参数 Runner 从最终代码与测试删除。
7. Required Skill、Prompt、Tool 与执行策略只由 Invocation 快照决定。
8. `SessionExecutionState` 是阶段、Gate、Task、Artifact、CurrentExecution 和回执唯一事实源；旧 TaskStore/旧历史任务 DTO 删除。
9. 三类 Gate 和四类 Workflow reject 语义符合本规格；operation 授权不重新规划。
10. 授权暂停、claim、底层提交、receipt、恢复与拒绝保持同一身份，两个崩溃窗口均不重放副作用。
11. OperationRegistry 是 operation 名称、授权、ledger 与 handler 的唯一绑定来源；ToolRegistry 不执行 handler。
12. OutputIndex 是全局 schema v2 唯一事实源；对外只使用稳定 output_id 和 expected index version。
13. `market.start_research` 只有经 Contract 验证的 JobAcceptedOutcome 才让当前节点 success；后台 Job 独立运行。
14. 临时 PlanResultPresenter 不消费旧 summary，且不把非 success 终态呈现为成功。
15. `strategy.career_plan`、`list_type="plan"` 旁路和 legacy Adapter 不存在。
16. 启动校验阻止 Definition、Prompt、Skill、operation、handler、ledger 或 Adapter 目录不完整的应用启动。
17. 定向测试、全部非 LLM 后端测试、完整 Pyright 和前端构建通过；失败、跳过和未执行项如实记录。
18. 新系统从干净 DATA_DIR 验收，不读取或迁移旧 Session/Task/Artifact/Output 数据。
19. 没有提前实现 Failure 分类、重试、Judge、最终 Run 聚合、授权 TTL 或 Trace exactly-once。

## 17. 全局失败机制前置交付

本规格完成后直接向全局失败机制提供：

- 泛型 OutcomeBinding、RequiredOutcome、ExecutionPlanNodeSpec；
- 原子 `PlanDispatch`、闭合 PlanNodeResult/PlanAdvanceResult 和 ExecutionPlanExecutor；
- `SessionExecutionState`、活动 Plan 快照与 RequestService；
- 唯一 `OperationRegistry`、ResolvedOperation、DurableResultLedgerRegistry；
- `OperationAuthorizationWait`、AuthorizationSuspendedExecution、confirmation、claim、CommittedOperationReceipt 与闭合恢复状态机；
- 稳定 output_id、OutputIndexStore 和删除 receipt；
- 临时 WorkerExecutionResult 与 PlanResultPresenter 的明确替换点。

全局失败机制可以引入 OperationResult、OperationPolicy、OperationExecutor、WorkerRun/TurnRun/JobRun、Failure、Judge 和 Turn Result Renderer；不得复制本规格或前置规格的 Registry、Contract、Outcome、Plan、授权请求 Store 或 Worker Run 编号生成逻辑。
