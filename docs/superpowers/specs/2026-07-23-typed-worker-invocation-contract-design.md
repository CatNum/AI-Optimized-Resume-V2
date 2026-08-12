# 强类型 WorkerInvocation 与结果契约设计规格

| 属性 | 内容 |
|------|------|
| 状态 | **已确认，待实施** |
| 版本 | **1.0.0** |
| 日期 | 2026-07-23 |
| 直接后续规格 | [ExecutionPlan 与受控执行生命周期](./2026-07-23-execution-plan-controlled-lifecycle-design.md) |
| 后续系统规格 | [全局失败机制](./2026-07-23-global-failure-mechanism-design.md) |
| 实施计划 | [强类型 WorkerInvocation 与结果契约 Implementation Plan](../plans/2026-07-23-typed-worker-invocation-contract.md) |
| 领域语言 | [CONTEXT.md](../../../CONTEXT.md) |

---

## 1. 背景与问题

当前 Coordinator 以字符串 Worker 队列表达动作，Runner 接收 `worker_id + task + context + prior_results`，调用职责、输入、Tool、Skill 和成功条件分散在 Prompt、配置、分支与自然语言结果中。它造成三个直接问题：

1. 调用前无法证明输入完整，也无法把某个动作限制在确定的 Pipeline 阶段；
2. Pydantic 输出可解析只证明结构正确，不能证明业务目标完成；
3. 下游容易从 `prior_results`、上下文或默认值猜测上游结果，导致上游失败后仍继续执行。

本规格先建立契约层，回答两个问题：Worker 本次究竟执行什么；什么确定性结果才允许被后续流程信任。本规格不切换聊天主链，仓库在该阶段结束时可以处于基础模块已验证、产品主链尚未迁移的中间状态。

## 2. 设计原则

1. **动态只停留在两个 seam**：LLM/JSON Proposal 解析 seam，以及 Worker 原始输出解析与 Invocation 配对 seam。通过 seam 后恢复为闭合具体类型。
2. **调用不可变**：`WorkerInvocation` 一经创建不得因 Session、Prompt 或注册表变化而改写。
3. **能力来自代码定义**：Tool、Skill、执行策略和 Success Contract 由代码 Registry 决定，LLM 只能提议 `worker_id + run_kind`。
4. **结构通过不等于成功**：只有确定性 Success Contract 能产生 `VerifiedOutcome`。
5. **业务值深冻结**：快照可到达的集合和子模型都不可原地修改，不能用 `dict[str, Any]` 逃生。
6. **接口就是测试面**：调用方和测试只通过 Registry、Contract、Skill Preloader 与统一 Runner seam，不断言私有字典或内部调用次数。
7. **不偷跑全局失败机制**：本规格不定义 Failure 分类、重试、Judge、Run Store、`partial_success` 或 `outcome_unknown`。

## 3. 目标与非目标

### 3.1 目标

- 为 7 类 Worker、15 个 Run Kind 建立具体 PreparedInput、Input、Invocation、WorkerStructuredOutput、VerifiedOutcome、Definition 与 Success Contract 类型。
- 使用 `WorkerInvocationRegistry` 作为 Invocation 创建唯一入口。
- 使用 `DeterministicSuccessContractRegistry` 作为确定性业务验收唯一入口。
- 让真实 ReAct Runner、确定性 Adapter、mock 与 stub 统一消费 `WorkerInvocation + WorkerRuntimeContext`。
- 在第一次 Worker LLM 调用前由 Harness 强制预加载全部 required Skill。
- 为授权暂停定义不可变 Runner 现场和闭合 continuation，但不实现跨请求持久化生命周期。
- 用 Pyright strict 验证 Invocation、结构化输出、Contract 与 Outcome 的静态关联。

### 3.2 非目标

- ExecutionPlan 节点、依赖、Outcome binding、调度、Plan claim 或 Plan 持久化；
- Coordinator 主链、delegate、Session 聚合、Gate、API、SSE 或前端切换；
- `OperationRegistry`、durable ledger、confirmation、claim、receipt 或授权恢复事务；
- Profile、Artifact、Task、市场方案、后台 Job 或产物索引持久化；
- 保持旧 Runner、旧页面和全部旧测试在本阶段可运行；
- `strategy.career_plan` 纯规划链；它在本规格、后续 ExecutionPlan 规格和全局失败机制完成后另行设计；
- 真实 LLM Eval；没有用户明确授权不得向外部 Provider 发送仓库业务内容。

## 4. 模块与依赖

本规格形成一个契约深模块，外部接口只有四组：

| 模块接口 | 含义 | 作用 |
|----------|------|------|
| `WorkerInvocationRegistry.prepare()/resolve()` | 调用准备与解析接口 | 把动态 Proposal 和具体输入校验为不可变 Invocation |
| `DeterministicSuccessContractRegistry.evaluate()` | 确定性结果验收接口 | 把配对后的具体 Worker 输出验收为命名 Outcome |
| `RequiredSkillPreloader.preload_required()` | 必需 Skill 预加载接口 | 在 Runner/LLM 前完成全部强制能力加载，失败时停止执行 |
| `run_worker_invocation()/resume_worker_invocation()` | 统一 Worker 运行接口 | 让 ReAct、deterministic、mock 和 stub 共享同一调用与恢复协议 |

第一阶段只定义 `HarnessOperationInvoker` 端口。该端口的含义是 Runner 请求 Harness 执行 operation 的接口，作用是保持调用方向稳定并允许测试使用 fake Adapter。第二阶段实现 `OperationRegistry`、授权与账本；全局失败机制再用唯一 `OperationExecutor` 包装同一个 Registry。

## 5. 核心模型

### 5.1 InvocationProposal

`InvocationProposal`（调用提议）是 Coordinator 对“应该执行什么”的最小动态输出：

```python
class InvocationProposal(BaseModel):
    worker_id: WorkerId
    run_kind: str
```

| 字段 | 含义 | 作用 |
|------|------|------|
| `worker_id` | Worker 标识 | 选择 identity、market、resume 等职责主体 |
| `run_kind` | 业务动作字符串 | 在 Proposal 解析 seam 选择已注册动作；未注册值明确拒绝 |

LLM 不得提供 Tool、Skill、依赖、成功契约、授权或失败策略。`run_kind` 在不可信输入侧保留为字符串；Registry 成功解析后必须恢复成带 `Literal worker_id + run_kind` 的具体类型。

### 5.2 WorkerRunDefinition

`WorkerRunDefinition`（Worker 动作定义）是某个 Run Kind 的代码事实源。每个具体子类必须展开 PreparedInput、Input、Invocation、WorkerStructuredOutput 与 Outcome 五个泛型参数，并把 `worker_id`、`run_kind` 收窄为 Literal。

本节使用的基础约束类型必须集中定义，不能各模型自行解释：`NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]`（非空字符串，用于身份与必填文本）；`NonNegativeInt = Annotated[int, Field(ge=0)]`（非负整数，用于迭代和版本）；`Sha256Hex = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]`（SHA-256 小写十六进制摘要，用于完整性校验）；`CanonicalJson = Annotated[str, AfterValidator(require_canonical_json)]`（规范 JSON 字符串，用于跨暂停边界稳定传输）。`require_canonical_json()`（规范 JSON 校验函数）负责重新解析并用唯一序列化器复算，输入不是规范形式时拒绝。

`ExecutionScope`（执行范围）是本阶段唯一公开的阶段范围类型：

```python
PipelinePhase = Literal[
    "explore", "market", "jd_analysis", "resume_strategy", "resume_optimize"
]

class ExecutionScope(FrozenModel):
    list_type: Literal["pipeline"] = "pipeline"
    phase: PipelinePhase
```

`list_type`（列表类型）固定为 `pipeline`，用于拒绝旧 `plan` 列表和复合阶段字符串；`phase`（流水线阶段）用于限制动作只能在登记阶段创建。

`OperationCapability`（操作能力）把 operation 名称和允许用途冻结在一起：

```python
OperationName = Literal[
    "profile_patch",
    "resume_read",
    "market_research",
    "write_resume_html",
    "register_outputs_index",
    "delete_output",
]

OperationPurpose = Literal[
    "persist_exploration_facts",
    "read_resume_source",
    "persist_capability_facts",
    "start_market_research",
    "persist_opportunity_assessment",
    "persist_jd_strategy",
    "write_optimized_resume",
    "persist_resume_optimization_facts",
    "register_verified_outputs",
    "delete_registered_output",
]

class OperationCapability(FrozenModel):
    operation_name: OperationName
    allowed_purposes: frozenset[OperationPurpose]
```

`operation_name`（操作名称）标识要调用的受控副作用能力；`allowed_purposes`（允许用途集合）限定该动作申请此 operation 时可声明的业务目的。`allowed_operations` 只能是从 `operation_capabilities` 投影名称得到的只读派生属性，不能作为第二份存储事实。用途只提供后续全局失败机制判定 `operation type + run_kind + purpose` 的稳定输入；`criticality`、重试、幂等和失败策略仍由后续 `OperationPolicyRegistry` 拥有。

| 字段 | 含义 | 作用 |
|------|------|------|
| `definition_id` | 稳定动作定义编号 | 供 Invocation、Trace 和测试引用 |
| `definition_revision` | 正整数定义修订号 | 任一输入/输出/控制语义变化时递增，阻止旧 Node Spec 静默采用新定义 |
| `definition_fingerprint` | 定义控制快照的 SHA-256 指纹 | 对规范序列化后的控制字段校验完整性，检测同修订号内容漂移 |
| `worker_id` | Worker 标识 Literal | 绑定职责主体并作为外层联合 discriminator |
| `run_kind` | 业务动作 Literal | 绑定具体输入、输出与契约 |
| `description` / `when_to_use` | 动作说明与适用场景 | 生成 Coordinator 可见的受限动作索引 |
| `allowed_scopes` | 允许的 `pipeline + phase` 集合 | 阻止越阶段调用；不接受复合阶段字符串或裸 `None` |
| `prepared_input_model` | 已有输入模型 | 描述动作准备阶段可冻结的具体事实 |
| `input_model` | 完整输入模型 | 描述 Runner 启动前必须满足的全部输入 |
| `invocation_model` | 具体 Invocation 类型 | 把动作与具体输入类型静态关联 |
| `structured_output_model` | Worker 输出类型 | 限定本 Invocation 可交给哪个 Contract 验收 |
| `operation_capabilities` | operation 名称与用途的冻结集合 | 形成模型可见 Tool 包络，并为 Harness 校验 `OperationRequest.purpose` 提供事实源 |
| `required_skills` | 必需 Skill 要求 | 由 Harness 在第一次 Worker LLM 调用前全部预加载 |
| `optional_skills` | 可选 Skill 要求 | 仅在 Definition 明确允许时由模型按需加载 |
| `execution_strategy` | `react` 或 `deterministic` | 选择唯一 Runner 实现，不允许运行时猜测 |
| `deterministic_adapter_id` | 确定性 Adapter 编号 | deterministic 动作绑定唯一 Adapter；ReAct 必须为空 |
| `emitted_outcomes` | 允许产生的具体 Outcome 类型 | 限定 Contract 返回的命名结果集合 |
| `success_contract_id` | 成功契约编号 | 提供稳定 Trace 身份 |
| `success_contract` | 泛型具体契约 | 静态关联 Invocation、Worker 输出与 Outcome |
| `semantic_judge_mode` | 后续 Judge 模式 | 只冻结未来策略元数据，本阶段不执行 Judge |

`AnyWorkerRunDefinition` 必须显式枚举 15 个具体 Definition 子类；不得退化为未参数化基类、`WorkerRunDefinition[Any, ...]` 或外部 JSON 配置。`config/workers.registry.json` 在第二阶段最终切换时删除，本阶段先停止把它当作新契约事实源。

`WorkerRunControlSnapshot`（Worker 动作控制快照）是 Definition 可跨阶段复制的稳定值对象：

```python
class WorkerRunControlSnapshot(FrozenModel):
    definition_id: NonEmptyStr
    definition_revision: int  # > 0
    definition_fingerprint: Sha256Hex
    worker_id: WorkerId
    run_kind: RunKind
    allowed_scopes: frozenset[ExecutionScope]
    operation_capabilities: tuple[OperationCapability, ...]
    required_skills: tuple[SkillRequirement, ...]
    optional_skills: tuple[SkillRequirement, ...]
    execution_strategy: Literal["react", "deterministic"]
    deterministic_adapter_id: NonEmptyStr | None
    success_contract_id: NonEmptyStr
    semantic_judge_mode: Literal["never", "when_needed", "required"]
```

该快照不包含 Python handler、模型类或可变 Registry 引用。`definition_fingerprint` 必须由单一规范序列化器对除指纹自身外的上述字段生成 SHA-256；相同语义产生相同字节，任何输入、输出或控制语义变化都必须同时递增 revision，revision 作为指纹输入会使 fingerprint 随之改变。

### 5.3 InvocationCreationRequest 与 WorkerInvocation

`InvocationPrepared[TPreparedInput]`（Invocation 准备结果）是 `WorkerInvocationRegistry.prepare()` 的成功分支，只保存已验证的 `scope`（执行范围）、具体 `prepared_input`（准备输入）和完整 `control_snapshot`（动作控制快照）。`prepared_input` 只包含当前已经存在的冻结业务事实，用于让第二阶段 Node Spec 保存依赖绑定前的输入；`control_snapshot` 用于让 blocked 节点在尚未创建 Invocation 时也固定 Definition 身份和能力。它不是 Invocation，不能交给 Runner。第二阶段必须把整个快照原样复制进 Node Spec 和创建请求，不能拆成独立字段后重新拼装。

`InvocationCreationRequest[TInput]`（Invocation 创建请求）是 `WorkerInvocationRegistry.resolve()` 的唯一输入包络。它携带节点身份、目标、完整业务输入和此前由 Registry 产生的整体控制快照；调用方不能逐项提供或改写 operation、Skill、执行策略、Contract 或 Judge 模式。

| 字段与类型 | 含义 | 作用 |
|------|------|------|
| `node_id: NonEmptyStr` | 计划节点编号 | 让第一阶段测试和第二阶段 Plan 使用同一创建 seam，并把 Invocation 绑定到唯一节点 |
| `goal: NonEmptyStr` | 本动作目标 | 向 Worker 说明本次业务目标，不替代 Definition 中的控制事实 |
| `inputs: TInput` | 完整具体输入 | 保存已经补齐全部依赖、可交给具体 `input_model` 重新校验的业务事实 |
| `control_snapshot: WorkerRunControlSnapshot` | Registry 生成的完整动作控制快照 | 选择 Definition 并证明 Node Spec 冻结的控制事实没有漂移 |

`WorkerPreparedInput` 与 `WorkerInput` 必须分别显式枚举 15 个具体 PreparedInput 和 Input 类型。`InvocationCreationRequest[WorkerInput]` 仍处于 Registry 解析 seam；Registry 必须先按 `control_snapshot.definition_id` 找到唯一具体 Definition，重新生成其控制快照并与请求快照做全字段相等校验，再用该 Definition 的 `input_model` 重新构造输入。定义不存在、revision/fingerprint 或任一控制字段不一致、输入类型与 Definition 不匹配、节点或目标为空时返回结构化拒绝，不创建 `invocation_id`。这样 Registry 变更不会让先前冻结的 Node Spec 静默获得新能力；需要采用新定义时必须重新 prepare 并创建新 Plan。`invocation_id`（调用编号）只能由 Registry 在全部校验通过后生成，调用方不能指定或复用。

`WorkerInvocation`（Worker 不可变调用快照）只在完整输入通过具体 `input_model` 校验后创建。它由先按 `worker_id`、再按 `run_kind` 判别的闭合联合组成。

| 字段 | 含义 | 作用 |
|------|------|------|
| `invocation_id` | 调用编号 | 关联本次调用、Runner 和 Trace |
| `node_id` | 预留的计划节点编号 | 让第二阶段可把调用绑定到 Plan；本阶段不实现 Plan |
| `definition_id` | 动作定义编号 | 证明调用采用哪个代码定义 |
| `definition_revision` / `definition_fingerprint` | 定义修订号与内容指纹 | 证明 Invocation 与此前冻结的 Node Spec 使用同一版控制事实 |
| `worker_id` / `run_kind` | 两级 Literal discriminator | 把调用缩窄到具体 Input 类型 |
| `allowed_scopes` | Definition 允许范围快照 | 保留 prepare 时校验所依据的范围集合，供 Trace 和后续一致性校验 |
| `goal` | 本动作目标 | 向模型说明任务，不替代控制字段 |
| `inputs` | 具体完整输入 | 保存 Runner 唯一可消费的业务事实快照 |
| `operation_capabilities` | operation 名称与用途包络快照 | 防止运行期间定义变化、越权 operation 或伪造 purpose；`allowed_operations` 由其派生 |
| `required_skills` / `optional_skills` | Skill 要求快照 | 固定必需与可选能力 |
| `execution_strategy` / `deterministic_adapter_id` | 执行实现快照 | 让 Runner Registry 只按冻结定义选择实现 |
| `success_contract_id` | 确定性契约编号 | 绑定输出验收规则 |
| `semantic_judge_mode` | 后续 Judge 模式 | 供全局失败机制消费，不在本阶段执行 |

Invocation 一经创建不得修改。用户改变参数或目标时必须创建新 Invocation，不能就地改写旧快照。

### 5.4 ContractEvaluation 与 VerifiedOutcome

`ContractEvaluation[TOutcome]`（确定性契约验收结果）使用 `satisfied` Literal discriminator 表达满足或不满足：

- `satisfied=True` 时必须含一个或多个允许的具体 `verified_outcomes`；
- `satisfied=False` 时 Outcome 必须为空，并提供稳定 `code + message + evidence_refs`；
- Schema 通过、Runner 正常结束或异步请求被接受都不能直接产生 Outcome。

`VerifiedOutcome`（已验证业务结果）是全部具体结果类型的闭合联合。它携带 `outcome_name`、契约编号、来源 Invocation 身份及具体 frozen 业务值，用于第二阶段的强类型依赖绑定和全局失败机制的 Run 判定。

确定性 Contract 接受验证依赖，不在内部创建文件系统、Store 或 Harness。本阶段测试使用本地/fake verifier Adapter；第二阶段接入真实 Store；全局失败机制改用 OperationResult 支持的 verifier Adapter。三者替换事实读取 Adapter，不复制契约规则。

静态与运行时职责必须区分：具体 `SuccessContract[TInvocation, TOutput, TOutcome]` handler 的三类配对由 Pyright strict 静态验证；公开 Registry 接收的是两个独立闭合联合，因此 Invocation 与 WorkerStructuredOutput 的跨动作错配由 `evaluate()` 在运行时返回结构化 contract violation，不能声称 Registry 调用点可由静态类型系统自动证明配对正确。

### 5.5 ProfilePatch 与产物结果

`ProfilePatch`（档案补丁）不能是任意 JSON，必须按 `patch_kind` 判别为以下 frozen 具体模型：

- `ExplorationProfilePatch`：修改职业初探事实；
- `ExperienceBankProfilePatch`：修改经历与能力证据；
- `OpportunityAssessmentProfilePatch`：记录 JD 机会判断；
- `JdStrategyProfilePatch`：记录投递策略事实；
- `ResumeOptimizationProfilePatch`：记录简历优化事实。

每个 Run Kind 只能输出允许的补丁变体。第一阶段只定义并验证补丁和产物结果；Profile、Artifact、OutputIndex 的实际持久化属于第二阶段。

### 5.6 深冻结不变量

- 有序集合使用 `tuple`，无序集合使用 `frozenset`；
- 结构化业务值使用 `frozen=True, extra="forbid"` 的具体子模型；
- 不得在 PreparedInput、Input、WorkerStructuredOutput、VerifiedOutcome 或暂停载荷中保留 `list`、`dict`、`set`、可变子模型或 `Any`；
- Registry 必须重新校验并创建新模型，不能浅复制调用方可变对象；
- Contract 和后续 binder 必须返回新对象，不得修改输入或 Outcome；
- Session/request 源对象变化不得改写既有 Invocation、Outcome 或暂停现场。

### 5.7 WorkerExecutionResult 与暂停载荷

本阶段使用临时闭合联合 `WorkerExecutionResult`（Worker 执行结果）：

| 分支 | 含义 | 作用 |
|------|------|------|
| `completed` | Runner 正常结束并解析了具体结构化输出 | 交给确定性 Contract 验收，不能直接视为 success |
| `failed` | 预检、LLM、Tool、循环或输出解析失败 | 保留稳定 code/message，阻止伪造成功；不做 Failure 分类 |
| `accepted_async` | `market.start_research` 后台启动被接受 | 仍需 Contract 验证 Job 已持久化且 Runner 已接受 |
| `awaiting_authorization` | 当前 operation 需要用户授权 | 携带不可变运行现场与 continuation，不形成终态 Outcome |

暂停/恢复载荷必须使用下列精确冻结模型，不能用任意消息字典或可选字段堆叠出隐式状态：

| 模型 | 精确字段与类型 | 含义与作用 |
|---|---|---|
| `PendingOperationCall` | `operation_call_id: NonEmptyStr`；`operation_name: OperationName`；`canonical_arguments_json: CanonicalJson`；`arguments_hash: Sha256Hex` | 保存一个尚未提交的 operation 调用；ReAct 中 `operation_call_id` 必须等于原始 `tool_call_id`，规范参数和摘要用于阻止恢复时改参 |
| `WorkerMessageSnapshot` | `role: Literal["system", "user", "assistant", "tool"]`；`content: str | None`；`tool_call_id: NonEmptyStr | None`；`tool_calls: tuple[PendingOperationCall, ...]` | 保存恢复所需的最小消息；assistant 才能携带 `tool_calls`，tool 消息必须携带 `tool_call_id`，其他组合拒绝 |
| `ReActOperationContinuation` | `continuation_kind: Literal["react"]`；`messages: tuple[WorkerMessageSnapshot, ...]`；`completed_iterations: NonNegativeInt`；`pending_call: PendingOperationCall`；`remaining_calls: tuple[PendingOperationCall, ...]`；`resume_action: Literal["append_committed_tool_result"]` | 冻结最近 assistant Tool Call 批次、当前待提交调用和其后未完成调用的原始顺序 |
| `DeterministicOperationContinuation` | `continuation_kind: Literal["deterministic"]`；`deterministic_adapter_id: NonEmptyStr`；`operation_call_id: NonEmptyStr`；`operation_name: OperationName`；`canonical_arguments_json: CanonicalJson`；`arguments_hash: Sha256Hex`；`completed_steps: NonNegativeInt`；`resume_action: Literal["complete_from_committed_result"]` | 冻结唯一 Adapter、待提交调用及恢复入口，避免恢复时重选实现 |
| `SuspendedWorkerRun` | `invocation: WorkerInvocation`；`continuation: OperationContinuation`；`suspended_at: datetime` | 保存完整 Invocation 和策略 continuation；本阶段不伪造尚不存在的 `plan_id`、`worker_run_id` 或 Session 持久化身份 |
| `CommittedOperationResult` | `operation_call_id: NonEmptyStr`；`operation_name: OperationName`；`arguments_hash: Sha256Hex`；`canonical_result_json: CanonicalJson`；`result_hash: Sha256Hex` | 作为 Runner 恢复的只读已提交结果；operation-specific Adapter 再把规范 JSON 解析成具体结果类型 |

`OperationContinuation`（操作继续位置）必须定义为以 `continuation_kind` 判别的 `ReActOperationContinuation | DeterministicOperationContinuation` 闭合联合。`CanonicalJson`（规范 JSON 字符串）必须由单一序列化器执行解析、排序和重新序列化，禁止 NaN、重复键和实现相关格式；`Sha256Hex` 是相应规范 UTF-8 字节的 SHA-256。恢复前必须重新计算参数与结果摘要，并验证 committed result 的 call id、operation name、arguments hash 与 ReAct 的 `pending_call` 或 deterministic continuation 的对应字段全部一致。

ReAct 的 `pending_call + remaining_calls` 必须与最后一个未闭合 assistant 消息中的 `tool_calls` 有序后缀完全一致；已存在的 tool 消息必须与更早 call id 一一对应。deterministic continuation 的 Adapter ID 必须等于 Invocation 的冻结 Adapter ID。任何消息角色形状、调用顺序、摘要或身份不一致都结构化拒绝，不能尝试修复或重新调用 operation。

`CommittedOperationResult` 不携带 Plan、节点、Worker Run 或 Session 持久化身份。第二阶段的 `CommittedOperationReceipt` 在完成全部外层身份、授权和账本校验后投影出该对象交给 Runner，因此 Runner seam 不需要因持久化状态机接入而改变。

第一阶段只定义、冻结、序列化和在进程内恢复这些载荷，不创建 confirmation、claim、receipt 或 Session 快照。第二阶段负责持久化生命周期；全局失败机制用最终 `WorkerRunResult` 替换临时联合，但复用 Invocation、Outcome、Contract 和暂停身份。

## 6. 第一版 Run Kind 目录

本节的控制矩阵与类型矩阵共同构成 15 个动作的唯一目录：控制矩阵固定 operation、Skill、执行策略、Adapter 和后续 Judge 策略，类型矩阵固定范围、输入、输出、Outcome 与确定性契约。实施者不得在两个矩阵之外为某个动作临时补控制值或业务字段。

### 6.1 动作控制矩阵

`operation_capabilities`（操作能力集合）表示模型或确定性 Adapter 可以申请的 operation 及其合法 purpose 上限，不表示每项都必须执行；空集合是合法值。表中 `operation(purpose)` 表示一个 `OperationCapability`。第一版 `OperationPurpose` 是表内 purpose 字符串的闭合 Literal 联合，新增值必须先修改本规格、Definition 和测试。`required_skills`（必需 Skill 集合）必须在 Runner 前全部预加载；`optional_skills`（可选 Skill 集合）只有明确登记后才允许模型按需加载。第一版所有动作的 `optional_skills=()`，不得因集合为空而自动暴露 `load_skill`。

| Worker.Run Kind | `operation_capabilities` | `required_skills` | `optional_skills` | `execution_strategy` / `deterministic_adapter_id` | `semantic_judge_mode` |
|---|---|---|---|---|---|
| `identity.exploration_first` | `profile_patch(persist_exploration_facts)` | `career-inner-exploration(exploration_first)` | `()` | `react` / `None` | `when_needed` |
| `identity.exploration_revisit` | `profile_patch(persist_exploration_facts)` | `career-inner-exploration(exploration_review)` | `()` | `react` / `None` | `when_needed` |
| `capability.exploration_first` | `resume_read(read_resume_source)`、`profile_patch(persist_capability_facts)` | `career-inner-exploration(capability_bank)` | `()` | `react` / `None` | `when_needed` |
| `capability.exploration_revisit` | `resume_read(read_resume_source)`、`profile_patch(persist_capability_facts)` | `career-inner-exploration(capability_bank)` | `()` | `react` / `None` | `when_needed` |
| `capability.jd_bank_deep_dive` | `resume_read(read_resume_source)`、`profile_patch(persist_capability_facts)` | `career-inner-exploration(capability_bank)` | `()` | `react` / `None` | `when_needed` |
| `market.propose_plan` | `()` | `()` | `()` | `react` / `None` | `when_needed` |
| `market.revise_plan` | `()` | `()` | `()` | `react` / `None` | `when_needed` |
| `market.start_research` | `market_research(start_market_research)` | `()` | `()` | `deterministic` / `market.start_research` | `never` |
| `opportunity.evaluate` | `profile_patch(persist_opportunity_assessment)` | `()` | `()` | `react` / `None` | `when_needed` |
| `strategy.jd_application` | `profile_patch(persist_jd_strategy)` | `career-jd-alignment(jd_alignment)` | `()` | `react` / `None` | `when_needed` |
| `resume.collect_optimization_levels` | `()` | `()` | `()` | `deterministic` / `resume.collect_optimization_levels` | `never` |
| `resume.generate_optimized_resume` | `resume_read(read_resume_source)`、`write_resume_html(write_optimized_resume)`、`profile_patch(persist_resume_optimization_facts)` | `resume-module-optimize(None)` | `()` | `react` / `None` | `when_needed` |
| `asset.reuse_outputs` | `()` | `()` | `()` | `react` / `None` | `when_needed` |
| `asset.register_outputs` | `register_outputs_index(register_verified_outputs)` | `()` | `()` | `deterministic` / `asset.register_outputs` | `never` |
| `asset.delete_output` | `delete_output(delete_registered_output)` | `()` | `()` | `deterministic` / `asset.delete_output` | `never` |

Harness 接到 `OperationRequest`（操作请求）时必须校验其 `operation_name`（操作名称）存在于当前 Invocation 的 `operation_capabilities`，且 `purpose`（业务用途）属于该 capability 的 `allowed_purposes`；非法组合在执行副作用前拒绝。这里不决定该用途是 critical 还是 optional，也不决定失败后重试或继续，避免抢占全局失败机制的策略职责。

`semantic_judge_mode`（语义 Judge 模式）在第一阶段只冻结策略值，不执行 Judge：`never` 表示后续全局失败机制不得调用 Judge，`when_needed` 表示确定性规则不足以判断目标完成度时才允许调用，`required` 保留给未来经单独确认的新动作，第一版 15 个动作不使用。Judge 不能覆盖 operation 失败或确定性 Contract 不满足。

`resume-module-optimize(None)` 表示该 Skill 没有 mode。它必须在 front matter 以顶层 `allowed_workers: [resume]` 明确授权 resume Worker；`SkillRegistry` 必须支持并校验“顶层 `allowed_workers` + 无 modes”的单模式 Skill。带 `modes` 的 Skill 继续按具体 mode 的 `allowed_workers` 授权，两种声明方式不能同时出现。这样 `RequiredSkillPreloader` 可以使用结构化 `SkillRequirement(name="resume-module-optimize", mode=None)`，不会依赖正文描述或绕过 Worker 授权。

### 6.2 具体类型与契约矩阵

引用字段使用 frozen 具体引用模型，所有 `str` 身份和业务文本必须去除首尾空白后非空，有序集合只使用 tuple。除 `asset.register_outputs` 外，同一行的 PreparedInput 与 Input 字段相同，但仍须定义为两个不同的具体类型，防止准备态被误交给 Runner。

| Worker.Run Kind | `ExecutionScope` | PreparedInput / Input 的精确字段 | WorkerStructuredOutput 的精确字段 | VerifiedOutcome 与确定性契约 |
|---|---|---|---|---|
| `identity.exploration_first` | `pipeline/explore` | `intake: ExplorationIntake`；`conversation_window: tuple[ConversationMessageSnapshot, ...]`；`profile_summary: ProfileSummarySnapshot | None` | `draft: ExplorationDraft`；`profile_patch: ExplorationProfilePatch | None` | `ExplorationDraftOutcome(value: ExplorationDraft)`；身份假设、证据和待确认问题均非空 |
| `identity.exploration_revisit` | `pipeline/explore` | `exploration_ref: ArtifactRef`；`change_reason: str`；`conversation_window: tuple[ConversationMessageSnapshot, ...]` | `draft: ExplorationDraft`；`changed_sections: tuple[ExplorationSection, ...]`；`profile_patch: ExplorationProfilePatch | None` | `ExplorationDraftOutcome(value: ExplorationDraft)`；版本匹配且 changed sections 非空 |
| `capability.exploration_first` | `pipeline/explore` | `resume_ref: ArtifactRef | None`；`intake: ExplorationIntake`；`existing_facts: tuple[CapabilityFact, ...]` | `bank_delta: ExperienceBankDelta`；`profile_patch: ExperienceBankProfilePatch | None` | `BankDeltaOutcome(value: ExperienceBankDelta)`；至少一条有证据来源的新增或修订事实 |
| `capability.exploration_revisit` | `pipeline/explore` | `experience_bank_ref: ArtifactRef`；`change_reason: str`；`resume_ref: ArtifactRef | None` | `bank_delta: ExperienceBankDelta`；`profile_patch: ExperienceBankProfilePatch | None` | `BankDeltaOutcome(value: ExperienceBankDelta)`；bank 版本匹配且 delta 非空 |
| `capability.jd_bank_deep_dive` | `pipeline/jd_analysis` | `opportunity_ref: ArtifactRef`；`experience_bank_ref: ArtifactRef`；`resume_ref: ArtifactRef | None` | `bank_delta: ExperienceBankDelta`；`coverage: RequirementCoverage`；`profile_patch: ExperienceBankProfilePatch | None` | `BankDeltaOutcome(value: ExperienceBankDelta)`；至少补齐一条与 opportunity requirement 关联的证据 |
| `market.propose_plan` | `pipeline/market` | `exploration_ref: ArtifactRef`；`experience_bank_ref: ArtifactRef`；`research_goal: str` | `proposal: MarketResearchPlanDraft` | `MarketPlanProposalOutcome(value: MarketResearchPlanDraft)`；步骤、数据源、地域和时间范围完整，尚未 confirmed |
| `market.revise_plan` | `pipeline/market` | `current_plan_ref: ArtifactRef`；`revision_request: str`；`expected_version: int` | `proposal: MarketResearchPlanDraft`；`supersedes_version: int` | `MarketPlanProposalOutcome(value: MarketResearchPlanDraft)`；旧版本匹配，新版本严格递增 |
| `market.start_research` | `pipeline/market` | `confirmation: MarketPlanConfirmationRef` | `job_id: str`；`plan_id: str`；`confirmation_id: str`；`accepted_at: datetime` | `JobAcceptedOutcome(value: AcceptedMarketJobRef)`；确认、Plan、Job 身份一致，Job 已持久化且 Runner 接受启动 |
| `opportunity.evaluate` | `pipeline/jd_analysis` | `market_result_ref: ArtifactRef`；`jd_fingerprint: str`；`jd_snapshot: JobDescriptionSnapshot`；`profile_facts: ProfileFactsSnapshot` | `assessment: OpportunityAssessment`；`profile_patch: OpportunityAssessmentProfilePatch | None` | `OpportunityAssessmentOutcome(value: OpportunityAssessment)`；市场结果已确认且覆盖同一 JD 指纹 |
| `strategy.jd_application` | `pipeline/resume_strategy` | `opportunity_ref: ArtifactRef`；`market_result_ref: ArtifactRef`；`profile_facts: ProfileFactsSnapshot` | `strategy: StrategyArtifact`；`optimize_transition: OptimizeTransition | None`；`profile_patch: JdStrategyProfilePatch | None` | `StrategyArtifactOutcome(value: StrategyArtifact)`、`OptimizeTransitionOutcome(value: OptimizeTransition)`；引用同一机会且转移前置完整 |
| `resume.collect_optimization_levels` | `pipeline/resume_optimize` | `available_levels: tuple[OptimizationLevel, ...]`；`strategy_ref: ArtifactRef`；`current_selection: tuple[OptimizationLevel, ...]` | `levels: tuple[OptimizationLevel, ...]`；`prompt: str` | `OptimizationLevelRequestOutcome(value: OptimizationLevelRequest)`；档位非空、来自目录且无默认伪造 |
| `resume.generate_optimized_resume` | `pipeline/resume_optimize` | `levels: tuple[OptimizationLevel, ...]`；`strategy_ref: ArtifactRef`；`resume_ref: ArtifactRef`；`capability_facts: ProfileFactsSnapshot`；`output_root: OutputRootRef` | `html_deliveries: tuple[HtmlDeliveryCandidate, ...]`；`profile_patch: ResumeOptimizationProfilePatch | None` | `VerifiedHtmlDeliveriesOutcome(value: tuple[VerifiedHtmlDelivery, ...])`；数量/档位匹配、规范路径在 output root 内且 HTML 完整 |
| `asset.reuse_outputs` | `pipeline/resume_optimize` | `candidates: tuple[RegisteredDeliveryRef, ...]`；`current_goal: str` | `recommendation: ReuseRecommendation` | `ReuseRecommendationOutcome(value: ReuseRecommendation, eligible_candidates: tuple[RegisteredDeliveryRef, ...])`；候选来自 Invocation，理由非空，不含 Gate 或默认选择 |
| `asset.register_outputs` | `pipeline/resume_optimize` | `PreparedInput`: `session_id: str`；`output_root: OutputRootRef`；`strategy_ref: ArtifactRef`；`expected_index_version: int`。`Input` 另加 `deliveries: tuple[VerifiedHtmlDelivery, ...]` | `registered: tuple[RegisteredDeliveryRef, ...]`；`new_index_version: int` | `RegisteredDeliveriesOutcome(value: tuple[RegisteredDeliveryRef, ...])`；delivery 非空、一一对应、稳定 output_id、版本 +1 |
| `asset.delete_output` | `pipeline/resume_optimize` | `output_id: str`；`expected_index_version: int` | `deleted_output_id: str`；`new_index_version: int` | `DeletedOutputOutcome(value: DeletedOutputRef)`；授权和 receipt 身份一致、目标存在、删除后不可解析、版本 +1 |

`WorkerPreparedInput`（全部准备输入）和 `WorkerInput`（全部完整输入）必须按下列成员显式闭合，不能用公共基类代替联合成员：

```python
WorkerPreparedInput = (
    ExplorationFirstPreparedInput
    | ExplorationRevisitPreparedInput
    | CapabilityExplorationPreparedInput
    | CapabilityRevisitPreparedInput
    | JdBankDeepDivePreparedInput
    | MarketPlanProposalPreparedInput
    | MarketPlanRevisionPreparedInput
    | MarketResearchStartPreparedInput
    | OpportunityEvaluationPreparedInput
    | JdApplicationStrategyPreparedInput
    | CollectOptimizationLevelsPreparedInput
    | GenerateOptimizedResumePreparedInput
    | ReuseOutputsPreparedInput
    | RegisterOutputsPreparedInput
    | DeleteOutputPreparedInput
)

WorkerInput = (
    ExplorationFirstInput
    | ExplorationRevisitInput
    | CapabilityExplorationInput
    | CapabilityRevisitInput
    | JdBankDeepDiveInput
    | MarketPlanProposalInput
    | MarketPlanRevisionInput
    | MarketResearchStartInput
    | OpportunityEvaluationInput
    | JdApplicationStrategyInput
    | CollectOptimizationLevelsInput
    | GenerateOptimizedResumeInput
    | ReuseOutputsInput
    | RegisterOutputsInput
    | DeleteOutputInput
)
```

所有 version 字段必须是非负整数；revision 动作产生的新版本必须严格大于 expected version，登记和删除动作的 new index version 必须恰好等于 expected index version + 1。

补充约束：

- `market.start_research` 的当前 Worker Run 只在 Contract 验证后台 Job 已持久化且启动已被接受后立即成功；不等待 Job 终态。
- `resume.generate_optimized_resume` 没有档位时不得启动。
- `asset.reuse_outputs` 的 Worker、Contract 和 mock 不创建 Gate；第二阶段由 Harness 从已验证 Outcome 创建 `reuse_confirm`。
- `asset.register_outputs` 的 `deliveries` 只来自 `VerifiedHtmlDeliveriesOutcome`；不得从摘要、上下文或默认路径补齐。
- `strategy.career_plan` 不进入本期闭合联合、Prompt、Skill、Contract 或启动检查。

## 7. Registry 与启动完整性

`WorkerInvocationRegistry` 的公开接口固定为：

```python
class WorkerInvocationRegistry:
    def prepare(
        self,
        proposal: InvocationProposal,
        *,
        scope: ExecutionScope,
        prepared_input: WorkerPreparedInput,
    ) -> InvocationPreparationResult: ...

    def resolve(
        self,
        request: InvocationCreationRequest[WorkerInput],
    ) -> InvocationResolution: ...
```

`prepare()`（准备调用）接收 Proposal、已经由 Harness 验证的执行范围和一个具体 `WorkerPreparedInput`。Registry 校验 Proposal、scope 与 PreparedInput 模型属于同一 Definition，并通过该 Definition 的 `prepared_input_model` 重新构造、深冻结输入；从 Session/Store 事实投影出 PreparedInput 是第二阶段的职责，本阶段不再引入含义重叠的准备事实联合。成功返回 `InvocationPrepared(scope, prepared_input, control_snapshot)`；失败返回 `InvocationRejected`。`InvocationPreparationResult` 是 `InvocationPrepared[WorkerPreparedInput] | InvocationRejected` 的闭合联合。它不读取 Store、不推进阶段、不创建 Plan。

`resolve(request)`（解析并创建调用）接收冻结的 `InvocationCreationRequest[WorkerInput]`，按 `request.control_snapshot.definition_id` 找到唯一具体 Definition，重新生成并全字段比对控制快照，再校验 `inputs`、生成 `invocation_id`，最后把请求中的快照原样复制进唯一不可变 Invocation。第一阶段测试可以直接使用 `prepare()` 返回的快照构造请求；第二阶段 Plan binder 先产生完整具体 Input，再把 Node Spec 的 `node_id + goal + control_snapshot` 与该 Input 组合为同一个创建请求。调用方不能提交 `invocation_id`，也不能拆散或改写控制快照。任何未知定义、快照漂移、身份为空、类型错配或输入缺失都返回 `InvocationRejected(code, message, evidence_refs)`；成功返回 `InvocationResolved(invocation)`，二者组成闭合 `InvocationResolution`，不产生部分 Invocation。

`DeterministicSuccessContractRegistry.evaluate()`（执行确定性成功验收）按 Invocation 的具体类型解析唯一 Contract，验证配对后的 WorkerStructuredOutput 和外部事实 Adapter，返回泛型 `ContractEvaluation[TOutcome]`。

启动完整性检查必须验证：

- 15 个 `worker_id + run_kind` 组合完整且唯一；
- Definition、Invocation、输出、Outcome、Contract 和 Prompt 引用完整；
- Skill 名称/mode 组合合法，required 与 optional 不冲突；
- deterministic Definition 绑定唯一 Adapter，ReAct Definition 不带 Adapter 编号；
- 每个 Definition 的 `definition_revision` 为正整数，规范控制字段重新计算得到的 fingerprint 与声明值一致且身份唯一；
- 每个非空 `operation_capabilities` 的 operation 名称合法且不重复、purpose 集合非空且只含第 6.1 节登记值；空 capability 集合合法；第二阶段接入 OperationRegistry 后再验证全部名称和 purpose 可解析；
- 具体 Definition 联合、Invocation 联合、WorkerStructuredOutput 联合和 VerifiedOutcome 联合覆盖一致。

## 8. Prompt、Skill 与 Runner

### 8.1 Prompt 分层

- `invocation_system.md` 保存 Worker 长期职责、边界和输出纪律；
- `runs/<run_kind>.md` 保存当前动作说明；
- Invocation 的目标、输入和能力包络在运行时注入；
- required Skill 正文由 Harness 预加载后注入，不作为模型 Tool；
- Tool Schema 只暴露当前 Invocation 允许的 operation；允许表示可以自主选择，不表示必须按固定顺序调用。

基础 Prompt 和业务 `SKILL.md` 必须删除 required Skill 重复加载、Run Kind/mode 重复猜测、跨 Worker 职责与未授权 Tool 规则。清理不能取消模型在已授权 Tool/optional Skill 包络内的自主判断。

### 8.2 RequiredSkillPreloader

`preload_required(invocation)`（预加载必需 Skill）按 `SkillRequirement(name, mode)` 顺序加载全部 required Skill：

- 全部成功才返回不可变 bundles；
- 任一失败返回 `required_skill_preload_failed`，bundles 为空，但 attempts 保留此前成功项的内容哈希和最终错误；
- 失败时不得调用 Runner、LLM、业务 Tool 或产生 VerifiedOutcome；
- optional Skill 只有 Definition 显式允许 `load_skill` 时才能在授权集合内按需加载。

### 8.3 WorkerRuntimeContext

`WorkerRuntimeContext`（Worker 运行上下文）只包含：Session 身份与修订、Trace 端口、`HarnessOperationInvoker`、已加载 Skill bundle，以及恢复当前 Invocation 所需的最小运行依赖。它不包含完整 `session_state`、任意业务字典、`prior_results` 或可从 Invocation 之外读取的业务事实。

### 8.4 统一 Runner

`run_worker_invocation(invocation, runtime_context)`（运行 Worker 调用）只消费完整 Invocation 与窄运行上下文。`resume_worker_invocation(suspended_run, committed_result, runtime_context)`（恢复 Worker 调用）从相同身份和确定性 continuation 继续，其中 `committed_result` 是已经通过外层校验的 `CommittedOperationResult`；第一阶段使用进程内 fake 验证恢复，不持久化 receipt。

恢复必须满足：

- 不重新调用 Coordinator、重新物化 Invocation 或重选 Adapter；
- 不重新生成、重排或重复执行已经冻结的 Tool Call；
- ReAct 分支为每个 Tool Call 补齐匹配 tool message 后才进入下一次模型迭代；
- deterministic 分支只调用原 Adapter 的 `complete_from_committed_result()`，该接口不能访问副作用执行端口；
- mock/stub 不补默认档位、Tool 参数、Outcome 或下游产物。

## 9. 测试 seam

| seam | 必须验证的行为 |
|------|----------------|
| `WorkerInvocationRegistry.prepare()/resolve()` | 动态 Proposal 如何变成带完整控制快照的 `InvocationPrepared`，创建请求如何复核同一快照并形成具体 Invocation；范围、快照漂移、身份、类型与深冻结错误如何拒绝 |
| `DeterministicSuccessContractRegistry.evaluate()` | 结构化输出如何验收并形成可信命名 Outcome；不满足时 Outcome 为空 |
| `RequiredSkillPreloader.preload_required()` | required Skill 是否在 Runner/LLM 前全部加载；失败是否 fail-fast 且证据完整 |
| `run_worker_invocation()` | ReAct/deterministic/mock 是否只消费 Invocation 和窄 Context |
| `resume_worker_invocation()` | 暂停现场是否保持身份和顺序；恢复是否不重放 operation 或 Tool Call |
| `uv run pyright` | 两级 discriminator、五泛型 Definition、输出配对、Contract 和 Outcome 是否端到端缩窄 |

测试不建立仅供测试使用的公开方法，不断言私有 Registry 字典或内部调用次数。旧浅模块测试在新接口测试覆盖后删除或重写。

## 10. 验收标准

1. 15 个 Run Kind 都有具体 PreparedInput、Input、Invocation、WorkerStructuredOutput、VerifiedOutcome、Definition 与 Contract 类型。
2. `AnyWorkerRunDefinition`、`WorkerInvocation`、`WorkerStructuredOutput` 和 `VerifiedOutcome` 是显式闭合联合，无裸 `BaseModel`、`Any` 或动态 Outcome 字典。
3. Proposal 和原始 Worker 输出是仅有的动态 seam；通过 seam 后恢复成具体类型。
4. Invocation、Outcome、ProfilePatch 和暂停载荷满足深冻结不变量。
5. `WorkerInvocationRegistry` 是 Definition 解析和 Invocation 创建的唯一事实源；`DeterministicSuccessContractRegistry` 是 Contract 解析与验收的唯一事实源，两者不互相复制目录。
6. 所有 15 个确定性 Contract 都只能从配对后的输出与验证事实产生 Outcome。
7. 空或无效 HTML 不能产生 `VerifiedHtmlDeliveriesOutcome`。
8. Required Skill 在第一次 Worker LLM 调用前全部预加载；失败时不启动执行。
9. 真实 ReAct、deterministic、mock 与 stub 使用相同 Runner seam，且暂停/恢复不重放调用。
10. Prompt 和 Skill 不再重复猜测控制事实，也不把允许 Tool 固化为必执行序列。
11. 定向 Registry、Contract、Skill、Runner 测试与 Pyright 通过；失败、跳过或未执行项如实记录。
12. 本阶段不声称聊天主链、API、前端或完整产品已迁移，不要求全部旧测试通过。
13. 没有实现 Failure 分类、重试、Judge、Run Store、最终 Run 聚合、OperationRegistry 或授权持久化。
14. `strategy.career_plan` 不存在于闭合目录；未保留 legacy Adapter 或通用 fallback。
15. 15 个 Definition 的 operation capability、purpose、required/optional Skill、执行策略、Adapter 和 Judge 模式与第 6.1 节控制矩阵逐行一致；mode-less resume Skill 使用显式顶层 Worker 授权。
16. `resolve()` 只接受冻结的 `InvocationCreationRequest`，复核由 `prepare()` 生成并经 Node Spec 原样传递的完整控制快照，再由 Registry 生成 `invocation_id`；第一阶段测试与第二阶段 Plan 不使用不同创建 seam。
17. 暂停载荷使用第 5.7 节的精确闭合模型，规范 JSON、摘要、消息角色、调用身份和未完成调用顺序任一不一致都不能恢复。

## 11. 后续依赖

ExecutionPlan 与受控执行生命周期规格直接消费本规格提供的：

- 15 个具体 Definition、PreparedInput、Input、`WorkerRunControlSnapshot` 与 Invocation；
- `WorkerInvocationRegistry`；
- `WorkerStructuredOutput` 与闭合 `VerifiedOutcome`；
- `DeterministicSuccessContractRegistry` 与泛型 `ContractEvaluation[TOutcome]`；
- Required Skill Preloader、统一 Runner、暂停现场与 continuation；
- `HarnessOperationInvoker` 端口。

全局失败机制通过第二阶段传递依赖本规格。它复用 Invocation 冻结的 `operation_capabilities` 取得稳定的 operation purpose，再由自己的 `OperationPolicyRegistry` 决定 criticality、重试、幂等和失败语义；它可以用最终 `WorkerRunResult` 替换临时 `WorkerExecutionResult`，但不得复制 Invocation/Outcome 联合、确定性 Contract Registry 或重新从原始输出提取 Outcome。
