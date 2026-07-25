# 全局失败机制 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Each vertical slice follows red → green and uses checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立覆盖同步 Worker Run、Turn Run 和后台 Job Run 的全局失败机制，使所有有业务意义的 operation 使用确定性结果、错误分类和策略，并通过 operation 事实、前置计划的泛型 `ContractEvaluation[VerifiedOutcome]` 与可选 Judge 判断真实完成状态，同时保留前置计划建立的 Invocation、Outcome 和 binder 静态类型关系。

**Architecture:** `OperationExecutor`（operation 执行器）是执行有业务意义动作的唯一深模块接口：它保存不可变输入快照，通过基础设施 Adapter 归一化结果，从代码策略注册表选择唯一策略，并负责重试、结果核对、补偿、断路器和审计。`RunEngine`（Run 引擎）在上层直接消费前置计划原子认领产生的 `PlanDispatch`，使用其中冻结的同一个 `worker_run_id` 管理 Worker/Turn/Job 生命周期：先读取 operation 与运行完整性事实，再调用前置计划已经实现的 `DeterministicSuccessContractRegistry.evaluate()`，必要时调用受约束 Judge，最后把终态 WorkerRunResult 转成强类型 `PlanNodeResult`、聚合 ExecutionPlan，并交给 `TurnResultRenderer` 生成用户可读结果。Snapshot、Trace、Failure 和 Emergency Sink 提供本地可回放证据，但不恢复应用重启前的旧执行。

**Tech Stack:** Python 3.11、Pydantic 2、LangGraph、LiteLLM、FastAPI SSE、pytest、本地 JSON/JSONL Store

**Design SSOT:** `../specs/2026-07-23-global-failure-mechanism-design.md`

**Required predecessor:** `2026-07-23-typed-worker-invocation-execution-plan.md` 已全部实施并通过，且已提供闭合 `WorkerInvocation`/`VerifiedOutcome` 联合、唯一 `DeterministicSuccessContractRegistry`、泛型 `ContractEvaluation[TOutcome]`、强类型 OutcomeBinding、原子 `PlanDispatch`、闭合 `PlanNodeResult`/`PlanAdvanceResult`、唯一 `OperationRegistry`，以及单次 operation 的活动快照、闭合 continuation、confirmation、claim 和 committed receipt 状态机。

**Status:** 待实现

---

## Global Constraints

- 本 plan 不重新设计 WorkerInvocation、ExecutionPlan 或确定性 Success Contract；直接消费前置 plan 提供的闭合 Invocation/Outcome 联合、Invocation/Plan 标识、allowed operations、required/optional Skill、OutcomeDefinition、success_contract_id、泛型 `ContractEvaluation` 和 OutcomeBinding。
- RunEngine 启动 Worker 时必须消费完整 `PlanDispatch`，原样沿用 claim 已绑定的 `worker_run_id`；不得只传 Invocation 后重新生成 Worker Run 编号。
- 本 plan 不创建第二份 Success Contract Registry，不复制各 Run Kind 的确定性契约 handler，也不从原始 Worker `structured_output` 重新提取命名 Outcome。
- 本 plan 复用前置 `OperationDefinition/OperationRegistry`，只增加执行结果、失败策略和 Adapter 绑定；不得复制 operation 名称、`requires_authorization`、`durable_result_ledger_id` 或 durable ledger 注册关系。
- RunEngine、WorkerRunResult 与 Store 不得把具体 Invocation/Outcome 降级为裸 `BaseModel`、`Any` 或 `Mapping[str, Any]`；新增接口必须继续通过前置 plan 的 Pyright strict 门禁。
- `OperationResult` 顶层只允许 `Success`、`BusinessOutcome`、`FailureResult`；正常等待授权、等待补充信息、无结果和后台任务已接受不能伪装为 Failure。
- Failure 第一版固定为 `input_required`、`contract_violation`、`tool_failure`、`model_failure`、`policy_blocked`，并提供 `unclassified_failure / unexpected_exception` 兜底。
- OperationPolicyRegistry 是失败策略唯一事实来源；策略安全行为不得从 JSON、Prompt 或 LLM 输出加载。
- 不设置统一最大重试次数。每条策略按“operation type + error code + idempotency”明确 attempts 或 deadline。
- 独立安全上限只防止配置错误和无限循环，触发后内部记录 `retry_safety_limit_exceeded`；用户消息默认不显示内部错误码。
- 同一个同步 Worker Run 内自动重试固定使用 operation 首次调用的不可变输入快照，不重新读取整个 Session 或 Profile。
- 有副作用的 `outcome_unknown` 不能直接重试，必须先执行结果核对。
- 后续失败默认保留已经确认的上游成果；只有显式登记的安全 compensation handler 可以补偿。
- Worker Run 必须执行两层判断：已知 required operation 失败可直接阻止成功；没有已知 operation 错误时仍必须检查整体业务完成度。
- Judge 不能覆盖 required operation 硬失败或确定性契约失败；运行时 Judge 与离线内容质量 Eval 分开。
- Operation Authorization 可以保持同一个 Run；Workflow Transition 与 Additional Input 必须结束当前 Run，并在后续用户消息创建新 Run。
- Session Grant 可以跨 Worker Run、不跨 Session，只表达可复用授权约束；单次 operation 的 confirmation、claim、continuation 和 receipt 继续由前置 SessionStore 状态机唯一管理。授权请求没有固定 TTL；活动快照虽已持久化，但运行实例变化后只标记 interrupted，不由新进程恢复，持久化 Grant 可供新 Run 重新校验。
- 应用重启只把活动 Run/Plan/Job 标记 interrupted，不继续任何旧 operation。
- 不新增通用 Worker/Turn 用户取消；保留市场 Job 已有 continue/cancel。
- 本地 Snapshot 保存完整事实，不做脱敏；Trace 和 Failure 使用引用控制体积与检索噪声。
- Emergency Sink 是唯一允许绕过 OperationExecutor 的最后诊断出口。
- 测试只通过已确认 seam：`OperationExecutor`、Error Adapter、OperationPolicyRegistry、`RunEngine`、`TurnResultRenderer`、Job Adapter、SSE delivery。
- 每个 Task 使用纵向 tracer bullet：先写一个公开行为红灯测试，再实现最小闭环，不批量写所有测试后再实现。
- 不迁移或修复旧 demo 运行记录；最终 Bug 回归只在新的干净临时环境运行。
- 不触碰用户现有 `docs/assets/` 或其他无关改动。

## Confirmed Test Seams

| Seam | Interface | 验证行为 |
|------|-----------|----------|
| operation 执行 | `OperationExecutor.execute()` | 结果归一化、策略选择、重试、核对、补偿和审计 |
| 错误适配 | `OperationAdapter.to_result()` | 已知错误、第三方异常和未知异常如何形成稳定 Failure |
| 策略注册 | `OperationPolicyRegistry.resolve()` | 最具体策略、冲突和失败关闭 |
| Run 判定 | `RunEngine.start_worker()/finish_worker()/to_plan_node_result()/finish_turn()` | claim 身份如何贯通 Worker Run，以及 operation 事实、前置 ContractEvaluation、可选 Judge 和 Plan 如何聚合 |
| 静态类型门禁 | `uv run pyright` | RunEngine 是否保持闭合 Invocation/Outcome 与泛型 ContractEvaluation，而未擦除为动态字典 |
| 用户呈现 | `TurnResultRenderer.render()` | 内部错误如何映射成确定性、可理解文本 |
| 后台任务 | `MarketJobAdapter` | 现有市场状态如何映射到 Job Run 且不恢复旧任务 |
| 结果交付 | SSE delivery interface | 执行成功与连接断开如何分离 |

这些 seam 已由设计规格第 24 节确认，不为测试暴露私有策略表、重试循环或 Store 内部字典。

## Target File Structure

### 前置模块扩展与新增深模块

```text
backend/career_os/platform/operation/models.py
    # 保留前置 OperationDefinition，并增加 OperationRequest、Success、BusinessOutcome、FailureResult、ExecutionResult

backend/career_os/platform/operation/registry.py
    # 复用前置 operation 与 durable ledger 唯一目录，供 Executor/Policy 查询，不复制授权元数据

backend/career_os/platform/operation/policy.py
    # OperationPolicyRegistry、Retry/Idempotency/CircuitBreaker 策略和启动校验

backend/career_os/platform/operation/adapters.py
    # Adapter interface、注册表和通用未知异常兜底

backend/career_os/platform/operation/executor.py
    # 唯一 execute 接口及内部重试、核对、补偿、审计流程

backend/career_os/platform/operation/catalog.py
    # 第一版稳定错误码、Adapter 与策略代码装配；operation 身份和授权元数据仍来自 OperationRegistry

backend/career_os/platform/run/models.py
    # WorkerRun、TurnRun、JobRun、状态、Outcome 与持久化模型

backend/career_os/platform/run/engine.py
    # 编排运行完整性、前置 ContractEvaluation、可选 Judge 与 Worker/Turn/Job 聚合

backend/career_os/platform/run/store.py
    # Snapshot、Run、Failure 的本地持久化和 interrupted 标记

backend/career_os/platform/run/messages.py
    # 确定性用户消息目录和 TurnResultRenderer

backend/career_os/platform/run/emergency.py
    # append-only Emergency Sink

backend/career_os/platform/run/authorization.py
    # 只管理跨 Worker Run 的 Session Grant 约束与查找，不保存单次 operation confirmation/claim/continuation/receipt

backend/career_os/agents/lc/success_judge.py
    # 受约束语义 Judge，仅返回固定 verdict/reason/evidence/confidence
```

### 新增测试

```text
backend/tests/operation/test_operation_executor.py
backend/tests/operation/test_operation_policy.py
backend/tests/operation/test_error_adapters.py
backend/tests/operation/test_side_effect_idempotency.py
backend/tests/run/test_worker_success_contract.py
backend/tests/run/test_turn_aggregation.py
backend/tests/run/test_run_persistence.py
backend/tests/run/test_authorization_lifecycle.py
backend/tests/run/test_market_job_adapter.py
backend/tests/runtime/test_sse_delivery.py
backend/tests/system/test_resume_failure_propagation.py
```

现有领域模块保留自己的实现和错误类型；通过 Adapter 接入，不把所有第三方细节堆进一个巨大中央异常函数。

---

## Task 1: 建立 write_resume_html 的 OperationResult tracer bullet

**Files:**

- Modify: `backend/career_os/platform/operation/__init__.py`
- Modify: `backend/career_os/platform/operation/models.py`
- Modify: `backend/career_os/platform/operation/registry.py`
- Create: `backend/career_os/platform/operation/adapters.py`
- Create: `backend/career_os/platform/operation/policy.py`
- Create: `backend/career_os/platform/operation/executor.py`
- Create: `backend/career_os/platform/operation/catalog.py`
- Create: `backend/tests/operation/test_operation_executor.py`
- Create: `backend/tests/operation/test_operation_policy.py`
- Create: `backend/tests/operation/test_error_adapters.py`
- Reference: `backend/career_os/platform/tool/handlers/resume_html.py`

**External interface:**

```python
class OperationExecutor:
    def execute(
        self,
        request: OperationRequest,
    ) -> OperationExecutionResult: ...
```

字段和函数含义：

- `OperationExecutor.execute`（执行业务操作）：先通过前置 `OperationRegistry.resolve(request.operation_type)` 取得唯一 `ResolvedOperation(definition, handler)`，再选择 Adapter 和 Policy；`operation_type` 必须等于该 Definition 与 handler 的 `operation_name`。Executor 不接受调用方传入 handler、新的授权要求或 ledger 编号。

- `OperationRequest`（operation 请求）：固定 actor、purpose、Run/Invocation 关联和输入快照引用。
- `OperationExecutionResult`（执行结果）：保存最终 OperationResult、策略决策、attempt 和审计引用。
- `execute`（执行 operation）：只接收请求，解析 Registry 绑定的唯一 handler 并隐藏 Adapter、策略、重试和审计复杂度。

- [ ] **Step 1: 写三分结果和未知异常红灯测试**

把 Fake handler 注册到可注入的 fake `OperationRegistry` 后验证：

```python
def test_execute_returns_success_for_verified_value(): ...
def test_execute_preserves_business_outcome_without_failure_policy(): ...
def test_execute_maps_known_resume_error_to_stable_failure(): ...
def test_execute_maps_unknown_exception_and_fails_closed(): ...
def test_execute_cannot_accept_or_replace_registry_handler(): ...
```

运行：

```bash
cd backend && uv run pytest \
  tests/operation/test_operation_executor.py \
  tests/operation/test_error_adapters.py -q
```

期望：红灯。

- [ ] **Step 2: 实现三类 OperationResult 和 Failure 分类**

Pydantic 模型固定 `extra="forbid"`。`FailureResult` 不包含 `retryable`，只保存失败事实。

预检缺少用户信息返回 `BusinessOutcome(needs_additional_input)`；只有 operation 已开始后发现输入快照违反声明才使用 `input_required`。

- [ ] **Step 3: 实现 Adapter 注册与 unknown fallback**

`OperationAdapter`（operation 适配器）在自己的 seam 识别领域错误。中央注册表只负责按 operation type 找 Adapter，不知道每个第三方异常细节。

第一条领域映射：

```text
write_resume_html invalid_html
→ contract_violation / invalid_html / failed_before_effect
```

未知异常：

```text
unclassified_failure / unexpected_exception
```

并保存完整异常的 `cause_ref` 占位引用。

- [ ] **Step 4: 实现最小策略注册表和选择优先级**

先覆盖 `write_resume_html`：

- required；
- invalid_html 允许 repair-context 策略重试；
- path_not_allowed 不重试；
- unknown failure 失败关闭。

公开 `resolve()` 返回唯一策略；同层冲突由 `validate_startup()` 拒绝。

- [ ] **Step 5: 转绿**

```bash
cd backend && uv run pytest \
  tests/operation/test_operation_executor.py \
  tests/operation/test_operation_policy.py \
  tests/operation/test_error_adapters.py -q
```

---

## Task 2: 实现策略级重试、安全上限和不可变输入快照

**Files:**

- Modify: `backend/career_os/platform/operation/models.py`
- Modify: `backend/career_os/platform/operation/policy.py`
- Modify: `backend/career_os/platform/operation/executor.py`
- Modify: `backend/tests/operation/test_operation_executor.py`
- Modify: `backend/tests/operation/test_operation_policy.py`

- [ ] **Step 1: 逐个增加重试红灯测试**

覆盖：

- 不同 error code 使用不同 max_attempts；
- deadline 策略不依赖统一 max；
- fixed 与 exponential_jitter 使用可注入 Clock/Backoff；
- repair_context 只向下一 attempt 注入固定修正事实；
- 每次 attempt 使用同一 input_snapshot_ref；
- 安全上限触发内部 `retry_safety_limit_exceeded`；
- 安全上限不把原始业务错误伪装成最终内部码。

测试注入 Fake Clock，不使用真实 sleep。

- [ ] **Step 2: 实现 RetryPolicy 和 Executor 循环**

`RetryPolicy`（重试策略）必须至少提供 attempts 或 deadline。`OperationExecutor` 接受时钟和退避依赖，不在内部直接创建真实时间依赖。

每次 attempt 写：

```text
operation_id
attempt
input_snapshot_ref
policy_id
result
decision
```

- [ ] **Step 3: 转绿**

```bash
cd backend && uv run pytest \
  tests/operation/test_operation_executor.py \
  tests/operation/test_operation_policy.py -q
```

---

## Task 3: 完成有副作用 operation 的幂等、核对和成果保留

**Files:**

- Create: `backend/tests/operation/test_side_effect_idempotency.py`
- Modify: `backend/career_os/platform/operation/executor.py`
- Modify: `backend/career_os/platform/operation/catalog.py`
- Modify: `backend/career_os/platform/tool/handlers/resume_html.py`
- Modify: `backend/career_os/platform/tool/handlers/outputs.py`
- Modify: related handler tests

- [ ] **Step 1: 写 write/register 副作用红灯测试**

验证：

- `write_resume_html` outcome_unknown 时先 probe，不直接重写；
- 已生成 delivery 时 probe 收敛为 Success；
- register timeout 后查询 delivery id/content hash；
- 下游登记失败保留 HTML；
- 同一 operation_id 重试不重复文件或索引；
- 嵌套 operation 只由最内层副作用 operation 重试。

- [ ] **Step 2: 为 HTML 写入增加稳定幂等信息**

使用稳定 operation_id、目标内容哈希和原子替换。Handler 仍负责文件领域约束；Executor 负责何时尝试和何时核对。

- [ ] **Step 3: 为资产登记增加 probe**

按 delivery id 或内容哈希查询现有索引。没有显式 compensation handler 时，登记失败不得删除 HTML。

- [ ] **Step 4: 转绿**

```bash
cd backend && uv run pytest \
  tests/operation/test_side_effect_idempotency.py \
  tests/e2e/test_resume_levels.py \
  tests/e2e/test_asset_register.py -q
```

---

## Task 4: 让 Harness Tool 执行统一进入 OperationExecutor

**Files:**

- Modify: `backend/career_os/harness/executor.py`
- Modify: `backend/career_os/platform/tool/registry.py`
- Modify: `backend/career_os/agents/graphs/workers/react_runner.py`
- Modify: `backend/career_os/agents/graphs/workers/react_mocks.py`
- Modify: `backend/tests/trace/test_trace_writer.py`
- Modify: `backend/tests/harness/test_task_tools.py`
- Modify: `backend/tests/agents/test_worker_react_runner.py`
- Modify: `backend/tests/operation/test_operation_executor.py`

- [ ] **Step 1: 写防绕过红灯测试**

验证：

- Worker 不能取得原始 Tool handler；
- Harness、ToolRegistry 和调用方不能向 `OperationExecutor.execute()` 传入 handler；
- 所有已注册 Tool 都有 operation definition、Adapter 和 policy；
- 未登记 operation 返回 `operation_policy_missing` 并失败关闭；
- Tool 权限拒绝映射 `policy_blocked / tool_not_allowed`；
- ReAct 收集结构化 OperationExecutionResult，不再用 `hasattr(code)` 猜错。

- [ ] **Step 2: 深化 Harness.execute_tool**

`Harness.execute_tool` 组装 `OperationRequest`，传入 Invocation/Run 关联和输入快照，然后调用全局 OperationExecutor。

ToolRegistry 只提供模型可见 Schema，不查找或返回 handler；`OperationExecutor` 只通过前置 `OperationRegistry.resolve()` 取得唯一受保护 handler。

- [ ] **Step 3: 建立 Tool operation 完整性目录**

第一版覆盖：

- 所有 Worker 业务 Tool；
- Skill Tool；
- Coordinator task/profile/gate Tool。

关键性必须结合 `operation_type + run_kind + purpose`，不能成为 Tool 永久属性。

- [ ] **Step 4: 转绿**

```bash
cd backend && uv run pytest \
  tests/operation/test_operation_executor.py \
  tests/harness/test_task_tools.py \
  tests/agents/test_worker_react_runner.py \
  tests/trace/test_trace_writer.py -q
```

---

## Task 5: 建立 WorkerRun 并编排三段式成功判定

**Files:**

- Create: `backend/career_os/platform/run/__init__.py`
- Create: `backend/career_os/platform/run/models.py`
- Create: `backend/career_os/platform/run/engine.py`
- Create: `backend/career_os/agents/lc/success_judge.py`
- Create: `backend/tests/run/test_worker_success_contract.py`
- Modify: `backend/career_os/agents/graphs/workers/base.py`
- Modify: `backend/career_os/agents/graphs/workers/registry.py`
- Modify: `backend/career_os/agents/graphs/workers/react_runner.py`
- Modify: `backend/career_os/agents/schemas/workers.py`

**Interface:**

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

- `start_worker`（启动 Worker Run）：使用 `PlanDispatch` 中已经冻结的 plan_id、node_id、Invocation 和 worker_run_id 创建 running 生命周期，不再生成新编号。
- `turn_run_id`（Turn Run 编号）：标识当前用户请求的运行生命周期，用于阻止 dispatch 跨 Turn 使用。
- `finish_worker`（结束 Worker Run）：按运行完整性、确定性契约和可选 Judge 顺序形成终态，并保留同一 node_id 与 worker_run_id。
- `to_plan_node_result`（转换计划节点结果）：把终态 WorkerRunResult 投影为前置 plan 的闭合 PlanNodeResult，供 ExecutionPlanExecutor 校验身份并推进节点。

- [ ] **Step 1: 写 resume 三段式集成判定红灯测试**

覆盖：

- claim 返回的 `PlanDispatch.worker_run_id` 与 `start_worker()` 创建的 WorkerRun 编号完全相同；
- `dispatch.plan_id`、`dispatch.node_id`、`dispatch.invocation.node_id` 或 `turn_run_id` 不匹配时不创建 WorkerRun；
- 对相同 `worker_run_id` 重复调用 `start_worker()` 被拒绝，不会启动第二次 Worker 执行；
- required operation 失败直接阻止 success；
- 所有 operation 成功但前置 `ContractEvaluation.satisfied=False` 仍失败；
- ReAct 提前结束或只返回角色说明不成功；
- 前置契约产生的 `VerifiedHtmlDeliveriesOutcome` 原类型进入 WorkerRunResult，并可交给已注册的强类型 binder 解除 Plan 依赖；
- RunEngine 不从原始 `structured_output` 自行复制或重建 verified Outcome；
- `typing.assert_type` 证明 RunEngine 的 satisfied 分支保持 `tuple[VerifiedOutcome, ...]`，没有降级为动态字典；
- `to_plan_node_result()` 保持 node_id、worker_run_id、闭合终态和原类型 verified Outcome；running、awaiting_authorization 和未经过契约验收的 accepted_async 不能直接转换。`market.start_research` 只有在 Job 创建并持久化、确定性 Contract 产生 `JobAcceptedOutcome`、Worker Run 已转为 success 后，才能立即转换并结束当前 Turn 的节点；
- 由 `to_plan_node_result()` 形成的结果可以使用 node_id 作为 mapping key，通过前置 `ExecutionPlanExecutor.advance()` 的身份校验；
- optional operation 失败可以 partial/degraded；
- Judge 不能覆盖硬失败；
- Judge uncertain/失败形成 outcome_unknown；
- 确定性规则足够时 `when_needed` 不调用 Judge。

- [ ] **Step 2: 实现 WorkerRun 模型和运行完整性**

状态固定：

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

运行完整性读取真实 operation evidence、ReAct 收敛、Skill 加载和未闭合调用。

`start_worker()` 只能从 `PlanDispatch` 创建 WorkerRun，并把 `dispatch.worker_run_id` 原样写入模型和 Store。创建前验证 plan_id、node_id、Invocation.node_id 与 turn_run_id 的归属关系；相同 Worker Run 编号已存在时失败关闭，不能覆盖旧记录或再次启动执行。

- [ ] **Step 3: 接入前置确定性 Success Contract Registry**

RunEngine 必须：

1. 依赖注入前置 plan 的 `DeterministicSuccessContractRegistry`；
2. 为同一 Registry 注入由 OperationResult/WorkerExecutionEvidence 支持的 Artifact/Index verifier Adapter，所有外部事实读取仍遵守 OperationExecutor 规则；
3. 使用 `evaluate()` 返回的 `ContractEvaluation[VerifiedOutcome]`，不得读取私有契约 handler；
4. 只有 `satisfied=True` 时接受闭合联合中的具体 `verified_outcomes`，并保持其类型直到 WorkerRunResult 与 Plan binder；
5. 将 `satisfied=False` 与 operation 事实、运行完整性结合，形成最终 failed、needs_additional_input 或其他合法 Worker Run 状态；
6. 不创建第二份契约目录，不复制 resume/asset 的路径、HTML、档位或索引验收规则。

- [ ] **Step 4: 实现受约束 Judge**

Judge 只返回固定 verdict、reason_codes、evidence_refs、confidence，并作为模型 operation 执行。离线 Eval 不复用运行时 verdict。

- [ ] **Step 5: 统一 WorkerRunner 返回 WorkerRunResult**

删除强类型 plan 的临时结构化结果 Adapter。真实 Runner、mock、stub 都通过 `RunEngine.finish_worker()` 返回同一 WorkerRunResult；Coordinator 随后调用 `RunEngine.to_plan_node_result()`，以 `node_id` 为 mapping key 交给 `ExecutionPlanExecutor.advance()`。该转换只投影终态、同一 `worker_run_id` 和原类型 verified Outcome，不重新判断契约，也不复制动态输出。

- [ ] **Step 6: 转绿**

```bash
cd backend && uv run pytest \
  tests/run/test_worker_success_contract.py \
  tests/agents/test_worker_invocation_runner.py \
  tests/agents/test_worker_react_runner.py \
  tests/agents/test_worker_emit.py -q
```

---

## Task 6: 聚合 ExecutionPlan 为 TurnRun，并确定性渲染用户结果

**Files:**

- Create: `backend/career_os/platform/run/messages.py`
- Create: `backend/tests/run/test_turn_aggregation.py`
- Modify: `backend/career_os/platform/run/engine.py`
- Modify: `backend/career_os/agents/graphs/coordinator.py`
- Modify: `backend/career_os/agents/lc/coordinator_llm.py`
- Modify: `backend/career_os/api/chat.py`
- Modify: `backend/tests/agents/test_coordinator_execution_plan.py`
- Modify: `backend/tests/agents/test_synthesis_pipeline_context.py`

**Interfaces:**

```python
class RunEngine:
    def finish_turn(self, turn_run: TurnRun, plan: ExecutionPlan) -> TurnRunResult: ...


class TurnResultRenderer:
    def render(self, result: TurnRunResult) -> RenderedTurnResult: ...
```

- [ ] **Step 1: 写依赖感知聚合红灯测试**

验证：

- 全部目标 success → Turn success；
- HTML 成功、登记失败 → partial_success；
- resume 失败 → failed；
- 关键节点 outcome_unknown → outcome_unknown；
- blocked_by_upstream 不创建假 WorkerRun；
- 最后一个 Worker 摘要不能覆盖 Turn 真实结果。

- [ ] **Step 2: 实现 TurnRun 聚合**

`finish_turn()` 读取 Plan 目标节点、已保留 Outcome 和 WorkerRunResult，不按调用顺序或最后结果猜测。

- [ ] **Step 3: 实现确定性消息目录**

目录覆盖五类用户业务结果。内部 `retry_safety_limit_exceeded` 映射为用户可理解文本，默认不展示错误码。

`TurnResultRenderer` 不暴露 Worker、Tool、Provider 或堆栈；可使用“简历生成”“产物登记”等业务动作名称。

- [ ] **Step 4: 限制 LLM 润色**

LLM 只能在 `allowed_actions`、严重性和可重试性不变的约束下润色；失败时使用确定性模板。

- [ ] **Step 5: 转绿**

```bash
cd backend && uv run pytest \
  tests/run/test_turn_aggregation.py \
  tests/agents/test_coordinator_execution_plan.py \
  tests/agents/test_synthesis_pipeline_context.py -q
```

---

## Task 7: 持久化 Snapshot、Trace、Failure 和 Emergency Sink

**Files:**

- Create: `backend/career_os/platform/run/store.py`
- Create: `backend/career_os/platform/run/emergency.py`
- Create: `backend/tests/run/test_run_persistence.py`
- Modify: `backend/career_os/platform/trace/writer.py`
- Modify: `backend/tests/trace/test_trace_writer.py`
- Modify: `backend/career_os/main.py`

- [ ] **Step 1: 写持久化与递归失败红灯测试**

验证：

- Snapshot 保存 Invocation、Plan、operation 输入、Prompt、Tool 参数/返回、模型原始响应和完整异常；
- Trace 只保存 Run/Plan/Invocation/operation 标识和引用；
- Failure 保存策略、attempt、probe、补偿、传播和用户消息 id；
- Failure Store 失败时 abort_turn 并写 Emergency Sink；
- Emergency Sink 失败只写 stderr，不递归调用 OperationExecutor；
- 启动时 running/awaiting Run 标记 interrupted 且不执行 handler。

- [ ] **Step 2: 实现本地 Store**

使用环境隔离的数据根目录。Snapshot 保存完整本地事实，不脱敏；Trace/Failure 对大字段保存引用。

- [ ] **Step 3: 扩展 TraceWriter 关联字段**

每条相关事件支持：

```text
turn_run_id
worker_run_id
job_run_id
plan_id
invocation_id
operation_id
policy_id
attempt
outcome
propagation
```

不要为每次 emit 随机生成无法关联的 run_id。

- [ ] **Step 4: 实现启动 interrupted 标记**

FastAPI lifespan 启动时只更新状态，不恢复旧 operation、不发送自动消息。

- [ ] **Step 5: 转绿**

```bash
cd backend && uv run pytest \
  tests/run/test_run_persistence.py \
  tests/trace/test_trace_writer.py -q
```

---

## Task 8: 实现 Operation Authorization 与三类 Gate 生命周期

**Files:**

- Create: `backend/career_os/platform/run/authorization.py`
- Create: `backend/tests/run/test_authorization_lifecycle.py`
- Modify: `backend/career_os/platform/operation/registry.py`
- Modify: `backend/career_os/harness/gate.py`
- Modify: `backend/career_os/api/chat.py`
- Modify: `backend/career_os/platform/store/session.py`
- Modify: `backend/tests/harness/test_gate_rules.py`
- Modify: `backend/tests/api/test_chat_intent_phase.py`

- [ ] **Step 1: 写授权生命周期红灯测试**

验证：

- 前置 Plan 已实现的 simple operation authorization 保持同 WorkerRun/Plan、同 continuation 和同 `operation_call_id`，本 Task 不创建第二份 request 状态；
- ReAct 与确定性 continuation 仍通过前置 `SessionStore` 的 confirmation/claim/receipt 接口恢复，`platform/run/authorization.py` 不读写其内部状态；
- 参数变化使旧 Run superseded；
- Workflow Transition 确认后新 Turn；
- Additional Input 补充后新 WorkerRun；
- Grant 跨 WorkerRun、不跨 Session；
- constraints 越界重新请求；
- policy_version 变化使旧 Grant 失效；
- authorization request 没有固定 TTL；
- 前置活动快照在相同 `runtime_instance_id` 内仍可恢复；运行实例变化后旧 Run/Plan 标记 interrupted，持久化 Grant 只能供新 Run 重新校验，不能恢复旧 continuation 或推断旧 operation 已提交。

- [ ] **Step 2: 实现 Session Grant Registry**

Grant 绑定：

```text
session_id + operation_type + constraints + policy_version
```

`resolve_grant()`（解析会话授权凭据）只根据 Session、operation、约束和策略版本返回 `GrantMatched` 或 `GrantRequired`，不直接推进前置 `OperationAuthorizationWait`。`GrantMatched` 只表示当前 operation 可以跳过新的用户询问；Harness 仍通过前置 `OperationRegistry` 校验 operation 和参数，并使用原 durable ledger、claim 与 receipt 协议。`GrantRequired` 由现有 Gate/SessionStore 接口创建新的单次授权等待，不返回自由文本错误。

- [ ] **Step 3: 让 Gate 动作成为 operation**

Gate 分类、确认、拒绝和状态推进都通过 OperationExecutor；用户拒绝是 BusinessOutcome，不触发断路器。OperationExecutor 只能调用前置 SessionStore 的公开授权接口，不能在 `authorization.py`、Run Store 或 Policy 中保存第二份 confirmation、claim、continuation 或 receipt。

- [ ] **Step 4: 转绿**

```bash
cd backend && uv run pytest \
  tests/run/test_authorization_lifecycle.py \
  tests/harness/test_gate_rules.py \
  tests/api/test_chat_intent_phase.py -q
```

---

## Task 9: 覆盖 LLM、Store、File、Browser 和状态转换 operation

**Files:**

- Modify: `backend/career_os/platform/operation/catalog.py`
- Modify: `backend/career_os/platform/operation/adapters.py`
- Modify: `backend/career_os/agents/lc/client.py`
- Modify: `backend/career_os/agents/lc/coordinator_llm.py`
- Modify: `backend/career_os/agents/lc/worker_llm.py`
- Modify: `backend/career_os/platform/store/*.py`
- Modify: `backend/career_os/platform/market_research/{browser,boss,trends,extraction,synthesis,store,service}.py`
- Modify: relevant `backend/tests/**`

- [ ] **Step 1: 为每类基础设施逐个增加 Adapter 测试**

按以下顺序逐类做红 → 绿：

1. LiteLLM Provider；
2. Session/Profile/Task/Artifact/Run Store；
3. File read/write；
4. Browser 与外部页面；
5. Gate/阶段/任务状态转换；
6. Job 创建和正式结果发布。

每类覆盖已知领域错误、已知第三方异常和 unexpected exception。

- [ ] **Step 2: 把调用接缝接入 OperationExecutor**

只包装有业务意义的外部状态、流程决策和可独立失败动作；字符串格式化和纯内存映射不建立 operation。

外层 operation 调用子 operation 时，只有最内层副作用 operation 负责重试。

- [ ] **Step 3: 增加 operation catalog 完整性测试**

测试扫描已注册 Tool、Provider、Store 外部方法、Browser 行为和状态转换目录，验证每个都存在：

- operation type；
- Adapter；
- policy；
- purpose/criticality 合法组合。

- [ ] **Step 4: 转绿并跑各领域测试**

```bash
cd backend && uv run pytest \
  tests/operation/ \
  tests/store/ \
  tests/platform/ \
  tests/harness/ -m "not llm" -q
```

---

## Task 10: 加入隔离断路器并适配现有市场 Job Run

**Files:**

- Create: `backend/tests/run/test_market_job_adapter.py`
- Modify: `backend/career_os/platform/operation/policy.py`
- Modify: `backend/career_os/platform/operation/executor.py`
- Modify: `backend/career_os/platform/run/models.py`
- Modify: `backend/career_os/platform/run/engine.py`
- Modify: `backend/career_os/platform/market_research/models.py`
- Modify: `backend/career_os/platform/market_research/service.py`
- Modify: `backend/career_os/platform/market_research/runner.py`
- Modify: `backend/tests/platform/test_market_research_service_recovery.py`

- [ ] **Step 1: 写断路器隔离红灯测试**

验证：

- key 为 environment + external dependency + operation type；
- Provider、Store、Browser、File 可触发；
- invalid_html、input_required、policy_blocked、no_results、用户拒绝和 waiting_user 不触发；
- 一个 operation 熔断不关闭整个 Runtime；
- 断路器不跨 demo 环境。

- [ ] **Step 2: 实现 closed/open/half_open**

使用可注入 Clock。CircuitBreaker 只保护策略声明的外部依赖。

- [ ] **Step 3: 写市场 Job Adapter 红灯测试**

验证：

- `market.start_research` WorkerRun 成功后 Job 独立运行；
- Job 创建并持久化、Contract 产生 `JobAcceptedOutcome` 后，`market.start_research` Worker Run 与当前 Turn Plan 节点立即 success/finished，不等待 Job completed；
- 独立 Job Run 使用自己的 Job ExecutionPlan 推进 queued/running/waiting_user/终态，不能复用或继续推进启动它的当前 Turn 节点；
- Job 后续失败不回写 Worker；
- queued/running/waiting_user/completed/partial/failed 映射正确；
- 现有 continue/cancel 保持；
- 通用 Worker/Turn 没有新增 cancel；
- 重启后 Job interrupted 且不恢复。

- [ ] **Step 4: Adapter 现有市场状态**

保留 `ResearchStatus` 和现有领域 Store；在通用 Job Run seam 做双向映射，不立即删除市场状态模型。Adapter 必须显式区分当前 Turn 的启动节点与后台 Job ExecutionPlan：前者只验收 Job 已持久化并立即终结，后者独立等待市场任务终态。

- [ ] **Step 5: 转绿**

```bash
cd backend && uv run pytest \
  tests/run/test_market_job_adapter.py \
  tests/platform/test_market_research_service_recovery.py \
  tests/platform/test_market_research_rejection_audit.py \
  tests/platform/test_market_research_semantic_audit.py -q
```

---

## Task 11: 分离 SSE 执行状态和交付状态

**Files:**

- Create: `backend/tests/runtime/test_sse_delivery.py`
- Modify: `backend/career_os/runtime/sse.py`
- Modify: `backend/career_os/api/chat.py`
- Modify: `backend/career_os/platform/run/models.py`
- Modify: `backend/career_os/platform/run/store.py`

- [ ] **Step 1: 写 SSE 断连红灯测试**

验证：

- SSE establish、token send、done send 是独立可观察 operation；
- Turn success 后断连只把 delivery 标记 disconnected；
- 已产生副作用的 operation 不重新执行；
- 用户重新打开 Session 可读取已完成 Turn Result；
- Job 生命周期不受 SSE 连接影响；
- 内部 Failure/Trace 不流入最终文本 token。

- [ ] **Step 2: 实现 execution_status 与 delivery_status**

持久化：

```json
{
  "execution_status": "success",
  "delivery_status": "disconnected"
}
```

SSE Adapter 归一化发送错误，但不反向改写已完成 TurnRun。

- [ ] **Step 3: 转绿**

```bash
cd backend && uv run pytest \
  tests/runtime/test_sse_delivery.py \
  tests/api/ -q
```

---

## Task 12: 在干净环境沉淀当前 Bug 的最终系统级回归

**Files:**

- Create: `backend/tests/system/test_resume_failure_propagation.py`
- Create or Modify: `backend/tests/system/conftest.py`
- Reference: both 2026-07-23 specs and plans

**Scope:** 这是跨两份 plan 的最终验收任务，不另建第三份 plan。必须在 Task 1–11 全部完成后执行。

- [ ] **Step 1: 建立干净临时环境 fixture**

Fixture 必须：

- 使用 `tmp_path` 创建独立 data/output/logs 根目录；
- 创建全新 Session；
- 不读取旧 demo Session、Profile、Run、Trace、Failure 或 output；
- 注入确定性 WorkerRunner、Operation Adapter 和 Clock；
- 不依赖真实 LLM、Chrome 或网络；
- 测试结束后由 pytest 清理临时目录。

- [ ] **Step 2: 写原 Bug 红灯场景**

构造：

```text
Session phase = resume_optimize
Plan = resume.generate_optimized_resume → asset.register_outputs
resume has no known Tool Failure
resume returns empty delivery or semantic incomplete
```

在修复逻辑全部接通前，测试必须能复现旧行为：asset 被错误执行或最终回复落到资产角色声明。

- [ ] **Step 3: 断言完整系统结果**

最终必须同时验证：

1. resume WorkerRun 不为 success；
2. asset handler 从未执行；
3. asset 节点为 blocked_by_upstream；
4. asset WorkerRun 不存在；
5. TurnRun 为 failed 或由具体契约定义的 needs_additional_input；
6. 用户消息明确说明简历未生成；
7. 回复不包含“我的角色主要负责资产登记和复用建议”或同义角色推诿；
8. output 目录无新增 HTML；
9. outputs index 无新增登记；
10. Snapshot、Trace、Failure 使用同一组 Run/Plan/Invocation/operation id 关联；
11. 测试全程未调用真实 LLM。

- [ ] **Step 4: 增加部分成功对照场景**

验证：

```text
HTML 成功
→ asset 登记失败
→ HTML 保留
→ Turn partial_success
→ 用户看到“简历已生成，但产物登记未完成”
```

- [ ] **Step 5: 运行最终系统回归**

```bash
cd backend && uv run pytest tests/system/test_resume_failure_propagation.py -q
```

期望：全部通过。

---

## Task 13: 全量验收与范围审计

**Files:** all files changed by this plan

- [ ] **Step 1: 搜索绕过和旧错误猜测**

运行：

```bash
rg -n 'hasattr\\(.*code|except Exception.*return|last_worker_result.*synthesis|MAX_ITERATIONS|storage_retry_times|retry_times' backend/career_os
rg -n 'verified_outcomes: Mapping\\[str, Any\\]|invocation: BaseModel|WorkerInvocation.*Any' backend/career_os/platform/run backend/typecheck
```

逐项确认：

- 有业务意义的异常不再绕过 Adapter；
- retry 配置已进入 OperationPolicyRegistry，或属于明确的 Job 有效预算；
- 最终结果不再由 last Worker 决定；
- 安全迭代上限不会伪装成普通业务错误。
- Run 层没有擦除前置 Invocation、Outcome 和 ContractEvaluation 的静态类型。

- [ ] **Step 2: 跑分层定向测试**

```bash
cd backend && uv run pytest \
  tests/operation/ \
  tests/run/ \
  tests/runtime/ \
  tests/system/test_resume_failure_propagation.py -q
```

- [ ] **Step 3: 跑全部非 LLM 测试**

```bash
cd backend && uv run pytest tests/ -m "not llm" -q
uv run pyright
```

- [ ] **Step 4: 运行 LLM Judge 专项 Eval**

只在配置真实 LLM 的环境运行：

```bash
cd backend && uv run pytest tests/eval/ -m llm -v
```

该结果单独记录；不允许用 LLM Eval 通过替代确定性测试。

- [ ] **Step 5: 做格式、状态和持久化人工检查**

```bash
git diff --check
git status --short
```

确认：

- 未修改旧 demo 运行记录；
- 未恢复任何旧 Run/Job；
- 未触碰 `docs/assets/`；
- Snapshot 保存完整本地事实；
- 用户消息不包含内部错误码；
- 市场 continue/cancel 保持，通用取消未新增。

---

## Completion Criteria

1. 所有有业务意义的 operation 都通过 OperationExecutor。
2. OperationResult 明确区分 Success、BusinessOutcome、Failure。
3. 五类 Failure 和未知兜底有稳定 category/code。
4. 每个基础设施 seam 有自己的 Error Adapter。
5. OperationPolicyRegistry 是唯一策略事实来源，最具体优先与同层冲突均有测试。
6. 每条重试策略有独立 attempts 或 deadline，不存在统一最大一次规则。
7. 安全上限使用内部 `retry_safety_limit_exceeded`，用户只看到确定性目录消息。
8. outcome_unknown 先 probe；有副作用重试不重复产物。
9. Worker Run 使用运行完整性、operation 事实、前置 ContractEvaluation 与可选 Judge 三段式判断；确定性契约 Registry 保持唯一。
10. Judge 不覆盖硬失败，uncertain 阻止下游。
11. Turn 由 Plan 聚合，不由最后一个 Worker 决定。
12. Session Grant 跨 WorkerRun、不跨 Session，且只管理可复用约束；单次 operation 的 confirmation、claim、闭合 continuation 和 committed receipt 继续由前置 SessionStore 状态机唯一管理，三类 Gate 生命周期正确。
13. Snapshot、Trace、Failure、Emergency Sink 可关联且不用于恢复。
14. 市场 Job 适配通用语义并保留已有 continue/cancel。
15. SSE 执行与交付状态分离，断连不重放业务 operation。
16. 当前 Bug 的干净环境系统级回归和部分成功对照场景通过。
17. 全部非 LLM 测试与 `uv run pyright` 通过；LLM Eval 与确定性验收分层记录。
18. RunEngine、WorkerRunResult 和 Store 保持前置 plan 的闭合 Invocation/Outcome 与泛型 ContractEvaluation，不引入裸 `BaseModel`、`Any` 或字符串 Outcome 字典。
19. `claim_next()` 产生的 PlanDispatch 被 RunEngine 完整消费；WorkerRun、WorkerRunResult 与 PlanNodeResult 始终保持同一个 plan_id、node_id 和 worker_run_id，重复或错配启动被拒绝。
20. `OperationDefinition/OperationRegistry` 来自前置 plan 且保持唯一；OperationExecutor 只接收 OperationRequest 并调用 `OperationRegistry.resolve()` 返回的唯一 Definition/handler 绑定，Policy、Adapter catalog 和 Session Grant Registry 只引用它，不复制 operation 授权要求、durable ledger 绑定，也不允许调用方传入 handler。

## Suggested Commit

仅在用户另行要求创建 commit 时使用：

```text
feat(runtime): 建立全局失败与运行结果机制

- 统一 operation 结果、错误适配和确定性失败策略
- 复用前置确定性契约，增加 Worker、Turn、Job 三段式判定与依赖传播
- 实现幂等核对、持久化证据和用户错误消息目录
- 沉淀简历失败阻断资产执行的干净环境系统回归
```
