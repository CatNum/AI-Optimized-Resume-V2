# 强类型 WorkerInvocation 与结果契约 Implementation Plan（暂不实现）

> **状态：暂不实现。** 本 Plan 仅保留历史实施讨论，不作为当前版本的执行清单。未经重新评审和用户明确确认，不得按本文任务修改代码。

**Goal:** 为全部 15 个 Run Kind 建立不可变 `WorkerInvocation`、闭合业务输出和确定性 Success Contract，并统一 required Skill 预加载与 Worker Runner seam。

**Architecture:** `WorkerInvocationRegistry` 是 Definition 解析与 Invocation 创建的深模块；`DeterministicSuccessContractRegistry` 是业务结果验收的深模块；`RequiredSkillPreloader` 在 Runner 前强制加载必需 Skill；统一 Runner 只消费 `WorkerInvocation + WorkerRuntimeContext`。真实 operation 执行通过注入的 `HarnessOperationInvoker` 端口，OperationRegistry、授权和持久化由第二阶段实现。

**Design SSOT:** `../specs/2026-07-23-typed-worker-invocation-contract-design-暂不实现.md`

**Direct successor:** `2026-07-23-execution-plan-controlled-lifecycle-暂不实现.md`

---

## Global Constraints

- 本阶段不接入 Coordinator、ExecutionPlan、Session、Gate、API、SSE 或前端主链。
- 中间状态无需维持旧 Runner/API/页面可运行，不建立兼容 Adapter、双写、双读或旧新 Runner 并行 seam。
- 第一阶段结束时不批量删除旧主链文件；但允许替换最终路径上的旧 `WorkerRegistry`，旧 Coordinator 调用方因此可以在第二阶段切换前不可运行。不得为维持旧主链增加别名、兼容 Registry 或双事实源；第二阶段最终切换时删除剩余旧接口和旧事实来源。
- 全部 15 个 Run Kind 在本阶段完成；`resume → asset` 只是先行测试切片。
- Proposal 与 Worker 原始输出解析是仅有的动态 seam；解析后不得使用裸 `BaseModel`、`Any` 或字符串 Outcome 字典。
- 新增业务模型必须 `frozen=True, extra="forbid"`，集合使用 tuple/frozenset，不保留可变嵌套值。
- `WorkerExecutionResult` 是临时闭合执行联合；不提前实现全局 Failure 分类、重试、Judge、Run Store 或最终 Run 状态。
- `SuspendedWorkerRun` 与 `OperationContinuation` 在本阶段定义并做进程内恢复测试；confirmation、claim、receipt 和 Session 持久化留给第二阶段。
- Definition 的 revision、fingerprint、operation purpose 与其他控制字段必须作为完整 `WorkerRunControlSnapshot` 冻结和传递；本阶段不定义 purpose 的 criticality、重试、幂等或失败策略。
- Required Skill 失败必须 fail-fast，不调用 Runner、LLM、Tool 或 Contract。
- 所有新增字段、类型和函数使用中文注释或 docstring 解释含义与作用。
- 不修改 `backend/.env`、运行数据、输出、Trace、用户隐私文件或 `docs/assets/`。
- 不运行真实 LLM Eval，除非用户另行明确授权。
- 每个 Task 按公开接口行为测试 → 最小实现 → 定向回归推进。

## Public Test Seams

| seam | 验证目标 |
|------|----------|
| `WorkerInvocationRegistry.prepare()/resolve()` | Proposal 与具体输入如何形成完整控制快照；resolve 如何拒绝快照漂移并形成唯一不可变 Invocation |
| `DeterministicSuccessContractRegistry.evaluate()` | 配对输出如何形成命名 VerifiedOutcome |
| `RequiredSkillPreloader.preload_required()` | required Skill 是否在 Runner 前完整加载并 fail-fast |
| `run_worker_invocation()` | 真实、确定性、mock 是否只消费 Invocation 与窄 Context |
| `resume_worker_invocation()` | 暂停恢复是否保持身份、顺序且不重放 operation |
| `uv run pyright` | 15 个具体 Definition、Invocation、输出、Contract 和 Outcome 是否可静态缩窄 |

不得为测试暴露私有 Registry 字典、内部缓存或调用计数器。

## Target File Structure

### 新增

```text
backend/career_os/platform/worker/
├── models.py
├── inputs.py
├── invocations.py
├── outputs.py
├── outcomes.py
├── profile_patches.py
├── contracts.py
└── runtime.py
backend/career_os/platform/skill/preloader.py
backend/career_os/agents/graphs/workers/
├── deterministic_adapters.py
├── invocation_runner.py
├── invocation_react_runner.py
└── invocation_mocks.py
backend/career_os/platform/prompt/{worker}/invocation_system.md
backend/career_os/platform/prompt/{worker}/runs/<run_kind>.md
backend/typecheck/worker_invocation_contracts.py
backend/tests/platform/test_worker_invocation_registry.py
backend/tests/platform/test_worker_success_contract.py
backend/tests/platform/test_profile_patch_types.py
backend/tests/platform/test_required_skill_preloader.py
backend/tests/agents/test_worker_invocation_runner.py
```

### 重点修改

```text
backend/career_os/agents/graphs/workers/base.py
backend/career_os/agents/graphs/workers/registry.py
backend/career_os/agents/lc/tools.py
backend/career_os/platform/worker/__init__.py
backend/career_os/platform/worker/registry.py（用最终 WorkerInvocationRegistry 替换旧 WorkerRegistry）
backend/career_os/platform/prompt/loader.py
backend/career_os/platform/skill/registry.py
.agent/skills/career-inner-exploration/SKILL.md
.agent/skills/career-jd-alignment/SKILL.md
.agent/skills/resume-module-optimize/SKILL.md
backend/tests/eval/test_workers_llm.py
backend/pyproject.toml
backend/uv.lock
```

本阶段不删除 `react_runner.py`、旧 Coordinator Schema 或 `config/workers.registry.json`，只把它们保留为第二阶段待迁移/删除范围；不保证依赖它们的旧主链仍可运行。`backend/career_os/platform/worker/registry.py` 必须原位替换为最终 `WorkerInvocationRegistry`，不能并存旧 `WorkerRegistry`、兼容别名或 JSON 投影；新模块不得读取这些旧事实源。

## Task 1: 建立 resume → asset 契约先行切片

**Files:**

- Create: `backend/career_os/platform/worker/{models,inputs,invocations,outputs,outcomes,profile_patches,contracts}.py`
- Modify: `backend/career_os/platform/worker/__init__.py`
- Modify (replace contents): `backend/career_os/platform/worker/registry.py`
- Create: `backend/tests/platform/test_worker_invocation_registry.py`
- Create: `backend/tests/platform/test_worker_success_contract.py`
- Create: `backend/typecheck/worker_invocation_contracts.py`
- Modify: `backend/pyproject.toml`
- Modify: `backend/uv.lock`

### Step 1: 写 Registry 红灯测试

通过公开接口验证：

- `resume.generate_optimized_resume` 的完整输入解析为具体 `GenerateOptimizedResumeInvocation`；
- `asset.register_outputs` 缺少 verified deliveries 时不能形成完整 Invocation；
- `InvocationCreationRequest` 的 `node_id`、`goal`、完整 `inputs` 和整体 `control_snapshot` 经统一接口形成 Invocation，`invocation_id` 只能由 Registry 生成；
- `prepare()` 成功结果中的 `scope`、准备输入和完整 `WorkerRunControlSnapshot` 能原样进入第二阶段 Node Spec 与创建请求，调用方不拆分快照或根据类名、字符串表另行推导 Definition；
- 未注册 Definition、revision/fingerprint/控制字段漂移、Definition/Input 类型错配、非法 operation purpose、空节点、空目标、错误 scope、空档位和可变嵌套输入被结构化拒绝；
- Invocation 的 `worker_id + run_kind` 能把 `inputs` 静态缩窄为具体模型；
- 创建后修改原 request、Session fixture 或嵌套集合不会改变 Invocation。

测试阶段只使用内部 `ResumeAssetWorkerInvocationSlice` 名称，不得提前发布不完整的 `WorkerInvocation` 公共联合。

### Step 2: 实现最小具体模型与 Registry

实现 resume/asset 所需 PreparedInput、Input、ProfilePatch、Invocation 和 Definition 子类，并定义冻结的 `WorkerRunControlSnapshot` 与 `InvocationCreationRequest[TInput]`。`InvocationCreationRequest`（Invocation 创建请求）保存 `node_id`（节点编号，用于关联第二阶段 Plan）、`goal`（业务目标，用于指导 Worker）、`inputs`（完整输入，用于 Runner 执行）和不可拆分的 `control_snapshot`（动作控制快照，用于选择并复核 Definition）；它不接受 `invocation_id`，也不接受由调用方逐项填写的 operation、Skill、执行策略或 Contract 字段。

`prepare()` 只消费 `InvocationProposal + ExecutionScope + WorkerPreparedInput`，返回 `InvocationPrepared` 或 `InvocationRejected`。Registry 校验三者与同一 Definition 配对，并用具体 `prepared_input_model` 重新构造和深冻结输入。`InvocationPrepared`（Invocation 准备结果）只保存已验证的 `scope`（执行范围，用于限制阶段）、具体 `prepared_input`（准备输入，用于保存依赖绑定前已经存在的事实）和完整 `control_snapshot`（控制快照，用于冻结 Definition revision、fingerprint、operation capability/purpose、Skill、执行策略、Adapter、Contract 和 Judge 模式）。它不是 Invocation，不能交给 Runner；第二阶段只能原样复制整个快照，不能拆分后重新拼装。从 Session/Store 投影 PreparedInput 留给第二阶段，不创建含义重叠的准备事实模型。

`resolve(request)` 按 `control_snapshot.definition_id` 解析唯一 Definition，重新生成控制快照并做全字段相等校验，再用具体 `input_model` 校验 `inputs`、由 Registry 生成 `invocation_id`，并把请求快照原样复制进 Invocation。第一阶段测试使用 `prepare()` 返回的快照构造创建请求；第二阶段由 Plan binder 生成完整 Input 后，把 Node Spec 的身份、目标和原快照组合成同一请求。错误返回 `InvocationRejected`，成功返回 `InvocationResolved`，两者组成闭合结果，不产生半成品 Invocation。

本步骤同时：

- 实现单一规范序列化器和 SHA-256 fingerprint 计算；Definition revision 必须为正整数，任一控制语义变化同时递增 revision 并改变 fingerprint；
- 将 `operation_capabilities` 作为 operation 名称与允许 purpose 的唯一存储事实，`allowed_operations` 仅作为名称投影；
- 用 `WorkerInvocationRegistry` 原位替换旧 `WorkerRegistry`，不保留兼容类、别名或 JSON 读取分支；
- 在 `backend/pyproject.toml` 的 dev dependency 加入 `pyright`，配置 `[tool.pyright] typeCheckingMode = "strict"` 并覆盖新 worker 契约模块与 `backend/typecheck/`；
- 更新 `backend/uv.lock`，确保后续所有 `uv run pyright` 命令使用仓库锁定依赖，而不是依赖全局安装。

### Step 3: 写 Success Contract 红灯测试

验证：

- Schema 通过或 `completed` 不能直接产生 Outcome；
- 空 delivery、路径越过 output root、HTML 不完整、档位/数量不匹配均返回 `satisfied=False`；
- 合法 delivery 产生具体 `VerifiedHtmlDeliveriesOutcome`；
- `register_outputs` 只接受经过验证的 delivery，登记结果必须一一对应并使索引版本严格 +1；
- Contract 接受 verifier Adapter，不自行创建 Store 或文件系统。

### Step 4: 实现泛型 Contract Registry

实现 `ContractEvaluation[TOutcome]`、具体 Contract handler 与唯一 Registry。编号只用于 Trace；类型关联来自 Definition 的泛型具体 Contract，不使用字符串 Outcome 映射。

### Step 5: 运行切片检查

```bash
(cd backend && uv run pytest tests/platform/test_worker_invocation_registry.py tests/platform/test_worker_success_contract.py -q)
(cd backend && uv run pyright typecheck/worker_invocation_contracts.py)
```

记录真实结果；此时不声称完整 15 类型或产品主链完成。

## Task 2: 发布全部 15 个具体类型和闭合联合

**Files:**

- Modify: `backend/career_os/platform/worker/{models,inputs,invocations,outputs,outcomes,contracts,registry}.py`
- Modify: `backend/career_os/platform/worker/__init__.py`
- Modify: `backend/career_os/platform/worker/profile_patches.py`
- Modify: `backend/typecheck/worker_invocation_contracts.py`
- Modify: `backend/tests/platform/test_worker_invocation_registry.py`
- Modify: `backend/tests/platform/test_worker_success_contract.py`
- Create: `backend/tests/platform/test_profile_patch_types.py`

### Step 1: 为完整目录写参数化红灯测试

按设计规格第 6 节逐行验证：

- 15 个 `worker_id + run_kind` 唯一且没有 `strategy.career_plan`；
- 每行都存在具体 PreparedInput、Input、Invocation、WorkerStructuredOutput、Outcome、Definition 和 Contract 类型；
- Definition 子类展开五个具体泛型参数并使用 Literal discriminator；
- 每个动作只允许设计规格控制矩阵声明的 pipeline phase、operation capability/purpose、required/optional Skill、执行策略、Adapter 和 Judge 模式；空 operation/Skill 集合按矩阵保持为空，不自动补能力；
- ProfilePatch 只能使用该 Run Kind 允许的具体变体；
- 所有业务值满足深冻结规则。

### Step 2: 实现 15 行具体目录

先实现具体模型，再发布最终闭合联合：

- `AnyWorkerRunDefinition`；
- `WorkerPreparedInput`；
- `WorkerInput`；
- `InvocationPrepared` / `InvocationPreparationResult`；
- `WorkerRunControlSnapshot`；
- `WorkerInvocation`；
- `WorkerStructuredOutput`；
- `VerifiedOutcome`；
- `ProfilePatch`。

完成后删除 Task 1 的切片别名。新增 Run Kind 必须先增加具体类型、Contract、Prompt、测试和静态门禁，不能由运行时配置动态发明。

### Step 3: 实现全部确定性 Contract

逐行实现并验证设计规格中的契约条件，特别覆盖：

- `market.start_research` 只有在 confirmation、持久化 Plan、Job 和 Runner 接受事实一致时产生 `JobAcceptedOutcome`；
- `asset.reuse_outputs` 只产生建议 Outcome，不产生 Gate 或默认选择；
- `asset.register_outputs` 不从上下文或摘要补 delivery；
- `asset.delete_output` 只验证授权执行后形成的删除事实，本阶段 verifier 使用 fake Adapter。

### Step 4: 扩展静态类型门禁

Pyright fixture 必须证明：

- 两级 discriminator 可缩窄到 15 个具体 Invocation；
- Definition 分支同步恢复五个泛型参数；
- 具体 `SuccessContract[TInvocation, TOutput, TOutcome]` handler 的错误泛型配对在静态检查失败；公开 Registry 收到两个独立闭合联合的跨动作错配由运行时测试验证返回 contract violation；
- ProfilePatch 和 Outcome 不能跨 Run Kind 混用；
- 没有 `Any`、裸 `BaseModel` 或字符串字段绑定逃生。

### Step 5: 运行目录检查

```bash
(cd backend && uv run pytest tests/platform/test_worker_invocation_registry.py tests/platform/test_worker_success_contract.py tests/platform/test_profile_patch_types.py -q)
(cd backend && uv run pyright typecheck/worker_invocation_contracts.py)
```

## Task 3: 重写 Prompt、Skill 与动作索引

**Files:**

- Create: `backend/career_os/platform/prompt/{identity,capability,market,opportunity,strategy,resume,asset}/invocation_system.md`
- Create: `backend/career_os/platform/prompt/{worker}/runs/<run_kind>.md`
- Modify: `backend/career_os/platform/prompt/loader.py`
- Modify: `backend/career_os/platform/skill/registry.py`
- Modify: `.agent/skills/career-inner-exploration/SKILL.md`
- Modify: `.agent/skills/career-jd-alignment/SKILL.md`
- Modify: `.agent/skills/resume-module-optimize/SKILL.md`
- Modify: `backend/tests/platform/test_worker_invocation_registry.py`
- Modify: `backend/tests/platform/test_worker_registry.py`
- Modify: `backend/tests/platform/test_prompt_loader.py`

### Step 1: 写 Prompt/Skill 完整性红灯测试

验证每个 Definition 能解析唯一 Worker 基础 Prompt 与 Run Prompt；required Skill 名称/mode 能被 Skill Registry 解析；`resume-module-optimize(None)` 通过顶层 `allowed_workers: [resume]` 授权，带 modes 的 Skill 继续按具体 mode 授权，二者不能混用；Prompt 不包含旧字符串队列协议、跨 Worker 职责或要求模型自行加载 required Skill 的指令。

### Step 2: 分层迁移 Prompt

- 把长期职责和边界放入 `invocation_system.md`；
- 把动作内容放入 `runs/<run_kind>.md`；
- 把输入、目标、Tool Schema 和 Skill bundle 留给运行时注入；
- 不把允许 Tool 固化为必执行步骤；
- 不把 Contract 或业务验证责任交给 LLM。

旧 `system.md` 在本阶段只保留为第二阶段待删除文件，不保证旧主链仍可使用；新 loader 路径不得读取它。第二阶段切换后删除旧读取和旧文件。

### Step 3: 清理业务 Skill 职责

删除重复 Run Kind/mode 猜测、required Skill 自加载、跨 Worker 派工和未授权 Tool 规则；保留 Worker 在 Invocation 授权包络内对 Tool/optional Skill 的自主选择。

为 mode-less Skill 建立唯一授权规则：`.agent/skills/resume-module-optimize/SKILL.md` 增加顶层 `allowed_workers: [resume]`；`SkillRegistry` 解析并校验顶层 `allowed_workers`，且在同一 Skill 同时声明顶层授权和 `modes` 时启动失败。`RequiredSkillPreloader` 使用 `SkillRequirement(name="resume-module-optimize", mode=None)` 加载，不从正文推断 Worker 身份。

### Step 4: 运行 Prompt/Skill 检查

```bash
(cd backend && uv run pytest tests/platform/test_worker_invocation_registry.py tests/platform/test_worker_registry.py tests/platform/test_prompt_loader.py -q)
```

## Task 4: 建立 required Skill 预加载和统一 Runner seam

**Files:**

- Create: `backend/career_os/platform/skill/preloader.py`
- Create: `backend/career_os/platform/worker/runtime.py`
- Create: `backend/career_os/agents/graphs/workers/deterministic_adapters.py`
- Create: `backend/career_os/agents/graphs/workers/invocation_runner.py`
- Create: `backend/career_os/agents/graphs/workers/invocation_react_runner.py`
- Create: `backend/career_os/agents/graphs/workers/invocation_mocks.py`
- Modify: `backend/career_os/agents/graphs/workers/base.py`
- Modify: `backend/career_os/agents/graphs/workers/registry.py`
- Modify: `backend/career_os/agents/lc/tools.py`
- Create: `backend/tests/platform/test_required_skill_preloader.py`
- Create: `backend/tests/agents/test_worker_invocation_runner.py`
- Modify: `backend/tests/eval/test_workers_llm.py`

### Step 1: 写 Skill 预加载红灯测试

验证成功顺序、内容哈希、未知 Skill/mode、授权不匹配和中途失败。失败结果的 bundles 必须为空，attempts 必须保留失败前证据，Runner/LLM/Tool/Contract 均未启动。

### Step 2: 实现 RequiredSkillPreloader

Preloader 接受 Invocation，不接受任意名称数组；只解析冻结 requirements。optional Skill 不在此接口加载。

### Step 3: 写统一 Runner 红灯测试

验证：

- ReAct、deterministic、mock 和 stub 均只接收 `WorkerInvocation + WorkerRuntimeContext`；
- Context 不含完整 Session、`prior_results` 或任意业务字典；
- Runner Registry 只按 `execution_strategy + deterministic_adapter_id` 解析实现；
- operation invoker 只接受 Invocation `operation_capabilities` 中登记的 `operation_name + purpose` 组合，非法 purpose 在副作用前拒绝；
- `completed/failed/accepted_async/awaiting_authorization` 四分支均可表达；
- mock 不补默认输入、Tool 参数、Outcome 或 delivery；
- 未预加载 required Skill 时不允许进入 Runner。

### Step 4: 实现 operation 调用端口与临时结果联合

定义 `HarnessOperationInvoker`、`WorkerRuntimeContext` 和 `WorkerExecutionResult`，并逐项实现设计规格第 5.7 节的精确暂停模型：`PendingOperationCall`（待提交操作调用）、`WorkerMessageSnapshot`（冻结消息）、`ReActOperationContinuation`（ReAct 恢复位置）、`DeterministicOperationContinuation`（确定性恢复位置）、闭合 `OperationContinuation`、`SuspendedWorkerRun`（暂停现场）和 Runner 只读的 `CommittedOperationResult`（已提交操作结果）。字段、Literal discriminator、tuple 顺序、消息角色约束和非空身份不得简化为字典或通用 payload。该端口至少有 fake Adapter 与第二阶段 Harness Adapter 两个预期实现，测试只使用 fake；本阶段不创建 OperationRegistry 或持久化 receipt。

实现单一 Canonical JSON 序列化器与 SHA-256 校验：参数和结果都必须先解析再规范序列化，拒绝 NaN、重复键和实现相关格式；恢复时重新计算 hash。operation-specific Adapter 负责把 `canonical_result_json` 解析为具体结果类型，`CommittedOperationResult` 不保存 `Any` 值。

### Step 5: 实现 ReAct 与 deterministic Runner

- ReAct Runner 解析当前 Invocation 的基础/动作 Prompt、Skill bundle 和 Tool Schema，由模型自主决定授权包络内的调用；
- deterministic Registry 只解析 Definition 已冻结的 Adapter ID；未知或不匹配编号明确失败；
- `completed` 只携带与 Invocation 配对的具体输出，不调用 Contract；
- `accepted_async` 只允许 `market.start_research` 的具体输出；
- 需要授权时冻结现场和 continuation，不执行 operation。

### Step 6: 写并实现进程内恢复

通过 `resume_worker_invocation()` 验证：

- ReAct 恢复保持 assistant Tool Call 顺序和 `tool_call_id`；
- 已完成调用不重放，剩余调用不重排；
- `pending_call + remaining_calls` 与最后一个未闭合 assistant Tool Call 批次的有序后缀完全一致，消息角色/字段组合合法；
- committed result 的 call id、operation name、arguments hash、规范结果 JSON 与 result hash 全部通过完整性校验；
- deterministic 恢复只调用原 Adapter 的 `complete_from_committed_result()`；
- 恢复不重新调用 Coordinator、LLM 或 operation invoker；
- Invocation、operation call 和 continuation 身份错配明确拒绝。

### Step 7: 运行 Runner 检查

```bash
(cd backend && uv run pytest tests/platform/test_required_skill_preloader.py tests/agents/test_worker_invocation_runner.py -q)
(cd backend && uv run pyright typecheck/worker_invocation_contracts.py)
```

## Task 5: 启动完整性与第一阶段验收

**Files:**

- Modify: `backend/career_os/platform/worker/registry.py`
- Modify: `backend/career_os/agents/graphs/workers/invocation_runner.py`
- Modify: `backend/typecheck/worker_invocation_contracts.py`
- Verify only: `backend/pyproject.toml`、`backend/uv.lock`、本 Plan 新增和修改的测试、Prompt 与 Skill

### Step 1: 实现契约模块启动校验

校验 15 个 Definition、Prompt、Skill、Contract、Outcome 和 Adapter 引用完整唯一；revision 为正整数，声明 fingerprint 与规范控制快照重算值一致。允许空 `operation_capabilities`；非空集合中的 operation 名称必须格式合法且不重复，每个 purpose 集合非空并只含设计规格控制矩阵登记值。第二阶段 OperationRegistry 建立后扩展为全部名称与 purpose 可解析。校验 mode-less Skill 的顶层 Worker 授权、带 mode Skill 的逐 mode 授权，以及两种声明方式互斥。

### Step 2: 负向搜索

```bash
rg -n 'WorkerRunDefinition\[Any|AnyWorkerRunDefinition: TypeAlias = WorkerRunDefinition|inputs: BaseModel|verified_outcomes: Mapping\[str, Any\]' backend/career_os/platform/worker backend/typecheck
rg -n 'StrategyCareerPlanDefinition|CareerPlanInvocation|list_type="plan"' backend/career_os/platform/worker backend/typecheck
rg -n 'required.*load_skill|pending_workers|prior_results' backend/career_os/platform/prompt/*/invocation_system.md backend/career_os/platform/prompt/*/runs .agent/skills
```

期望：新契约模块、Prompt 和相关 Skill 不命中旧协议或动态类型逃生。旧主链文件中的命中留到第二阶段清除，不在本阶段误报为已完成。

### Step 3: 运行第一阶段验收

```bash
(
  cd backend
  uv run pytest \
    tests/platform/test_worker_invocation_registry.py \
    tests/platform/test_worker_success_contract.py \
    tests/platform/test_profile_patch_types.py \
    tests/platform/test_required_skill_preloader.py \
    tests/agents/test_worker_invocation_runner.py -q
)
(cd backend && uv run pyright)
```

第一阶段不运行或不要求通过全部旧后端测试与前端构建，因为主链尚未切换。若主动执行，结果只能作为中间状态快照如实记录。

### Step 4: 记录交付边界

交付说明必须写明：

- 契约模块的定向测试和 Pyright 实际结果；
- 全部旧测试、前端构建和真实 LLM Eval 是否未执行；
- 聊天主链、Session、Gate、API 和前端尚未迁移；
- 第二阶段是产品可运行性和全局失败机制的直接前置。

## Completion Criteria

1. 设计规格定义的 15 个 Run Kind 全部进入具体类型和闭合联合。
2. `WorkerInvocationRegistry` 是 Definition 解析与 Invocation 创建的唯一事实源，`DeterministicSuccessContractRegistry` 是 Contract 解析与验收的唯一事实源。
3. 所有确定性 Contract 只从配对输出和 verifier 事实产生 Outcome。
4. ProfilePatch、Outcome、Invocation 和暂停载荷满足深冻结规则。
5. Required Skill 在 Runner 前 fail-fast 预加载。
6. 统一 Runner 和恢复 seam 不读取完整 Session、不补默认事实、不重放 operation。
7. 定向测试与完整 Pyright 通过，或如实记录失败/跳过。
8. 没有提前实现 ExecutionPlan、OperationRegistry、授权持久化或全局 Failure。
9. 没有声称产品主链已完成迁移。
10. 15 个动作的 operation capability/purpose、Skill、执行策略、Adapter 和 Judge 模式与设计规格控制矩阵一致，mode-less resume Skill 具有显式 Worker 授权。
11. Pyright 在 Task 1 首次运行前已进入 dev dependency 和 `uv.lock`，并以 strict 配置执行。
12. Node Spec 传回的完整控制快照只有与当前 Definition 的 revision、fingerprint 和全部控制字段一致时才能创建 Invocation。
13. 暂停恢复对规范 JSON、摘要、消息角色、调用身份和未完成调用顺序执行完整性校验。

## Suggested Commit

仅在用户另行要求创建 commit 时使用：

```text
refactor(worker): 建立强类型调用与结果契约

- 为十五个 Run Kind 建立不可变 Invocation、结构化输出和命名 Outcome
- 通过确定性成功契约与必需 Skill 预加载约束 Worker 执行
- 统一 ReAct、确定性 Adapter 和暂停恢复的 Runner 接口
```
