# 全局失败机制设计规格

| 属性 | 内容 |
|------|------|
| 状态 | **已确认，实施计划已编写** |
| 版本 | **1.3.0** |
| 日期 | 2026-07-23 |
| 直接前置规格 | [ExecutionPlan 与受控执行生命周期](./2026-07-23-execution-plan-controlled-lifecycle-design.md) |
| 传递前置规格 | [强类型 WorkerInvocation 与结果契约](./2026-07-23-typed-worker-invocation-contract-design.md) |
| 适用范围 | Operation、Worker Run、Turn Run、Job Run、Gate、Trace、SSE、用户错误呈现与本地审计 |
| 实施计划 | [全局失败机制 Implementation Plan](../plans/2026-07-23-global-failure-mechanism.md) |
| 领域语言 | [CONTEXT.md](../../../CONTEXT.md) |

---

## 1. 背景与现场证据

当前系统的错误处理分散在 Tool handler、Harness、Worker ReAct、Coordinator 特殊分支、市场调研 Runner 和 API 层：

- Tool 可能返回带 `code` 的对象，也可能抛异常；
- Worker ReAct 可能返回 `status="failed"`，但 Coordinator 没有统一传播规则；
- Trace 记录了 `agent.run.start`，真实 Worker 的所有终态没有统一 `agent.run.end`；
- Worker 输出通过 Pydantic 类型校验后即可被标为 completed，无法证明业务目标完成；
- Coordinator 使用最后一个 Worker 的 `user_visible_summary` 合成本轮回复；
- retry 次数分散在不同模块，缺少统一的 operation 策略事实来源；
- 长时间市场调研已经拥有独立状态机，但没有与通用 Worker/Turn 失败语义对齐。

2026-07-22 demo Bug 的真实链路是：

1. resume Worker Run 没有形成成功结果；
2. Coordinator 仍继续 asset；
3. asset 根据自己的职责拒绝简历优化；
4. 最终回复被 asset 摘要覆盖；
5. 用户无法看到真正失败点；
6. Trace 无法直接回答 resume 最终为何失败。

这不是单个 if 缺失，而是系统没有统一回答以下问题：

- 某个 operation 是否失败；
- 失败属于什么类别；
- 是否能安全重试；
- operation 失败是否导致 Worker Run 失败；
- operation 都未报错时，Worker 是否真的完成目标；
- 上游未成功时，下游是否允许执行；
- Turn 最终是成功、部分成功还是失败；
- 用户应该看到什么；
- 如何完整回放当时的输入、策略和结果。

## 2. 设计原则

1. **业务正确性和系统稳定性优先**：不以统一限制重试次数换取更短等待。
2. **组件报告事实，Harness 作决策**：LLM、Tool、Store、Browser 只报告结果；Harness 统一分类和选择策略。
3. **operation 第一层，Run 第二层**：关键 operation 失败可以直接导致 Worker Run 失败；Worker Run 失败也可能来自没有已知 operation 错误的整体未完成。
4. **模型不能覆盖硬失败**：Judge 或 Worker 摘要不能把关键 operation 失败、必需结果缺失改判为成功。
5. **失败关闭**：未分类、结果未知、策略缺失、审计持久化失败时默认不继续依赖链。
6. **保留已确认成果**：默认不做全链路回滚，只执行已注册且安全的补偿。
7. **用户消息与内部诊断分离**：内部保存稳定错误码，外部只展示可理解的业务说明。
8. **本地完整可回放**：不做脱敏，但避免把大段原文重复嵌入每条 Trace 和 Failure。
9. **不恢复旧执行**：应用重启后未完成 Run 只标记 interrupted，不自动续跑。
10. **运行正确性与离线质量分离**：运行时 Judge 判断目标是否完成；Eval 判断结果质量。
11. **确定性契约单一事实来源**：复用《强类型 WorkerInvocation 与结果契约》提供的闭合 `WorkerInvocation`/`VerifiedOutcome` 联合、`DeterministicSuccessContractRegistry` 与泛型 `ContractEvaluation[TOutcome]`；本规格只编排 operation 事实、运行完整性、确定性验收结果和可选 Judge，不复制业务契约或擦除其静态类型。
12. **认领身份端到端不变**：RunEngine 完整消费前置 Plan claim 产生的 `PlanDispatch`，从 WorkerRun 到 PlanNodeResult 始终使用同一个 plan_id、node_id 和 worker_run_id。
13. **授权所有权分层但不重复**：复用《强类型 WorkerInvocation 与结果契约》的闭合 continuation，以及《ExecutionPlan 与受控执行生命周期》的 `OperationRegistry`、`OperationAuthorizationWait`、claim 和 committed receipt，组成单次 operation 恢复的唯一状态机；本规格的 Session Grant 只表达可跨 Worker Run 复用的授权约束，不能替代或复制单次操作状态。

## 3. 目标

1. 为所有有业务意义的 operation 提供统一执行接口。
2. 使用 `Success / BusinessOutcome / Failure` 区分成功、正常业务分支和失败。
3. 统一五类 Failure，并保留未分类失败兜底。
4. 使用强类型 operation 策略注册表决定关键性、重试、幂等、结果核对、补偿和失败传播。
5. 根据“operation 类型 + 错误码 + 幂等能力 + Worker/Run Kind 目的”选择唯一策略。
6. 不设置全局统一重试次数；每条策略明确尝试次数或截止条件。
7. 为有副作用 operation 引入 `outcome_unknown` 与结果核对。
8. 对 Worker Run 执行“运行完整性 → 复用前置确定性 Success Contract → 受约束语义 Judge”三段式判定。
9. 明确 Worker Run、Turn Run、Job Run 状态和聚合规则。
10. 使用 ExecutionPlan 依赖传播阻止错误下游执行。
11. 将业务执行状态与 SSE 交付状态分离。
12. 持久化 Run Snapshot、Trace 和 Failure，并提供非递归 Emergency Sink。
13. 使用确定性用户错误消息目录，LLM 只能可选润色。
14. 保留市场调研现有 Job 级等待、方向重试和安全取消，不新增通用 Run 主动取消。
15. 保证 claim、WorkerRun、WorkerRunResult 与 PlanNodeResult 的身份连续，拒绝重复或错配执行。

## 4. 非目标

本规格不包含：

- 历史状态迁移或旧 `completed/failed` 记录兼容；
- 应用重启后恢复 Worker Run、Turn Run、ExecutionPlan、operation 或 Job Run；
- 用户主动取消正在执行的通用 Worker Run 或 operation；
- Turn 内 Worker 并发执行；
- 固定的全局“最多重试一次”规则；
- 授权请求固定 TTL；
- 跨 Session 授权；
- 在用户消息中展示内部错误码、Worker、Tool、堆栈或模型供应商；
- 云端日志上传、多用户隔离、RBAC 或远程监控平台；
- 对本地 Run Snapshot 做脱敏；
- 将每个普通内部函数都包装为 operation；
- 让 LLM 自由选择失败策略、依赖或补偿函数；
- 重新定义或复制《强类型 WorkerInvocation 与结果契约》已经实现的闭合 Invocation/Outcome 类型、确定性 Success Contract Registry、契约 handler 或 Outcome 提取规则；
- 重新定义《ExecutionPlan 与受控执行生命周期》已经实现的 Operation Definition、operation 授权元数据、活动计划快照、confirmation/claim/receipt 状态机，或改写其消费的前置 continuation；
- 使用运行时 Judge 评价文案是否足够优秀；
- 删除或重做市场调研已有的显式取消能力。

## 5. Operation 边界

### 5.1 哪些动作是 Operation

满足任意一项的动作必须作为 operation：

- 可能失败并改变用户结果；
- 产生、读取或发布外部状态；
- 决定流程是否继续；
- 需要重试、降级、补偿或结果核对；
- 需要独立 Trace、耗时和失败策略。

第一版全部覆盖：

- Coordinator、Worker、Judge、Gate 分类与最终润色的 LLM 调用；
- 所有 Tool 调用；
- Session、Task、Artifact、Profile、Run、Market 等 Store 读写；
- 浏览器、招聘网站、Google Trends 等外部访问；
- 文件读取、HTML 写入、截图和索引更新；
- Gate 确认、阶段推进、任务认领和状态转换；
- Worker Run 的 Success Contract 编排与可选 Judge；
- SSE 建立、事件发送与最终文本交付；
- Job 创建、启动、状态更新、正式结果发布和既有市场重试。

以下不是独立 operation：

- 字符串格式化；
- 纯内存字段映射；
- 不会单独影响业务决策的辅助函数；
- 已由外层 operation 完整覆盖、且没有独立副作用或策略的实现细节。

### 5.2 OperationRequest

本规格不重新创建 operation 目录。前置 `OperationRegistry.resolve(operation_type)` 必须一次返回唯一 `ResolvedOperation(definition, handler)`；这里的 `operation_type`（操作类型）与前置模型的 `operation_name`（操作名称）是同一个稳定标识，只因运行事实与定义模型的字段语境不同而使用不同字段名。Adapter、Policy、LLM 或调用方不得新增未注册类型、替换 handler，也不得覆盖 Definition 的授权与 durable ledger 元数据。

```python
class OperationRequest(BaseModel):
    operation_id: str
    operation_type: str
    actor: str
    purpose: str
    session_id: str | None
    turn_run_id: str | None
    worker_run_id: str | None
    job_run_id: str | None
    invocation_id: str | None
    input_snapshot_ref: str
```

| 字段 | 含义 | 作用 |
|------|------|------|
| `operation_id` | operation 唯一编号 | 关联尝试、授权、Trace 和结果 |
| `operation_type` | 操作类型 | 匹配 Adapter 与失败策略 |
| `actor` | 执行角色 | 校验 Tool/Store/LLM 使用者 |
| `purpose` | 本次业务用途 | 区分同一 operation 在不同 Run Kind 下的关键性 |
| `session_id` | Session 编号 | 绑定数据与 Session 授权 |
| `turn_run_id` | Turn Run 编号 | 关联本轮执行 |
| `worker_run_id` | Worker Run 编号 | 关联 Worker 结果判定 |
| `job_run_id` | Job Run 编号 | 关联后台长任务 |
| `invocation_id` | Worker Invocation 编号 | 取得 Run Kind 与能力快照 |
| `input_snapshot_ref` | 输入快照引用 | 保证同 Run 重试使用相同输入 |

## 6. OperationResult

### 6.1 三类顶层结果

```python
OperationResult = Success[T] | BusinessOutcome[B] | FailureResult
```

#### Success

operation 按契约完成，并得到可验证结果。

```python
class Success(BaseModel, Generic[T]):
    value: T
    outcome: Literal["succeeded"] = "succeeded"
```

- `value`（成功值）：operation 产生的结构化结果。
- `outcome`（执行结论）：明确表示成功，不需要结果核对。

#### BusinessOutcome

operation 正常完成，但形成非成功推进的业务结论，例如：

- `no_results`：合法查询没有结果；
- `awaiting_authorization`：等待当前 operation 授权；
- `rejected`：用户拒绝 Workflow Transition 或授权；
- `needs_additional_input`：需要新的业务输入；
- `accepted_async`：后台 Job 已成功创建。

BusinessOutcome 不进入失败策略、不计入错误率、不触发断路器。

#### FailureResult

operation 未按契约完成，携带失败事实，不自行决定处理策略。

```python
class FailureResult(BaseModel):
    failure_id: str
    source: str
    actor: str
    operation_type: str
    purpose: str
    category: FailureCategory
    code: str
    outcome: Literal["failed_before_effect", "outcome_unknown"]
    safe_detail: dict[str, Any]
    cause_ref: str | None = None
```

| 字段 | 含义 | 作用 |
|------|------|------|
| `failure_id` | 失败编号 | 关联策略、传播和用户消息 |
| `source` | 失败来源 | 区分 LLM、Tool、Store、Browser、SSE 等 |
| `actor` | 执行角色 | 关联 Worker 或 Harness |
| `operation_type` | 操作类型 | 匹配策略 |
| `purpose` | 业务用途 | 选择场景特化策略 |
| `category` | 失败类别 | 进行大类统计与兜底 |
| `code` | 稳定机器码 | 精确匹配策略与测试 |
| `outcome` | 副作用结论 | 决定能否直接重试 |
| `safe_detail` | 结构化诊断 | 保存字段、规则、计数等可检索事实 |
| `cause_ref` | 原始原因引用 | 指向完整堆栈、Provider 响应或 Tool 结果 |

`FailureResult` 不包含最终 `retryable` 决策。是否重试由 operation 策略注册表结合幂等能力和当前上下文决定。

## 7. Failure 分类

第一版固定五类：

| Category | 含义 | 示例 |
|----------|------|------|
| `input_required` | operation 已开始后才发现声明的必需输入缺失 | 不可变输入快照缺少已声明字段、适配器漏传必需参数 |
| `contract_violation` | 输入、输出或持久化数据不符合契约 | 非法 JSON、空必需产物、invalid_html |
| `tool_failure` | Tool、Store、Browser、文件或外部依赖执行失败 | I/O 失败、浏览器异常、Store 写失败 |
| `model_failure` | 模型调用或模型结构化响应失败 | 超时、限流、鉴权失败、无有效 JSON |
| `policy_blocked` | 权限、阶段、资源范围或安全策略阻止执行 | Tool 越权、阶段不允许、路径越界 |

另有兜底：

```text
unclassified_failure / unexpected_exception
```

未分类失败：

- 不自动重试；
- 不继续依赖链；
- 保存异常类型与完整堆栈引用；
- 进入 Worker Run 第二层判定；
- 默认失败关闭。

预检阶段发现用户尚未提供业务信息时，返回 `needs_additional_input`；发现当前 operation 尚未授权时，返回 `awaiting_authorization`。这两者都是正常 `BusinessOutcome`，不归类为 `input_required`，也不进入重试、错误率或断路器统计。

## 8. Error Adapter

### 8.1 职责

各基础设施模块在自己的执行接缝维护 Error Adapter：

```text
LiteLLM Adapter
Tool Adapter
Store Adapter
Browser Adapter
File Adapter
SSE Adapter
Job Adapter
Gate Adapter
```

Adapter 将领域错误、第三方异常或错误返回值转换为稳定 FailureResult。Harness 不维护一个知道所有第三方细节的巨大异常函数。

### 8.2 转换顺序

1. 已经是 `FailureResult`：原样保留。
2. 已登记领域错误：使用领域 Adapter。
3. 已登记第三方异常：转换为稳定 category/code。
4. 未识别异常：转换为 `unclassified_failure / unexpected_exception`。

示例：

```text
LiteLLM RateLimitError
→ model_failure / rate_limited

write_resume_html invalid_html
→ contract_violation / invalid_html

Store PermissionError
→ tool_failure / store_permission_denied

Tool path_out_of_scope
→ policy_blocked / path_not_allowed
```

## 9. OperationPolicyRegistry

### 9.1 唯一事实来源

operation 策略使用强类型代码注册，不使用外部 JSON 定义安全行为。

```python
class OperationPolicy(BaseModel):
    policy_id: str
    matcher: OperationPolicyMatcher
    criticality: Literal["required", "optional"]
    idempotency: IdempotencyPolicy
    retry: RetryPolicy
    probe_handler: str | None
    compensation_handler: str | None
    preserve_on_downstream_failure: bool
    exhausted_decision: FailureDecision
    circuit_breaker: CircuitBreakerPolicy | None
```

| 字段 | 含义 | 作用 |
|------|------|------|
| `policy_id` | 策略编号 | Trace 记录与版本审计 |
| `matcher` | 匹配条件 | 选择 operation、错误码和用途 |
| `criticality` | operation 关键性 | 决定失败是否可能终止 Worker Run |
| `idempotency` | 幂等能力 | 决定能否安全重复执行 |
| `retry` | 重试策略 | 决定尝试次数、间隔和截止条件 |
| `probe_handler` | 结果核对处理器 | outcome_unknown 时查询真实结果 |
| `compensation_handler` | 补偿处理器 | 只执行显式登记的安全补偿 |
| `preserve_on_downstream_failure` | 是否保留成功成果 | 防止后续失败误删有效产物 |
| `exhausted_decision` | 策略耗尽决策 | fail_worker、degrade、wait 等 |
| `circuit_breaker` | 断路器策略 | 保护持续故障的外部依赖 |

### 9.2 关键性

关键性不是 Tool 的永久属性，而是：

```text
operation type
+ Worker run_kind
+ purpose
```

例如：

- resume.generate_optimized_resume 的 `write_resume_html` 是 required；
- resume.collect_optimization_levels 不应调用该 operation；
- 记录最近优化档位的 `profile_patch` 可以 optional；
- 保存用户已确认关键事实的 `profile_patch` 是 required。

合法组合必须在 WorkerRunDefinition 与 OperationPolicyRegistry 中预先登记，LLM 不能把 required operation 改成 optional。

### 9.3 固定优先级

多个策略匹配同一 Failure 时，按以下固定优先级选择唯一最具体策略：

```text
worker + operation + purpose + error_code + outcome
worker + operation + error_code + outcome
operation + purpose + error_code + outcome
operation + error_code + outcome
operation + error_category
error_code
error_category
global fallback
```

规则：

- 越靠上越优先；
- 同一层只能匹配一条；
- 同层冲突在启动时拒绝应用启动；
- 没有匹配时使用全局失败关闭策略；
- LLM 不能选择 policy_id。

### 9.4 RetryPolicy

```python
class RetryPolicy(BaseModel):
    max_attempts: int | None
    deadline_seconds: float | None
    backoff: Literal["none", "fixed", "exponential_jitter"]
    repair_context: bool
```

| 字段 | 含义 | 作用 |
|------|------|------|
| `max_attempts` | 最大总尝试次数 | 由具体业务稳定性需求决定 |
| `deadline_seconds` | 策略截止时间 | 防止长时间无界执行 |
| `backoff` | 等待策略 | 适配即时修正、限流或外部恢复 |
| `repair_context` | 是否注入修正反馈 | 适用于 JSON/HTML 等可修复契约错误 |

系统没有统一“最多一次”规则。每条策略必须明确 `max_attempts` 或 `deadline_seconds`，禁止无限重试。

### 9.5 安全上限

正常重试次数由业务策略决定；独立安全上限只防止配置错误和无限循环：

- Worker Run 有最大 ReAct 迭代数与绝对截止时间；
- Turn Run 有绝对截止时间；
- Job Run 有自己的预算或截止条件；
- 达到安全上限形成内部错误码 `retry_safety_limit_exceeded`；
- 该内部错误码只进入 Trace/Failure，不直接展示给用户；
- 用户只看到错误目录渲染的可理解说明。

## 10. 幂等、结果核对与补偿

### 10.1 outcome_unknown

有副作用 operation 必须区分：

```text
succeeded
failed_before_effect
outcome_unknown
```

- `failed_before_effect`：明确未产生副作用，可以按策略重试。
- `succeeded`：记录并禁止重复执行。
- `outcome_unknown`：不能直接重试，先执行结果核对。

### 10.2 幂等要求

所有有副作用且允许自动重试的 operation 必须具备：

- 稳定幂等键；或
- 结果核对能力。

`write_resume_html` 示例：

- 使用稳定 `operation_id`；
- 临时文件加原子替换；
- 重试前按 operation_id 或目标内容哈希查询交付物；
- 已生成则返回原 delivery，不重复创建。

`register_outputs_index` 示例：

- 使用 delivery id 或内容哈希；
- 超时后查询索引；
- 已存在则把 outcome_unknown 收敛为 success。

### 10.3 同 Run 输入快照

同一次同步 Worker Run 内自动重试：

- 固定使用 operation 首次调用的不可变输入快照；
- 不重新读取整个 Session 或 Profile；
- 不为低概率本地并发引入全局版本锁。

进入 Additional Input Gate、创建新 Turn 或应用重启后，不恢复旧 operation。

### 10.4 补偿

默认采用“保留已确认成果 + 显式补偿”：

- 后续失败不自动回滚上游成功成果；
- 只有已登记、确定、安全的 compensation handler 才能执行；
- LLM 不得选择或生成补偿动作；
- 没有补偿函数时明确保留结果。

例如：

```text
HTML 已生成
+ 资产登记失败
→ 保留 HTML
→ 标记 generated_unregistered
→ 不重新生成 HTML
```

## 11. OperationExecutor

### 11.1 唯一入口

```python
class OperationExecutor:
    def execute(
        self,
        request: OperationRequest,
    ) -> OperationExecutionResult:
        ...
```

`execute`（执行 operation）统一负责：

1. 创建或验证 operation_id；
2. 保存输入快照；
3. 通过 `OperationRegistry.resolve(request.operation_type)` 取得唯一 Definition/handler 绑定并调用该 handler；
4. 通过 Adapter 得到 OperationResult；
5. 为 Failure 匹配唯一策略；
6. 执行重试、退避、结果核对或补偿；
7. 写 Operation Attempt、Trace 和 Failure；
8. 返回唯一执行结果与 Failure Decision。

### 11.2 防止绕过

- ToolRegistry 不向 Worker 暴露原始 handler；
- OperationExecutor 不接受调用方传入 handler，只接受 `OperationRequest` 并解析前置 Registry 的唯一绑定；
- LLM Provider、Store、Browser、File、SSE、Gate 和 Job 接缝通过 OperationExecutor；
- 原始 handler 只在 `ResolvedOperation` 与 operation 模块实现内部可见；
- 未注册 operation 返回 `operation_policy_missing` 并失败关闭；
- 注册完整性测试要求所有已登记 Tool、Provider、Store、外部访问和状态转换有 operation 定义与 Adapter。

### 11.3 嵌套 operation

外层 operation 可以调用子 operation，但：

- 实际副作用只由最内层 operation 负责重试；
- 外层不得再次执行整个子调用链；
- 每次 attempt 关联 parent_operation_id；
- 结果核对与补偿只作用于拥有副作用的 operation。

## 12. FailureDecision

Harness 可以输出：

```text
retry
degrade
await_authorization
needs_additional_input
fail_worker
abort_turn
continue
```

| 决策 | 含义 |
|------|------|
| `retry` | 按当前策略和固定输入再次尝试 |
| `degrade` | operation 非关键，记录降级后继续 |
| `await_authorization` | 当前冻结 operation 等待用户授权 |
| `needs_additional_input` | 当前 Run 结束，用户补充后新建 Run |
| `fail_worker` | 当前 Worker Run 不能完成目标 |
| `abort_turn` | 状态一致性无法证明，终止当前 Turn |
| `continue` | 失败不影响当前目标；仅允许明确 optional 场景 |

每个决策必须记录 policy_id、attempt、依据与传播结果。

## 13. Worker Run 分层判定

### 13.1 第一层：operation 事实

任何 required operation 在策略耗尽后失败，可以直接阻止 Worker Run 成功。

optional operation 失败是否降级，由匹配策略决定。operation 没有报错不等于 Worker Run 成功。

### 13.2 第二层：整体结果

用于捕获：

- LLM 未调用本应调用的 operation；
- ReAct 提前结束；
- JSON 合法但业务产物为空；
- operation 都成功但组合结果不符合目标；
- Worker 输出自相矛盾；
- 达到最大迭代数；
- Worker 只输出角色说明或泛化建议；
- Harness 尚未认识的动态步骤失败。

### 13.3 三段式 Success Contract

#### 运行完整性

检查：

- ReAct 是否正常收敛；
- 是否超时或达到最大迭代；
- 是否存在未处理 Failure；
- 是否存在 outcome_unknown；
- 是否存在未闭合 Tool 调用；
- required Skill 是否成功加载。

#### 确定性成功契约

调用《强类型 WorkerInvocation 与结果契约》提供的 `DeterministicSuccessContractRegistry.evaluate()`，消费其 `ContractEvaluation[VerifiedOutcome]`。其中 `VerifiedOutcome`（已验证结果）是该规格定义的闭合联合，`satisfied`（是否满足）是用于静态缩窄成功/不满足分支的 Literal discriminator。该 Registry 是以下规则的唯一实现位置：

- 必需输出字段；
- 命名 Outcome；
- 产物数量；
- 文件与索引真实性；
- 状态写入；
- Gate 类型；
- 上游输入一致性。

本规格的 `RunEngine` 不再注册第二份契约 handler，也不从 Worker 原始 `structured_output` 自行提取 Outcome。它只接收《强类型 WorkerInvocation 与结果契约》的闭合 `WorkerInvocation` 联合，并为同一个 Registry 注入由 OperationResult/WorkerExecutionEvidence 支持的 Artifact/Index verifier Adapter，使外部事实读取仍经过 OperationExecutor。只有 `ContractEvaluation.satisfied=True` 时，具体 `verified_outcomes` 才能参与 Worker Run success 和 ExecutionPlan 的强类型 binder；契约不满足时，由本规格结合 operation 事实与运行完整性形成最终状态和 Failure。RunEngine、WorkerRunResult 和 Store 不得把这些对象降级为 `Mapping[str, Any]` 或字符串 Outcome 字典。

例如 `resume.generate_optimized_resume`：

```text
verified_html_deliveries.minimum = 1
每份路径存在
HTML 完整文档校验通过
档位与 Invocation 输入一致
```

#### 受约束语义 Judge

只在动作定义声明 `when_needed` 或 `required` 时使用：

```json
{
  "verdict": "success | incomplete | failed | uncertain",
  "reason_codes": ["goal_not_addressed"],
  "evidence_refs": ["worker_output.user_visible_summary"],
  "confidence": 0.86
}
```

字段含义：

- `verdict`（结论）：目标完成、未完成、失败或无法判断。
- `reason_codes`（原因码）：来自固定契约目录。
- `evidence_refs`（证据引用）：指向 Worker 输出或 Artifact。
- `confidence`（置信度）：决定是否接受或保守停止。

Judge 规则：

- 不得把 required operation 失败改为 success；
- 不得把确定性契约未满足改为 success；
- 确定性规则足够时完全跳过 Judge；
- Judge 超时、非法输出或重试耗尽时，Worker Run 进入 outcome_unknown；
- `uncertain` 默认暂停下游；
- Judge 只判断目标完成度，不承担离线内容质量 Eval。

### 13.4 Plan claim 与 Worker Run 身份连续性

RunEngine 必须直接消费《ExecutionPlan 与受控执行生命周期》的 `PlanDispatch`，不能只接收其中的 Invocation：

```python
class RunEngine:
    def start_worker(
        self,
        dispatch: PlanDispatch,
        *,
        turn_run_id: str,
    ) -> WorkerRun: ...

    def finish_worker(
        self,
        worker_run: WorkerRun,
        execution: WorkerExecutionEvidence,
    ) -> WorkerRunResult: ...

    def to_plan_node_result(
        self,
        result: WorkerRunResult,
    ) -> PlanNodeResult: ...
```

接口含义：

- `start_worker`（启动 Worker Run）：使用 `PlanDispatch` 中已经由 `claim_next()` 原子认领的计划编号、节点编号、Invocation 和 Worker Run 编号创建 running 生命周期。
- `turn_run_id`（Turn Run 编号）：标识本轮用户请求的运行生命周期，用于验证 dispatch 所属 Plan 没有跨 Turn 使用。
- `finish_worker`（结束 Worker Run）：保持同一计划、节点和 Worker Run 身份，结合运行证据生成最终 `WorkerRunResult`。
- `to_plan_node_result`（转换计划节点结果）：把终态 WorkerRunResult 投影为《ExecutionPlan 与受控执行生命周期》定义的最小 `PlanNodeResult`，供 `ExecutionPlanExecutor.advance()` 验证身份并推进 Plan。

身份规则：

1. Coordinator 必须先采用 `PlanClaimed.plan`，再把同一返回值中的 `PlanDispatch` 交给 `start_worker()`。
2. `start_worker()` 必须原样使用 `dispatch.worker_run_id`，不得生成、替换或归一化另一个编号。
3. `dispatch.plan_id`、`dispatch.node_id`、`dispatch.invocation.node_id`、`dispatch.worker_run_id` 和 `turn_run_id` 必须与当前已采用 Plan 完全一致；不一致时失败关闭，不能创建 Worker Run。
4. Store 中已经存在相同 `worker_run_id` 时，重复启动必须被拒绝，不能产生第二次 Worker 执行。
5. `WorkerRunResult` 必须保留同一个 `plan_id`、`node_id` 和 `worker_run_id`；`to_plan_node_result()` 只能复制这些身份、闭合终态和原类型 `tuple[VerifiedOutcome, ...]`，不得从摘要或动态字典重建 Outcome。
6. `running`、`awaiting_authorization` 和 operation 层尚未验收的 `accepted_async` 不能直接转换为 `PlanNodeResult`。`market.start_research` 是唯一的异步接收特例：确定性 Contract 验证 Job 已创建并持久化，产生 `JobAcceptedOutcome` 后，当前 Worker Run 转为终态 `success`，其当前 Turn 的 Plan 节点立即推进；独立 Job Run 随后使用自己的 Job ExecutionPlan 等待 Job 终态并推进自己的节点。其他异步接收状态不得绕过契约。
7. Coordinator 使用 `result.node_id` 作为结果 mapping key；`advance()` 再验证 mapping key、节点状态和 Worker Run 编号，因此过期或错配结果不能结束另一次认领。

## 14. Worker Run 状态

```text
running
awaiting_authorization
success
partial_success
needs_additional_input
failed
outcome_unknown
cancelled
superseded
interrupted
```

| 状态 | 含义 |
|------|------|
| `running` | 正在执行 operation 或 ReAct |
| `awaiting_authorization` | 当前冻结 operation 等待用户授权 |
| `success` | Success Contract 完全满足 |
| `partial_success` | 保留了有效成果，但整体目标未完成 |
| `needs_additional_input` | 需要改变后续输入，当前 Run 结束 |
| `failed` | 已明确失败且策略处理完毕 |
| `outcome_unknown` | 关键结果无法确认 |
| `cancelled` | 用户拒绝当前 operation 授权 |
| `superseded` | 用户修改参数或目标，旧 Run 被新 Run 取代 |
| `interrupted` | 应用退出或重启，旧 Run 不恢复 |

下游调度：

- 默认只有 success 可以满足 ExecutionPlan 依赖；
- partial_success 只有在下游显式声明接受具体部分 Outcome 时可使用；
- 其余状态均不执行依赖节点。

Workflow Transition Gate 的拒绝不回写已成功的上游 Worker Run。它是 Gate 的正常 BusinessOutcome。

## 15. Turn Run

### 15.1 状态

```text
success
partial_success
needs_additional_input
awaiting_authorization
failed
outcome_unknown
cancelled
superseded
interrupted
```

### 15.2 依赖感知聚合

- 当前目标节点全部 success：Turn success；
- 核心目标完成、非关键后续失败：Turn partial_success；
- 核心目标未完成：Turn failed；
- 任一关键节点 outcome_unknown：Turn outcome_unknown；
- operation 等待授权：Turn awaiting_authorization；
- Worker 需要新输入：Turn needs_additional_input；
- 下游 blocked_by_upstream 不单独制造 failed Worker Run；
- Turn 结果由 Plan 和 Worker Run 聚合，不由最后一个 Worker 决定。

### 15.3 TurnResultRenderer

最终用户草稿由独立 `TurnResultRenderer`（Turn 结果渲染器）生成：

- 读取 Turn 聚合状态；
- 读取已保留成果；
- 读取用户消息目录；
- 不直接采用最后一个 Worker 的 user_visible_summary；
- 不暴露 Worker、Tool、内部错误码或堆栈；
- 可以引用业务动作名称，例如“简历生成”或“产物登记”。

## 16. Job Run

### 16.1 与 Worker Run 的区别

Worker Run 可以成功创建后台 Job：

```text
market.start_research Worker Run
→ Job 创建并持久化
→ 确定性 Contract 产生 JobAcceptedOutcome
→ Worker Run success
→ 当前 Turn 的 market.start_research Plan 节点立即 finished
```

Job Run 随后独立执行：

```text
启动浏览器
→ 采集 Trends
→ 采集 BOSS
→ 语义提取
→ 统计
→ 综合
→ 发布正式 Artifact
```

后台失败不得把已经结束的 Worker Run 改回 failed。

这里存在两个不同的执行计划：当前 Turn 的 `ExecutionPlan` 只负责“启动已确认市场研究”这一节点，验收 Job 已持久化后立即结束；后台 Job 的 `Job ExecutionPlan` 负责浏览器采集、语义提取、统计与发布，必须等待自身终态才能推进自身节点。二者通过 `job_id` 关联，但不共享节点生命周期。

### 16.2 共享与独立

Job Run 共享：

- OperationResult；
- Failure 分类；
- OperationPolicyRegistry；
- Error Adapter；
- 重试、幂等、结果核对、补偿和断路器；
- Snapshot、Trace 和 Failure 格式；
- 确定性 Success Contract 与可选 Judge。

Job Run 独立拥有：

- Job id；
- Job ExecutionPlan；
- 生命周期状态；
- 有效预算；
- 正式 Artifact 发布；
- 用户轮询或状态卡。

### 16.3 市场调研兼容

现有市场调研已经支持：

- queued/running/waiting_user；
- completed/partial_completed/failed；
- 方向重试；
- 登录或验证后继续；
- 用户安全取消；
- 进程重启后将活动任务标记为中断。

本规格：

- 保留现有市场 Job 的 continue/cancel；
- 不把该能力推广为通用 Worker/Turn 主动取消；
- 不自动恢复重启前的市场 Job；
- 后续实现时把现有状态 Adapter 到通用 Job Run 语义，不要求立即删除市场领域状态。

## 17. Gate 与 Session 授权

### 17.1 三类 Gate

#### Operation Authorization Gate

适用于已确定 operation、参数已冻结、只缺用户授权：

- 保持同一个 Worker Run 与 ExecutionPlan；
- 不设置固定 authorization_request_ttl；
- 完整复用《强类型 WorkerInvocation 与结果契约》的 `SuspendedWorkerRun + OperationContinuation`，以及《ExecutionPlan 与受控执行生命周期》的 `AuthorizationSuspendedExecution + OperationAuthorizationWait`；`AuthorizationSuspendedExecution` 是 `SessionExecutionState.current_execution` 中等待 operation authorization 的唯一分支，ReAct 与确定性执行都按其 discriminator 恢复原执行点；真正异步、跨请求且不等待授权的 Plan 使用独立 `AsynchronousExecution`，后台 Job 仍由自身生命周期管理；
- confirmation、恢复权 claim、底层 durable ledger 和 `CommittedOperationReceipt` 继续由前置 `SessionStore` 状态机唯一管理，本规格不创建第二份 authorization request Store；
- 拒绝、参数变化、运行实例变化、临时资源失效或业务主动结束会终止等待；
- 参数变化时旧 Run superseded，新建 Run。

#### Workflow Transition Gate

适用于是否进入下一业务阶段：

- 当前 Worker Run 与 Plan 正常结束；
- 用户确认后创建新 Turn Run 和新 Plan；
- `optimize_confirm` 属于此类。

#### Additional Input Gate

适用于用户提供会改变后续输入的信息：

- 当前 Worker Run needs_additional_input；
- 用户补充后创建新 Worker Run；
- 优化档位选择属于此类。

### 17.2 Session Grant

`SessionGrant`（会话授权凭据）只表达用户已经允许的可复用约束，用于新 Worker Run 在执行具体 operation 前减少重复询问；它不是当前 operation 的 confirmation、执行权 claim、continuation 或结果 receipt。

确认并持久化后的 Session Grant：

- 可以跨 Worker Run；
- 不能跨 Session；
- 绑定 `session_id + operation_type + constraints + policy_version`；
- 可约束目录、文件类型、delivery id、是否允许覆盖等范围；
- 超出约束时重新申请；
- 用户撤销、Session 清理或策略风险等级变化时失效。
- 命中 Grant 只表示当前 operation 可以跳过新的用户询问；Harness 仍必须根据前置 `OperationRegistry` 校验 operation、参数和资源范围，并为有副作用的执行使用原 durable ledger 和结果协议。

示例：

```json
{
  "session_id": "sess_xxx",
  "operation_type": "write_resume_html",
  "constraints": {
    "root": "output/demo",
    "allow_overwrite": true,
    "filename_pattern": "*.html"
  },
  "policy_version": "write_resume_html.auth.v1"
}
```

字段含义：

- `session_id`（会话编号）：限制授权不能跨 Session。
- `operation_type`（操作类型）：限制授权只覆盖指定操作。
- `constraints`（约束）：限制资源和参数范围。
- `policy_version`（策略版本）：风险规则变化时使旧授权失效。

前置 `OperationAuthorizationWait` 会持久化，但只允许同一 `runtime_instance_id` 恢复；应用重启后由全局失败机制把旧活动 Run/Plan 标记为 interrupted，不接管旧 claim。已经确认并持久化的 Session Grant 可以供重启后的新 Run 按约束重新校验，但不能用于恢复旧 continuation 或推断旧 operation 已提交。

## 18. 断路器

断路器按：

```text
environment
+ external dependency
+ operation type
```

隔离。

状态：

```text
closed → open → half_open → closed
```

触发候选：

- Provider 持续超时或限流；
- Store 持续不可写；
- Browser 外部依赖持续不可用；
- 文件系统持续 I/O 错误。

不触发：

- invalid_html；
- input_required；
- policy_blocked；
- no_results；
- 用户拒绝；
- 正常等待用户验证。

断路器不能因为一个 operation 故障熔断整个 Agent Runtime，也不能跨 demo 环境传播。

## 19. 用户错误消息目录

### 19.1 确定性目录

```python
class UserErrorMessageDefinition(BaseModel):
    message_id: str
    title: str
    template: str
    allowed_actions: tuple[str, ...]
```

| 字段 | 含义 | 作用 |
|------|------|------|
| `message_id` | 消息定义编号 | 测试与 Trace 引用 |
| `title` | 用户可理解标题 | 表达业务结果 |
| `template` | 确定性模板 | 保证同类错误稳定表达 |
| `allowed_actions` | 可执行下一步 | 禁止承诺系统不支持的恢复动作 |

例如内部：

```text
retry_safety_limit_exceeded
```

外部：

```text
本次简历生成连续多次未能成功。为避免重复生成文件，已暂停自动重试。你可以稍后重新尝试。
```

用户消息默认不包含内部错误码。

### 19.2 LLM 润色

LLM 只能在严格约束下可选润色：

- 不改变错误严重性；
- 不改变可重试性；
- 不增加 allowed_actions 外的新动作；
- 不暴露 Worker、Tool、Provider、堆栈或内部错误码；
- 润色失败时直接使用确定性模板。

### 19.3 五类用户业务结果

用户侧统一表达：

1. 需要补充信息；
2. 正在按策略自动处理；
3. 部分完成；
4. 暂时未能完成，可以重新尝试；
5. 当前条件不满足，需要先处理配置、授权或业务前置条件。

## 20. 持久化与回放

### 20.1 三层存储

#### Run Snapshot

保存完整事实：

- Invocation 与 ExecutionPlan；
- operation 完整输入；
- ReAct Prompt、消息、Tool 参数和 Tool 返回；
- 模型原始响应；
- 完整异常堆栈；
- 成功结果与 Artifact 引用。

本地项目不做脱敏。

#### Trace

保存可检索时间线：

- turn_run_id、worker_run_id、job_run_id；
- plan_id、invocation_id、operation_id；
- event、status、latency；
- policy_id、decision、attempt；
- outcome、propagation；
- Snapshot 与 Failure 引用。

Trace 不重复嵌入完整简历、JD、Prompt 或模型大响应，原因是控制日志体积与检索噪声，不是隐私限制。

#### Failure

保存：

- FailureResult；
- 匹配策略与优先级；
- 尝试历史；
- 结果核对；
- 补偿；
- Worker/Turn/Job 传播；
- 用户消息 definition id 与最终渲染结果。

### 20.2 不用于恢复

持久化只用于：

- 本地诊断；
- 回放；
- 测试夹具；
- 稳定性统计；
- 面试证据。

应用启动时：

- running/awaiting_authorization 的旧 Worker/Turn/Plan 标记 interrupted；
- running/waiting 的 Job 标记 interrupted；
- 不重新调用任何 operation；
- 不自动向用户发送消息；
- 用户下一次请求创建新 Turn Run。

## 21. Emergency Sink

Failure Store 或 Trace Store 自身失败时不能再次进入 OperationExecutor 形成递归：

```text
Failure/Trace 持久化失败
→ abort_turn
→ 直接写 append-only Emergency Sink
→ Emergency Sink 失败则写 stderr
```

Emergency Sink：

- 使用独立固定本地文件；
- 只追加，不读取、不重试、不调用业务模块；
- 记录时间、Run/operation id、原始失败码和持久化异常；
- 不承担正常 Trace；
- 是唯一允许绕过 OperationExecutor 的最后诊断出口。

Failure 无法持久化时，系统已经无法证明状态一致性，当前 Turn 必须失败关闭。

## 22. SSE 与交付状态

业务执行和结果交付分离：

```json
{
  "execution_status": "success",
  "delivery_status": "disconnected"
}
```

规则：

- SSE 断开不自动等同业务失败；
- 已产生副作用的 Run 不因连接断开被粗暴中止；
- Job Run 不受 SSE 生命周期影响；
- Worker/Turn 已成功但最终文本未送达时，保留 Turn Result；
- 用户重新打开 Session 时读取已完成结果，不重新执行 operation；
- 当前系统不因此新增通用用户取消；
- SSE 建立、token 发送、done 发送分别作为可观察 operation。

内部过程仍是事件流，最终内容仍是文本流；前端打字机队列不把 Failure Trace 或 Worker 内部过程展示为最终回答。

## 23. 当前 Bug 的目标行为

强类型规格先形成：

```text
resume.generate_optimized_resume
→ asset.register_outputs
```

全局失败机制再保证：

### resume required operation 失败

```text
Failure
→ 匹配策略
→ 重试/修正/核对
→ 策略耗尽
→ resume Worker Run = failed
→ asset Invocation = blocked_by_upstream
→ asset Worker Run 不存在
→ Turn Run = failed
```

### resume 没有 operation 错误，但整体未完成

```text
运行完整性通过
→ 确定性 Success Contract 发现 verified_html_deliveries 为空
→ resume Worker Run = failed 或 needs_additional_input
→ asset blocked_by_upstream
```

### HTML 成功、登记失败

```text
resume Worker Run = success
→ asset 执行
→ register_outputs_index 失败
→ 保留 HTML
→ asset Worker Run = failed
→ Turn Run = partial_success
→ 用户看到“简历已生成，但产物登记未完成”
```

任何场景都不得再输出 asset 的角色说明来代替真实失败原因。

## 24. 测试策略

### 24.1 OperationExecutor

使用公开接口和注册到 fake `OperationRegistry` 的 Fake Adapter/Handler 验证：

- Success、BusinessOutcome、Failure 三分；
- 策略最具体优先；
- 同层冲突拒绝启动；
- 未分类失败关闭；
- 每条策略自己的 attempts/backoff/deadline；
- 安全上限；
- outcome_unknown 先核对；
- 幂等重试不重复副作用；
- 显式补偿与默认保留成果；
- 嵌套 operation 不重复重试副作用。
- 调用方无法传入或替换 handler；未知、重复、缺失或名称错配的 handler 绑定在启动或 resolve 时失败关闭。

### 24.2 Error Adapter

每个基础设施 Adapter 定向测试：

- 已知领域错误；
- 已知第三方异常；
- 未知异常；
- 原始 cause_ref；
- category/code 稳定。

### 24.3 Success Contract 与 Judge

验证：

- required operation 失败不能被 Judge 改为成功；
- RunEngine 使用前置 `DeterministicSuccessContractRegistry`，不维护第二份契约目录；
- `ContractEvaluation.satisfied=False` 阻止 Worker Run success，且不能向 Plan 传播 verified Outcome；
- `ContractEvaluation.satisfied=True` 的 `verified_outcomes` 原样进入 WorkerRunResult，不从原始结构化输出重新提取；
- when_needed 在确定性规则足够时不调用 Judge；
- required 调用 Judge；
- Judge uncertain/失败形成 outcome_unknown；
- 运行时 Judge 与离线 Eval 分开。

### 24.4 Worker/Turn 聚合

验证：

- `start_worker()` 原样使用 PlanDispatch 中的 worker_run_id，plan/node/turn 身份错配或重复编号时不创建第二个 Worker Run；
- WorkerRunResult 转换出的 PlanNodeResult 保持相同 plan_id、node_id、worker_run_id、闭合终态和具体 verified Outcome 类型；
- running、awaiting_authorization 和未经过确定性 Contract 的 accepted_async 不能直接转换为 PlanNodeResult；`market.start_research` 在 Job 创建并持久化、Contract 产生 `JobAcceptedOutcome` 后必须先形成 Worker Run success，再立即结束当前 Turn 的节点；
- 独立 Market Job Run 使用自己的 Job ExecutionPlan；其 queued/running/waiting_user 或后续失败不回写已经 success 的启动 Worker Run，也不阻塞当前 Turn 节点；
- success 才解除默认下游依赖；
- partial_success 默认不解除；
- blocked_by_upstream 不创建 Worker Run；
- HTML 成功、登记失败形成 Turn partial_success；
- resume 失败形成 Turn failed；
- 最终消息由 TurnResultRenderer 生成。

### 24.5 Gate 与授权

验证：

- Operation Authorization 保持同 Run；
- 参数变化使旧 Run superseded；
- Workflow Transition 新建 Turn；
- Additional Input 新建 Run；
- Session Grant 跨 Run、不跨 Session，且不替代单次 operation 的 confirmation/claim/continuation/receipt；
- 授权约束越界重新请求；
- 不设置授权请求固定 TTL。

### 24.6 Job Run

验证：

- Worker 成功创建 Job 后独立运行；
- Job 失败不回写 Worker；
- Job 重启后 interrupted 且不恢复；
- 市场现有 continue/cancel 保持；
- 通用 Worker/Turn 没有新增取消入口。

### 24.7 持久化与 SSE

验证：

- Snapshot 保存完整输入输出；
- Trace 使用引用；
- Failure 记录策略与传播；
- Failure Store 失败进入 Emergency Sink；
- SSE 断开不重新执行业务 operation；
- Turn 成功但 delivery disconnected 可重新读取结果。

### 24.8 当前 Bug 系统级回归

两个 plan 全部实施后，在干净临时环境增加最后的跨模块回归测试：

1. 创建 Session 并进入 resume_optimize；
2. 创建 resume → asset ExecutionPlan；
3. 模拟 resume 没有已知 Tool 错误，但返回空交付物或语义 incomplete；
4. 验证 resume 不为 success；
5. 验证 asset 未执行；
6. 验证 asset 为 blocked_by_upstream；
7. 验证 Turn 正确聚合；
8. 验证用户消息解释“简历未生成”；
9. 验证回复不出现资产智能体角色声明；
10. 验证 output 与资产索引无新增；
11. 验证 Trace、Failure、Snapshot 关联完整。

该测试使用确定性 Runner/Adapter，不依赖真实 LLM。真实 LLM Eval 只覆盖语义 Judge 能力。

## 25. 验收标准

- 所有有业务意义的 operation 通过 OperationExecutor。
- OperationExecutor 只接收 OperationRequest，并通过前置 `OperationRegistry.resolve()` 使用唯一 Definition/handler 绑定；调用方不能传入或替换 handler。
- 所有基础设施接缝都有 Error Adapter。
- OperationResult 明确区分 Success、BusinessOutcome、Failure。
- 五类 Failure 和未分类兜底均有稳定机器码。
- OperationPolicyRegistry 是唯一失败策略事实来源。
- 策略按固定最具体优先级选择，冲突拒绝启动。
- 不存在统一最大重试次数；每条策略明确 attempts 或 deadline。
- 有副作用且可重试的 operation 具备幂等键或结果核对。
- outcome_unknown 不直接重试。
- Worker Run 使用“运行完整性 → 前置确定性 ContractEvaluation → 可选 Judge”三段式判定，且不复制确定性契约 Registry。
- Judge 不覆盖 operation 硬失败或确定性契约。
- Worker、Turn、Job 状态与聚合符合本规格。
- ExecutionPlan 上游非 success 时阻断依赖节点。
- Turn 最终回复不再由最后一个 Worker 决定。
- 内部错误码不展示给用户。
- 用户错误消息目录是确定性事实来源，LLM 仅可选润色。
- Run Snapshot、Trace、Failure、Emergency Sink 全部可验证。
- 应用重启只标记 interrupted，不恢复旧执行。
- SSE execution/delivery 状态分离。
- 不新增通用用户取消；市场已有取消能力保持。
- 强类型规格与本规格各自拥有独立 plan 和测试。
- 当前 demo Bug 的干净环境系统级回归测试最终通过。

## 26. 预计变更范围

实施计划至少需要评估：

| 路径 | 预期变化 |
|------|----------|
| `backend/career_os/platform/operation/` | 复用前置 OperationDefinition/Registry，并增加 OperationResult、Executor、Policy、Adapter 接口；不得复制授权元数据 |
| `backend/career_os/platform/run/` | Turn/Worker/Job Run 模型与本地 Store |
| `backend/career_os/platform/trace/` | Run/Plan/Invocation/operation 关联和引用 |
| `backend/career_os/harness/executor.py` | Tool、Store、LLM 等统一 OperationExecutor 入口 |
| `backend/career_os/harness/delegate.py` | Invocation、授权与 Worker Run 创建 |
| `backend/career_os/agents/graphs/workers/` | operation 结果与运行完整性证据收集 |
| `backend/career_os/agents/graphs/coordinator.py` | Plan 执行、依赖传播和 Turn 聚合 |
| `backend/career_os/agents/lc/` | Provider Adapter、Judge 与受约束输出 |
| `backend/career_os/platform/store/` | Snapshot、Failure、Run 记录与 Adapter |
| `backend/career_os/runtime/sse.py` | delivery operation 与交付状态 |
| `backend/career_os/api/chat.py` | Turn 生命周期和用户结果渲染 |
| `backend/career_os/platform/market_research/` | 现有领域状态到 Job Run 的 Adapter |
| `backend/tests/` | operation、策略、Run、Gate、Job、SSE 与最终 Bug 回归 |

上述目录是模块接缝建议，不是 plan 中必须机械创建的目录。实施计划应优先形成深模块，避免只增加大量透传类型。

## 27. 实施顺序与依赖

1. 先完成《强类型 WorkerInvocation 与结果契约》对应 plan；它提供闭合 `WorkerInvocation`/`VerifiedOutcome` 联合、唯一 `DeterministicSuccessContractRegistry`、泛型 `ContractEvaluation[TOutcome]`、统一 Runner、暂停现场和闭合 continuation。
2. 再完成《ExecutionPlan 与受控执行生命周期》对应 plan；它提供强类型 OutcomeBinding、原子 `PlanDispatch`、闭合 `PlanNodeResult`/`PlanAdvanceResult`、唯一 `OperationRegistry`，以及单次 operation 的活动快照、confirmation、claim 和 committed receipt 状态机。
3. 两个前置 plan 都通过各自验收后，才实施本规格对应的独立 plan；本规格不得用动态字典、临时目录、第二份 Registry、第二份授权请求 Store 或重新生成的 Worker Run 编号替代前置能力。
4. 三个 plan 内各自测试先行。
5. 当前 2026-07-22 demo Bug 的跨模块系统级回归测试最后在干净环境增加。
6. 不在本规格实施中迁移或修复旧 demo 运行记录。
