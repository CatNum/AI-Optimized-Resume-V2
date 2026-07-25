# 强类型 WorkerInvocation 与 ExecutionPlan Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Each vertical slice follows red → green and uses checkbox (`- [ ]`) syntax for tracking.

**Goal:** 一次性重写当前执行系统：用动态边界内的 `InvocationProposal`、不可变且具体类型化的 `ExecutionPlanNodeSpec`、延迟物化的闭合 `WorkerInvocation` 联合、类型化确定性 Success Contract 和依赖感知 `ExecutionPlan` 替换字符串 Worker 队列；以单个 `SessionExecutionState` 聚合替换分散的 Session/Task/Artifact 控制事实，并同时落地稳定 `output_id`、全局版本化产物索引、可幂等恢复的授权/确认身份与持久化 receipt、按 ReAct/确定性策略判别的 `SuspendedWorkerRun/OperationContinuation`、独立 `OperationRegistry` 和闭合 `ProfilePatch`，使 Harness 校验并冻结每个 Worker Run 的业务动作、输入来源、执行策略、能力包络、可信 Outcome 和下游依赖。

**Architecture:** 把现有 `WorkerRegistry` 深化为 `WorkerInvocationRegistry`（Worker 调用注册表）：Coordinator 只在 LLM/JSON seam 提出动态 `worker_id + run_kind`，注册表通过 `prepare()/resolve()` 返回由 Literal 区分的闭合 `WorkerInvocation` 联合。`ExecutionPlanBuilder` 以 `PlanBuildResult = PlanBuilt | PlanBuildRejected` 返回结构化成功/拒绝，`ExecutionPlan` 通过强类型 `OutcomeBinding` 补全下游输入并串行调度。所有 Task 直接建设或替换最终接口；旧四参数 Runner、字符串 analyze、旧 Prompt/loader、旧 API、旧页面契约和旧测试可以在对应 Task 直接删除，中间工作树不要求可运行，也不建立并行或兼容 seam。`ExecutionPlanRequestService.handle(ExecutionPlanRequest)` 是聊天、市场启动、产物删除、Gate 决策和 confirmation 的唯一深接口；闭合请求联合只携带外部业务事实，资源解析、冻结摘要、binding 校验和终态结果重放都隐藏在该模块内部，不再使用 `preset_proposals` 或 `request_context: dict[str, Any]`。`SessionExecutionState` 是阶段、完整 Task 控制状态、闭合 pending Gate、Artifact 引用与版本、当前执行和终态回执的唯一事实源；同步 Plan 只在请求内运行，`CurrentExecution = NoCurrentExecution | AsynchronousExecution | AuthorizationSuspendedExecution` 只保存跨请求尚未结束的 Plan，单个 `execution-state.json` 通过 revision CAS 原子发布且不读取或迁移旧本地数据。RequestService 负责该聚合的全部持久化事务以及 confirmation 的授权、claim、冻结 operation 和 receipt 协议；`ExecutionPlanTurnHandler` 负责新 Turn，`ExecutionPlanResumeHandler` 在 receipt 提交后恢复原 Worker 和推进 Plan，两者都不能直接写 Session。`OperationRegistry` 是 operation 授权元数据、durable ledger 和唯一 handler 的事实来源。`OutputIndexStore` 从干净目录创建全局索引并持久化删除 receipt。纯规划请求本期不提供 legacy Adapter，后续独立 Spec/Plan 直接接入 pipeline。最终任务统一恢复后端、前端、类型检查和跨模块回归的完整可运行性。

**Tech Stack:** Python 3.11、Pydantic 2、LangGraph、LiteLLM、pytest、Pyright strict、本地 Markdown Prompt

**Design SSOT:** `../specs/2026-07-23-typed-worker-invocation-execution-plan-design.md`

**Dependency:** 本 plan 必须先于 `2026-07-23-global-failure-mechanism.md` 实施。

**Status:** 待实现；已确认按最终架构一次性重写，不保留迁移期兼容 seam 或旧数据迁移

---

## Global Constraints

- 本 plan 实现调用定义、Invocation、确定性 Success Contract、命名 Outcome 提取、ExecutionPlan、能力注入和 Runner 输入接口；不实现全局 Failure 分类、OperationPolicyRegistry、重试、补偿、断路器、Run Store、语义 Judge、最终 Run 状态聚合或用户错误目录。
- 本 plan 明确实现 `operation_authorization` 的同 Session 双请求恢复：第一次请求序列化完整活动 ExecutionPlan、SuspendedWorkerRun 和闭合 OperationContinuation；第二次请求只接受结构化 confirmation。底层 operation 以 `authorization_id` 幂等保存结果，聚合中的 `CommittedOperationReceipt` 提交后 ResumeHandler 才继续。已持久化 rejected 的旧实例快照收敛为 cancelled/rejected，其余未完成快照收敛为 interrupted。
- `ExecutionPlanRequestService` 是唯一 Session 持久化事务模块。它只接收闭合 `ExecutionPlanRequest`，Handler 的内部结果携带尚未提交 transition，RequestService 消费 transition 后返回不含 transition、带已提交/观察修订号的 `ExecutionPlanRequestResult`。普通 Turn 对完整 `SessionExecutionState` 执行一次命名 CAS；confirmation 恢复按授权、claim、receipt、resuspend/finalize 分别执行命名 CAS，不能声称含外部副作用的整个请求只有一次 CAS。
- `SessionExecutionState` 是阶段、闭合 Gate、完整 Task 控制状态、Artifact 引用与版本、当前执行和回执的唯一事实源；旧 `state.json`、`artifacts.json`、TaskStore 阶段及旧格式读取全部删除，不建立兼容投影。同步 Plan 不进入当前槽位；`CurrentExecution` 的 `NoCurrentExecution/AsynchronousExecution/AuthorizationSuspendedExecution` 三个分支互斥，`pending_gate` 只用于已结束 Plan 后等待下一 Turn，非空时 `current_execution` 必须是 `NoCurrentExecution`。后台 Job 使用自身状态，不占用异步 Plan 分支。
- 当前仓库采用每个 `DATA_DIR` 单写入进程模型：进程内并发由 `session_revision` CAS 仲裁，单个 `execution-state.json` 使用同目录临时文件、flush/fsync、原子 replace 和父目录同步发布。
- operation 名称、`requires_authorization`（是否需要授权）、`durable_result_ledger_id`（持久化结果账本编号）和唯一领域 handler 绑定只由独立 `OperationRegistry` 管理；`resolve(operation_name)` 一次返回 `ResolvedOperation(definition, handler)`，Harness 与后续 OperationExecutor 都不能接收调用方临时传入的 handler。Tool Registry 只管理模型可见调用形式。
- 产物登记和删除必须使用稳定 `output_id` 与全局 `expected_index_version`；唯一索引文件固定为 `settings.data_dir / "outputs-index.json"`，并从干净目录直接创建最终 schema。不得读取或迁移旧 `profile.outputs_index`。
- 市场方案确认必须生成并持久化 `confirmation_id`；同版本重复确认幂等，修订清除旧编号，启动研究必须验证确认引用的 Session、版本和摘要。
- `ProfilePatch` 必须是按 `patch_kind` 区分的闭合联合；具体 Worker 输出不得继续使用任意 JSON。
- 纯规划链和 `strategy.career_plan` 完全移出本期闭合目录；本 plan 直接删除旧 `list_type="plan"` 路径，不保留 `LegacyCareerPlanAdapter`、兼容响应或第二执行 seam。
- `InvocationProposal` 只允许模型提供 `worker_id`（Worker 标识）和 `run_kind`（业务动作）；依赖、Tool、Skill、成功契约和授权范围只由 Harness 补全。
- `allowed_operations`（允许 operation）与 `optional_skills`（可选 Skill）只定义本次 Invocation 的能力包络，不是 Harness 预先生成的 Tool 调用清单；ReAct Worker LLM 仍自主决定是否调用、调用顺序和参数。
- Harness 必须校验并执行每次 Tool/Skill 调用，但不得把 ReAct 内部动态 operation 预先编码成固定步骤。只有输入完整、动作唯一且不需要模型推理的路径，才允许使用注册的确定性 Adapter 绕过 Worker LLM。
- 动态数据只允许存在于两个明确 seam：`InvocationProposal.run_kind: str` 所在的 LLM/JSON Proposal 解析 seam，以及 Worker 原始输出解析与 Invocation/输出配对 seam。`resolve()` 成功后的调用与输入、输出解析和配对后的结构化输出，以及后续结果和绑定，不得再使用裸 `BaseModel inputs`、`Any`、字符串 Outcome 名称或 `Mapping[str, Any]`。
- 15 个 Run Kind 必须各有一个具体 Invocation 类和一个带 Literal `worker_id + run_kind` 的具体 Definition 子类，并组成可由 Pyright 缩窄的闭合联合；新增 Run Kind 必须修改代码类型、注册定义、Contract/Outcome 与 Pyright fixture。
- Tasks 1–3 只使用明确命名的 resume/asset 内部切片别名验证机制；Task 4 发布全部 15 个最终闭合类型。后续 Task 直接替换调用方，不要求旧接口在中间态继续可运行。
- Plan 创建的是 `ExecutionPlanNodeSpec`（计划节点规格）；依赖未来 Outcome 的节点不得提前构造输入不完整的 WorkerInvocation。
- `WorkerInvocation` 创建后不可修改；用户改变输入或目标时创建新 Invocation 和新 Plan。
- `ConfigDict(frozen=True)` 只禁止字段重赋值，不等于深冻结；PreparedInput、完整 Input、WorkerStructuredOutput、VerifiedOutcome、Node Spec、Invocation、PlanNodeResult 与 ExecutionPlan 的嵌套业务值必须使用 `tuple`、`frozenset` 或 `frozen=True, extra="forbid"` 的具体子模型，禁止把 `list`、`dict`、`set` 或其他可变容器带过已解析 seam。
- 第一版 ExecutionPlan 只串行执行，但模型必须表达真实依赖，不能退回普通字符串队列；节点选择、`ready → running`、Worker Run 编号绑定和 dispatch 生成只能由 `ExecutionPlanExecutor.claim_next()` 在一次 Plan 状态转换中完成。
- `advance()` 只接收本次新完成的 running 节点结果，并在 `running → finished` 时把 `PlanNodeResult` 持久化到节点；ExecutionPlan 是累积结果的唯一事实来源，Coordinator 不得维护第二份 `plan_node_results`。fan-in 必须能跨多次 `advance()` 使用不同上游的已持久化结果。
- Coordinator LLM 的动作索引必须覆盖当前阶段和 Harness 预先判定可合法前向进入的阶段；索引计算不得修改 Session 或 Task Store，目标阶段、动作、Gate 与整个 Plan 校验成功后才能提交阶段推进。
- `Workflow Transition Gate` 两侧的动作不得进入同一个 Plan；`Additional Input Gate` 补充信息后创建新 Turn 和新 Plan。
- `asset.reuse_outputs` 只产生经过确定性 Contract 验证的 `ReuseRecommendationOutcome`，不得由 Worker、Prompt、mock 或 Contract 输出 `gate_prompt` 或默认选择。Harness 基于该 Outcome 创建并持久化闭合三选一 `reuse_confirm` Additional Input Gate；当前 Plan 结束，用户选择后在新 Turn 创建终态空 Plan、增量优化 Plan 或新建完整优化 Plan。
- `asset.register_outputs` 只有在 `resume.generate_optimized_resume` 产生 `VerifiedHtmlDeliveriesOutcome`，并经 `bind.resume_verified_html_to_asset_register` 强类型 binder 构造 `RegisterOutputsInput` 后，才能物化 WorkerInvocation 并 ready。
- `required_skills` 使用结构化 `SkillRequirement(name, mode)`，由 Harness 在第一次 Worker LLM 调用前全部预加载；任一失败都返回 `required_skill_preload_failed`，不得调用 WorkerRunner、LLM、业务 Tool 或产生 verified Outcome。
- required Skill 预加载在本 plan 中只做 fail-fast，不实现重试、降级或用户消息分类；后续全局失败 plan 消费同一加载证据，不得重新实现另一套 Skill 必需性判断。
- required Skill 预加载返回成功/失败判别联合；失败分支不暴露可启动 Worker 的部分 bundle，但必须保留按 Requirement 顺序的尝试记录、成功项内容哈希和最终失败错误，供 Trace 使用。
- required Skill 不进入 LiteLLM Tool Schema；optional Skill 只有在 Definition 显式允许 `load_skill` 时才能按 `optional_skills` 中声明的名称与 mode 加载。
- required Skill 由 Harness 强制预加载；optional Skill 是否需要由 ReAct Worker LLM 在授权集合内自主判断，Harness 只做可见性、参数和权限校验。
- 现有 Worker 基础 Prompt 与 Skill 正文必须审计并改写，删除 required Skill 重复加载、Run Kind/mode 重复猜测、跨 Worker 职责和互相冲突的 Tool 规则；不得以“清理旧 Prompt”为由取消 LLM 对已授权 Tool/optional Skill 的自主选择。
- `config/workers.registry.json` 不再作为运行时行为事实来源；本 plan 选择删除该手写运行时配置，不增加第二份可改写安全行为的 JSON。
- Runner 在本 plan 中返回临时闭合 `WorkerExecutionResult = completed | failed | accepted_async | awaiting_authorization`，公开签名只接收 `WorkerInvocation + WorkerRuntimeContext`；RuntimeContext 只含 Session 身份/修订号、Trace、Harness operation 调用能力和已加载 Skill，不含完整 `session_state` 或业务事实。completed/accepted_async 的局部 Adapter 必须先调用确定性 Success Contract，只有 `ContractEvaluation.satisfied=True` 才能生成带 verified Outcome 的最小 `PlanNodeResult`。后续全局失败 plan 用最终 `WorkerRunResult` 替换该临时联合，并复用唯一契约 Registry。
- 本 plan 接受临时 `PlanResultPresenter`：它只读取 ExecutionPlan 终态、PlanNodeResult 和 VerifiedOutcome 生成确定性 `synthesis_draft + artifact_refs`，不读取旧 Worker summary、`prior_results` 或角色说明；后续全局失败机制用统一 Turn Result Renderer 替换。
- `market.start_research` 是异步提交的唯一特例：`WorkerExecutionAcceptedAsync` 不能直接成为 Plan 结果；局部结果 Adapter 验证后台 Job 已创建并持久化、身份可追踪且 `MarketResearchRunner.start()` 已接受后台启动后调用确定性 Contract，产生 `JobAcceptedOutcome` 才能让当前 Worker Run/节点 success。现有 `MarketResearchRunner` 独立继续，不等待后台任务终态；正式 Job Run 与 Job ExecutionPlan 留给后续全局失败机制。
- 真实 Runner、mock、stub 不得补默认档位、默认 Tool 参数或默认下游产物。
- 所有新增字段、类型和函数必须使用中文注释或 docstring 解释含义与作用。
- 测试只通过已确认的公开 seam：`WorkerInvocationRegistry`、`DeterministicSuccessContractRegistry`、`ExecutionPlanBuilder/Executor`、`RequiredSkillPreloader`、统一 `WorkerRunner`、persistence-free Turn/Resume Handler 和持久化 `ExecutionPlanRequestService.handle()`；不得断言私有字典或内部调用次数。旧契约测试可以删除或重写，最终验收只验证目标架构。
- 每个 Task 按一个行为测试 → 最小实现 → 该切片回归的顺序推进，不先批量写完所有测试。
- 不修改用户现有 `docs/assets/`，不清理无关工作区改动。

## Confirmed Test Seams

| Seam | Interface | 验证行为 |
|------|-----------|----------|
| Worker 调用注册表 | `WorkerInvocationRegistry.prepare()/resolve(spec, source_results=...)` | 提议如何变成 Node Spec，以及如何按 source_node_id 从带来源身份的 PlanNodeResult 生成唯一、不可变的 Invocation |
| 确定性成功契约 | `DeterministicSuccessContractRegistry.evaluate()` | Worker 输出如何经过业务验收并形成可信命名 Outcome |
| 计划构建 | `ExecutionPlanBuilder.build() -> PlanBuildResult` | Harness 如何补全依赖、Required Outcome 输入绑定，并以 PlanBuilt/PlanBuildRejected 表达成功或结构化拒绝 |
| 计划推进 | `ExecutionPlanExecutor.advance()` | 新结果如何持久化到 finished 节点，并结合 Plan 内历史结果绑定输入、物化下游 Invocation；不产生 dispatch |
| 计划认领 | `ExecutionPlanExecutor.claim_next()` | 如何原子选择唯一 ready 节点、绑定 Worker Run 编号、转换为 running 并返回唯一 dispatch |
| 必需 Skill 预加载 | `RequiredSkillPreloader.preload_required()` | required Skill 是否在 Runner/LLM 前按名称与 mode 全部加载；失败时 bundles 为空但 attempts 可完整写 Trace |
| Worker 执行 | `run_worker_invocation()` / `resume_worker_invocation()` | 起始执行是否只消费 WorkerInvocation；恢复是否只消费 SuspendedWorkerRun、已提交 receipt 和运行依赖，且不重放 operation、不重选 Adapter、不重新生成 Tool Call |
| 操作定义 | `OperationRegistry.resolve()/validate_startup()` | operation 定义、授权要求、durable ledger 和唯一 handler 是否只有一个绑定来源，并能被 Worker 与后续 OperationExecutor 共用 |
| Turn 编排 | `run_execution_plan_turn()` / `ExecutionPlanResumeHandler` | 闭合 `NewExecutionPlanTurnRequest` 与已提交 receipt 的恢复是否分别形成闭合且尚未提交的 `ExecutionPlanStateTransition` |
| 请求事务 | `ExecutionPlanRequestService.handle(ExecutionPlanRequest)` | 是否集中加载/提交完整 Session 聚合、消费内部 transition 并只返回已提交结果；普通 Turn 一次命名 CAS，confirmation 按命名状态迁移执行多次 CAS |
| Session 聚合 | `SessionStore.load_execution_state()` 与命名 CAS | 阶段、闭合 Gate、完整 Task 控制状态、Artifact 引用和唯一 CurrentExecution 是否在单个 `execution-state.json` 中共同发布 |
| 授权暂停计划存储 | `SessionStore.suspend/authorize/claim/commit_authorized_operation_result/resuspend/finalize_active_execution_plan()` | `AuthorizationSuspendedExecution` 是否保存唯一当前 Plan/continuation，把底层幂等结果与授权 receipt 原子提交，并在终结时同时保存终态 Plan/confirmation receipt和切换当前执行槽位 |
| 产物索引 | `OutputIndexStore.read_snapshot()/register()/delete_authorized()` | 全局索引、稳定 output_id、版本及删除 receipt 是否在重试与崩溃恢复时保持一致 |
| 结果展示 | `PlanResultPresenter.render()` | 是否只从 Plan 终态与 verified outcomes 形成确定性回复，不回退到 Worker 角色说明 |
| 市场确认 | `MarketResearchPlanStore.confirm()` / `MarketResearchService.start()` | confirmation_id 是否持久化、幂等、随修订失效；启动是否在 Job 持久化且 Runner 接受后台启动后才返回 accepted |
| 静态类型门禁 | `uv run pyright` | Invocation 缩窄、Contract Outcome 和 binder 签名是否端到端一致 |

这些 seam 已由设计规格第 15 节确认；实施时无需再创建测试专用公开方法。

## Target File Structure

### 新增

```text
backend/career_os/platform/worker/models.py
    # 定义 WorkerId、动态 Proposal、具体 Node Spec、15 个具体 Invocation、WorkerExecutionResult 与闭合联合

backend/career_os/platform/worker/inputs.py
    # 定义 15 个 Run Kind 的准备输入和完整输入模型

backend/career_os/platform/worker/profile_patches.py
    # 定义按 patch_kind 判别的闭合 ProfilePatch 联合

backend/career_os/platform/worker/outcomes.py
    # 定义类型化 OutcomeDefinition、具体 VerifiedOutcome 与闭合联合

backend/career_os/platform/worker/bindings.py
    # 定义泛型 OutcomeBinding 和上游 Outcome 到下游完整输入的 binder

backend/career_os/platform/worker/contracts.py
    # 定义泛型 ContractEvaluation、具体 Success Contract 与类型化 Outcome 提取

backend/career_os/platform/worker/plan.py
    # 定义 PlanBuildResult、带持久化节点结果的 ExecutionPlan、Plan Rule、Builder 和串行 Executor

backend/career_os/platform/worker/requests.py
    # 定义早期窄事实投影，并在 Task 8 发布聊天、市场、删除、Gate 与 confirmation 的闭合请求联合

backend/career_os/platform/worker/transitions.py
    # 定义 Handler 返回、只能由 RequestService 提交的闭合 Session 状态迁移

backend/career_os/platform/store/execution_state.py
    # 定义完整 Task、分阶段 Artifact、闭合 pending Gate、唯一 CurrentExecution 与 Session 聚合 schema

backend/career_os/platform/store/writer_lease.py
    # 定义每个 DATA_DIR 的单写入进程租约

backend/career_os/platform/output/models.py
    # 定义 output_id、版本化索引快照、登记/删除结果和删除授权

backend/career_os/platform/operation/models.py
    # 定义独立 OperationDefinition，不把授权与 ledger 元数据塞进 ToolDefinition

backend/career_os/platform/operation/canonical.py
    # 定义参数、账本结果和 receipt 共用的 canonical JSON 与 SHA-256 实现

backend/career_os/platform/operation/ledger.py
    # 定义 DurableOperationResult、DurableResultLedger 接口与持久化账本注册表

backend/career_os/platform/operation/output_index_ledger.py
    # 定义与 OutputIndexStore 共享删除 receipt 的持久化 ledger Adapter，不单独制造删除事实

backend/career_os/platform/operation/registry.py
    # 定义 ResolvedOperation、唯一 Definition/handler 绑定与 durable ledger 启动完整性校验

backend/career_os/platform/operation/__init__.py
    # 导出 OperationDefinition 与 OperationRegistry 的稳定公开接口

backend/career_os/platform/skill/preloader.py
    # 定义 required Skill 的成功/失败判别结果、只读 LoadedSkillBundle、逐项尝试证据和 fail-fast 错误

backend/career_os/agents/graphs/workers/deterministic_adapters.py
    # 定义确定性 Adapter Protocol、Registry 和依赖已就绪的生产 Adapter；市场与产物 Adapter 在对应后续 Task 接线

backend/career_os/agents/graphs/workers/invocation_runner.py
    # 定义只接收 WorkerInvocation 的唯一 Runner seam

backend/career_os/agents/graphs/workers/invocation_react_runner.py
    # 定义最终 ReAct 实现

backend/career_os/agents/graphs/workers/invocation_mocks.py
    # 定义与唯一 Runner seam 同签名的 mock/stub

backend/career_os/agents/graphs/execution_plan_coordinator.py
    # 定义 CoordinatorRuntimeContext、ExecutionPlanTurnResult 与唯一类型化 Coordinator 深模块入口

backend/career_os/api/execution_plan_requests.py
    # 定义 persistence-free Turn/Resume Handler 与共享类型化 Plan 请求事务模块

backend/career_os/platform/worker/presentation.py
    # 定义临时 PlanResultPresenter，只从 Plan 终态与 VerifiedOutcome 生成回复材料

backend/career_os/platform/prompt/<worker>/runs/<run_kind>.md
    # 只描述当前业务动作，不承担动作选择

backend/tests/platform/test_worker_invocation_registry.py
    # 通过注册表公开接口验证定义、阶段、输入和能力快照

backend/tests/platform/test_worker_success_contract.py
    # 通过契约公开接口验证确定性业务验收和命名 Outcome 提取

backend/tests/platform/test_execution_plan.py
    # 通过计划公开接口验证依赖图和串行调度

backend/tests/platform/test_profile_patch_types.py
    # 验证各 Run Kind 只能输出对应的闭合 ProfilePatch

backend/tests/platform/test_output_index.py
    # 验证干净目录初始化、稳定 output_id、索引版本和授权绑定

backend/tests/platform/test_operation_registry.py
    # 验证 operation 唯一性、授权字段组合和 durable ledger 绑定

backend/tests/platform/test_durable_result_ledger.py
    # 验证账本幂等语义和每个默认 Adapter 销毁实例后的重启/重建一致性

backend/tests/api/test_active_execution_plan_session.py
    # 验证 ReAct 与确定性 continuation 的暂停、确认和恢复协议

backend/tests/api/test_outputs_api.py
    # 验证两阶段删除确认 API 复用同一 Plan 链、第一次无副作用与重复确认幂等

backend/tests/platform/test_required_skill_preloader.py
    # 验证 required Skill 在 Runner/LLM 前全部预加载，并在任一失败时 fail-fast

backend/tests/agents/test_worker_invocation_runner.py
    # 验证真实 Runner、mock、stub 的统一 Invocation 输入接口

backend/tests/agents/test_coordinator_execution_plan.py
    # 验证 Coordinator 从提议到 Plan 的端到端确定性行为

backend/tests/platform/test_plan_result_presenter.py
    # 验证展示不回退到 Worker summary 或角色说明

backend/typecheck/worker_invocation_contracts.py
    # 用 typing.assert_type 固化 Invocation 缩窄、Contract 和 binder 的静态契约
```

### 重点修改

```text
backend/career_os/platform/worker/registry.py
backend/career_os/platform/worker/__init__.py
backend/career_os/agents/state/coordinator.py
backend/career_os/agents/state/worker.py
backend/career_os/agents/lc/coordinator_llm.py
backend/career_os/agents/lc/tools.py
backend/career_os/agents/graphs/coordinator.py
backend/career_os/agents/graphs/workers/base.py
backend/career_os/agents/graphs/workers/registry.py
backend/career_os/harness/delegate.py
backend/career_os/harness/executor.py
backend/career_os/harness/chat_attachments.py
backend/career_os/platform/store/session.py
backend/career_os/platform/store/output.py
backend/career_os/platform/tool/handlers/outputs.py
backend/career_os/platform/market_research/models.py
backend/career_os/platform/market_research/plans.py
backend/career_os/api/market_research.py
backend/career_os/api/sessions.py
    # 查看改为 output_id 路由，删除改为两阶段 delete-confirmations API，不再接收路径
backend/career_os/platform/prompt/loader.py
backend/career_os/platform/skill/registry.py
backend/career_os/platform/prompt/coordinator/system.md
backend/career_os/platform/prompt/{identity,capability,market,opportunity,strategy,resume,asset}/system.md
.agent/skills/career-inner-exploration/SKILL.md
.agent/skills/career-jd-alignment/SKILL.md
.agent/skills/resume-module-optimize/SKILL.md
backend/career_os/api/chat.py
    # 直接替换为类型化请求入口并删除旧 handler
web/src/components/OutputsPanel.tsx
web/src/lib/chatAttachments.ts
backend/pyproject.toml
backend/uv.lock
backend/tests/**
```

### 删除

```text
config/workers.registry.json
    # 删除手写运行时事实来源；Worker 索引改由代码注册表投影

backend/career_os/agents/schemas/workers.py
    # 删除旧 Worker 级通用输出 Schema

backend/career_os/agents/lc/worker_llm.py
    # 删除旧 summary 增强 seam

backend/career_os/agents/graphs/workers/react_runner.py
backend/career_os/agents/graphs/workers/react_mocks.py
    # 删除旧 Runner 与 mock seam，由 invocation_* 实现唯一替代

backend/career_os/platform/store/task.py
    # 删除 TaskStore 控制事实源，完整任务控制状态进入 SessionExecutionState

backend/tests/agents/test_worker_emit.py
    # 删除只验证旧 Worker 输出 seam 的测试
```

---

## Task 1: 建立 resume → asset 的强类型调用注册表切片

**Files:**

- Create: `backend/career_os/platform/worker/models.py`
- Create: `backend/career_os/platform/worker/inputs.py`
- Create: `backend/career_os/platform/worker/outcomes.py`
- Create: `backend/career_os/platform/worker/bindings.py`
- Create: `backend/career_os/platform/worker/plan.py`
- Create: `backend/typecheck/worker_invocation_contracts.py`
- Modify: `backend/pyproject.toml`
- Modify: `backend/uv.lock`
- Modify: `backend/career_os/platform/worker/registry.py`
- Modify: `backend/career_os/platform/worker/__init__.py`
- Create: `backend/tests/platform/test_worker_invocation_registry.py`
- Reference: `backend/tests/platform/test_worker_registry.py`

**Interfaces:**

```python
class WorkerInvocationRegistry:
    def get_definition(
        self, worker_id: WorkerId, run_kind: str
    ) -> ResumeAssetWorkerRunDefinition: ...
    def build_llm_index(
        self,
        *,
        selectable_scopes: frozenset[ExecutionScope],
    ) -> list[dict[str, Any]]: ...
    def prepare(
        self,
        proposal: InvocationProposal,
        *,
        node_id: str,
        goal: str,
        target_scope: ExecutionScope,
        session_state: ResumeAssetSessionFacts,
        turn_request: ResumeAssetTurnRequest,
        required_outcomes: tuple[RequiredOutcome, ...],
    ) -> PreparedExecutionPlanNodeSpec: ...
    def resolve(
        self,
        spec: ResumeAssetPreparedExecutionPlanNodeSpec,
        *,
        source_results: tuple[ResumeAssetPlanNodeResult, ...],
    ) -> ResumeAssetWorkerInvocation: ...
    def validate_startup(self) -> None: ...
```

函数含义与作用：

- `get_definition`（获取动作定义）：在动态 Proposal seam 按 Worker 和 Run Kind 返回当前 resume/asset 内部切片联合中的唯一具体 Definition 子类；Task 4 建立 15 个具体类型后再发布最终 `AnyWorkerRunDefinition`。
- `ResumeAssetSessionFacts`（简历产物切片 Session 事实）与 `ResumeAssetTurnRequest`（简历产物切片请求）是 Tasks 1–3 的内部 frozen 测试切片，只包含构造这五个动作输入所需的具体字段；它们不得使用 `dict[str, Any]`，Task 4 发布最终 `SessionExecutionState/NewExecutionPlanTurnRequest` 后必须删除。
- `build_llm_index`（构建模型索引）：只投影 Harness 已判定为本轮可选择执行范围中的动作；范围由结构化 `list_type + phase` 表达，索引可以同时包含当前阶段和合法前向目标阶段，但不授予阶段转换权限。
- `prepare`（准备计划节点）：验证动作允许在已经验证的 `target_scope`（目标执行范围）执行，并验证 Gate，冻结当前输入候选与能力，生成不可执行的 Node Spec。
- `resolve`（物化 Worker 调用）：按 `RequiredOutcome.source_node_id` 从带来源身份的 `PlanNodeResult` 选择结果，调用强类型 binder 绑定具体 Outcome、校验完整输入并生成当前切片联合中的具体 Invocation。
- `validate_startup`（校验启动完整性）：在真实请求前发现重复或缺失定义。

- [ ] **Step 1: 写 resume/asset 注册表红灯测试**

至少增加以下行为测试：

```python
def test_resolve_resume_generation_freezes_validated_inputs(): ...
def test_resume_collection_does_not_expose_write_operation_or_skill(): ...
def test_prepare_asset_registration_does_not_invent_future_delivery(): ...
def test_prepare_freezes_prepared_inputs_from_later_session_mutation(): ...
def test_prepare_converts_nested_mutable_collections_to_immutable_values(): ...
def test_prepared_inputs_nested_values_cannot_be_mutated(): ...
def test_resolve_asset_registration_requires_bound_verified_delivery(): ...
def test_resolve_uses_required_source_node_when_outcome_types_match(): ...
def test_resolve_returns_concrete_register_outputs_invocation(): ...
def test_resolved_invocation_does_not_retain_mutable_source_references(): ...
def test_unknown_run_kind_is_rejected(): ...
def test_execution_scope_forbidden_run_kind_is_rejected(): ...
def test_definition_literal_fields_narrow_generic_parameters(): ...
def test_resume_asset_execution_strategies_are_explicit(): ...
```

断言使用公开字段，并验证具体 Invocation 的 `frozen=True` 与 `extra="forbid"`。测试必须同时直接尝试修改嵌套序列、集合和子模型，证明深冻结不变量成立；只验证 Session 后续变化没有影响快照，不足以证明 Invocation 不可变。在 `backend/typecheck/worker_invocation_contracts.py` 增加 `typing.assert_type`：证明按 `worker_id + run_kind` 分支后，resume generate 和 asset register 的 `inputs` 分别缩窄为 `GenerateOptimizedResumeInput` 与 `RegisterOutputsInput`；证明所有已解析集合字段静态缩窄为 `tuple`/`frozenset` 或 frozen 具体子模型；证明当前 `RESUME_ASSET_WORKER_RUN_DEFINITIONS` 是五个带 Literal discriminator 的具体 Definition 子类联合，且每个子类继承时保持各自五个具体泛型参数。最终 `ALL_WORKER_RUN_DEFINITIONS`、`AnyWorkerRunDefinition` 和 `WorkerInvocation` 闭合联合只能在 Task 4 全部 15 个具体类型齐备后发布。

运行：

```bash
cd backend && uv run pytest tests/platform/test_worker_invocation_registry.py -q
```

期望：因模型和接口尚不存在而失败。

- [ ] **Step 2: 定义最小领域模型和输入模型**

先实现 resume/asset 相关类型：

- `InvocationProposal`（调用提议）：只含 `worker_id`、`run_kind`。
- `PipelinePhase`（Pipeline 阶段）：只允许当前 `PIPELINE_PHASES` 中的闭合阶段值。
- `PipelineExecutionScope`（Pipeline 执行范围）：以 `list_type="pipeline" + phase` 同时表示 Pipeline 列表和具体阶段。
- `ExecutionScope`（执行范围）：本期等同 frozen 的 `PipelineExecutionScope`，供 Definition、Registry 与 ExecutionPlan 共用；`list_type="plan"` 不进入该类型，也没有 legacy Adapter。
- `SkillRequirement`（Skill 要求）：使用闭合的 Skill 名称与 mode 描述预加载要求；有 mode 的 Skill 必须显式提供 mode，无 mode 的 Skill 使用 `None`。
- `WorkerRunDefinition[TPreparedInput, TInput, TInvocation, TWorkerOutput, TOutcome]`（泛型动作定义基类）：静态关联准备输入、完整输入、具体 Invocation、具体 Worker 输出、允许 operation、Skill、执行策略、具体 Outcome 和成功契约。
- resume/asset 五个具体 Definition 子类：分别继承五参数完整的泛型基类，并把 `worker_id + run_kind` 声明为对应 Literal；不能只创建五个同一泛型基类的参数化 TypeAlias。
- `ResumeAssetWorkerRunDefinition`（内部切片动作定义联合）：只显式枚举本 Task 的五个具体 Definition 子类，用于 Tasks 1–3 验证机制；它不得导出为最终公开 `AnyWorkerRunDefinition`。
- `OutcomeDefinition[TOutcome]`（结果定义）：固定具体输出模型，Outcome 名称从该模型的 `outcome_name: ClassVar[Literal[...]]` 派生，避免名称与模型配错。
- `OutcomeBinding[TOutcome, TPreparedInput, TInput]`（结果绑定）：用有类型签名的 binder 把上游具体 Outcome 和下游准备输入转换为下游完整输入。
- `RequiredOutcome`（必需结果）：只保存上游 node_id、稳定 `binding_id` 和最小数量，不保存动态目标字段字符串。
- `ResumeAssetPlanNodeResult`（内部切片节点结果）：先建立 Plan/节点/Worker Run 身份、闭合终态与 resume/asset 具体 Outcome tuple，供 `resolve()` 在 Tasks 1–3 正确验证 `source_node_id`；Task 3 再把它接入切片 ExecutionPlan 状态机，Task 4 用完整 Outcome 联合发布最终 `PlanNodeResult`。
- `ExecutionPlanNodeSpec[TPreparedInput]`（计划节点规格）：冻结具体准备输入、能力快照与 Required Outcome 来源，但不可交给 Runner。
- `WorkerInvocationBase`（调用公共字段）以及 resume/asset 五个具体 Invocation 类；Tasks 1–3 使用内部 `ResumeAssetWorkerInvocation` 联合，最终公开 `WorkerInvocation` 留给 Task 4 一次性建立。
- `CollectOptimizationLevelsInput`（收集档位输入）。
- `GenerateOptimizedResumeInput`（生成优化简历输入）。
- `ReuseOutputsInput`（复用建议输入）。
- `RegisterOutputsInput`（登记产物输入）。
- `DeleteOutputInput`（删除产物输入）。

所有 Artifact 使用稳定引用或经过验证的结构化 delivery，不把 `prior_results` 摘要当成 Required Outcome。

所有 PreparedInput、完整 Input、WorkerStructuredOutput 和 VerifiedOutcome 模型必须使用统一的不可变模型约束：

- Pydantic 模型及其所有具体子模型使用 `ConfigDict(frozen=True, extra="forbid")`；
- 有序集合字段声明为 `tuple[T, ...]`，无序集合字段声明为 `frozenset[T]`；
- 已解析业务事实不得声明为 `list`、`dict`、`set`、`MutableSequence` 或 `MutableMapping`；
- 需要键值结构时定义具名 frozen 子模型，不能以 `dict[str, Any]` 逃逸；
- 从 Session、request context、Worker JSON 或 Tool 结果进入已解析 seam 时，必须重新构造具体模型，不能依赖 `model_copy(deep=True)` 或普通深拷贝冒充不可变性；
- binder 和状态转换只创建新模型，不原地修改输入模型。

在 `backend/pyproject.toml` 增加 Pyright 开发依赖和 `typeCheckingMode = "strict"`。第一版检查范围至少覆盖：

```text
career_os/platform/worker/
career_os/agents/graphs/workers/
career_os/harness/delegate.py
typecheck/
```

若现有文件阻止一次性重写完成，只允许按具体诊断在文件内消除类型问题；不得用全局 `ignore`、`typeCheckingMode = "basic"` 或把新 seam 排除出检查范围。

- [ ] **Step 3: 深化 WorkerRegistry 为代码注册表**

在 `registry.py` 内登记 resume/asset 五种动作并实现五个公开方法。不要让调用方读取内部 `_definitions`。

`prepare()` 必须：

1. 查找唯一动作定义；
2. 校验动作允许在 `target_scope`（已验证的目标执行范围）执行；不得接受 `pipeline/explore` 复合字符串或把裸 `None` 同时解释为列表类型与阶段；
3. 校验 Gate；
4. 从 Session 与 request context 复制当前业务事实，重新校验并构造只含 tuple、frozenset 与 frozen 具体子模型的 PreparedInput；不得保留调用方 list/dict/set 或可变子模型引用；
5. 保存 Builder 提供的 Required Outcome 输入绑定；
6. 冻结 allowed operations、结构化 required/optional Skill Requirement、`execution_strategy + deterministic_adapter_id`、成功契约和 Judge 模式；
7. 生成稳定 `node_id` 对应的 ExecutionPlanNodeSpec，不生成 `invocation_id`。

`resolve()` 必须：

1. 只接受 `ExecutionPlanNodeSpec` 与带 `plan_id + node_id + worker_run_id` 来源身份的 `PlanNodeResult`；
2. 按 `source_node_id + binding_id` 从 `source_results` 查找每个 Required Outcome 需要的具体 Outcome，不能接收脱离来源的 Outcome tuple；
3. 校验 `minimum` 并调用注册的 `OutcomeBinding.bind`；
4. binder 合并 Node Spec 的 `prepared_inputs` 与具体 Outcome，返回定义声明的完整输入模型；
5. 生成稳定前缀的 `invocation_id`，并保证 `invocation.node_id == spec.node_id`；
6. 缺少、为空、类型错误或无法绑定的 Outcome 必须失败，禁止从 `prior_results`、context 或默认值补齐。

`resolve()` 是 Invocation 的唯一创建入口。没有 Required Outcome 的 resume 节点可以在 Plan 初始化时以空 `source_results` 立即调用；asset 节点必须等上游结果后调用。Tasks 1–3 的返回值属于内部 slice 联合，Task 4 发布最终 `WorkerInvocation` 后替换该别名；解析成功后的 Runner、Contract 和 Plan binder 不得重新退化为 `Any`、裸 `BaseModel inputs` 或字符串结果字典。

- [ ] **Step 4: 转绿并跑现有注册表测试**

```bash
cd backend && uv run pytest \
  tests/platform/test_worker_invocation_registry.py \
  tests/platform/test_worker_registry.py -q
uv run pyright
```

期望：新测试通过；依赖旧 JSON Registry 契约的测试直接重写或删除，不建立兼容投影。

---

## Task 2: 建立 resume → asset 的确定性 Success Contract

**Files:**

- Create: `backend/career_os/platform/worker/contracts.py`
- Modify: `backend/career_os/platform/worker/outcomes.py`
- Modify: `backend/typecheck/worker_invocation_contracts.py`
- Modify: `backend/career_os/platform/worker/__init__.py`
- Modify: `backend/career_os/platform/worker/registry.py`
- Create: `backend/tests/platform/test_worker_success_contract.py`
- Reference: `backend/career_os/agents/schemas/workers.py`
- Reference: `backend/career_os/platform/tool/handlers/resume_html.py`

**Interfaces:**

```python
class ContractSatisfied(BaseModel, Generic[TOutcome]):
    model_config = ConfigDict(frozen=True, extra="forbid")

    satisfied: Literal[True]
    verified_outcomes: tuple[TOutcome, ...]
    violations: tuple[()] = ()


class ContractUnsatisfied(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    satisfied: Literal[False]
    verified_outcomes: tuple[()] = ()
    violations: tuple[str, ...]


ContractEvaluation: TypeAlias = (
    ContractSatisfied[TOutcome] | ContractUnsatisfied
)


class SuccessContract(
    Protocol,
    Generic[TInvocation, TWorkerOutput, TOutcome],
):
    def evaluate(
        self,
        invocation: TInvocation,
        structured_output: TWorkerOutput,
    ) -> ContractEvaluation[TOutcome]: ...


class DeterministicSuccessContractRegistry:
    def evaluate(
        self,
        invocation: ResumeAssetWorkerInvocation,
        structured_output: ResumeAssetWorkerStructuredOutput,
    ) -> ContractEvaluation[ResumeAssetVerifiedOutcome]: ...

    def validate_startup(
        self,
        definitions: tuple[ResumeAssetWorkerRunDefinition, ...],
    ) -> None: ...
```

函数和字段含义与作用：

- `ContractEvaluation[TOutcome]`（泛型确定性契约验收结果）：只表达代码可以确认的业务完成事实，并把成功时允许返回的具体 Outcome 类型编码到签名中。
- `satisfied`（是否满足）：`Literal[True] | Literal[False]` discriminator，供 Pyright 缩窄成功和不满足分支。
- `verified_outcomes`（已验证结果）：只保存契约确认且由 WorkerRunDefinition 声明的具体 `VerifiedOutcome`，供 ExecutionPlan 消费。
- `violations`（契约违反原因）：保存稳定内部原因，例如空交付物、路径不存在、HTML 不完整或档位不一致。
- `SuccessContract.evaluate`（执行具体契约）：静态关联具体 Invocation、具体 Worker 结构化输出和允许产生的具体 Outcome。
- `DeterministicSuccessContractRegistry.evaluate`（分派契约）：按闭合 Invocation 联合选择具体契约，验收结构化输出与本地 Artifact 事实并返回闭合 Outcome 联合。
- `validate_startup`（校验契约目录）：拒绝缺失或重复契约、未声明 Outcome 和契约产出名称越界。

Registry 构造时注入 Artifact/Index verifier Adapter，不自行创建文件系统、Store 或 Harness；本 plan 复用现有本地校验实现，后续全局失败 plan 可以注入由 OperationResult/运行证据支持的 Adapter，而不替换契约 Registry。

- [ ] **Step 1: 写 resume/asset 契约红灯测试**

至少覆盖：

```python
def test_completed_resume_with_empty_deliveries_is_unsatisfied(): ...
def test_resume_with_missing_file_does_not_emit_verified_outcome(): ...
def test_resume_delivery_outside_output_root_is_unsatisfied(): ...
def test_resume_delivery_via_symlink_outside_output_root_is_unsatisfied(): ...
def test_resume_with_invalid_html_does_not_emit_verified_outcome(): ...
def test_resume_with_level_mismatch_does_not_emit_verified_outcome(): ...
def test_valid_resume_emits_verified_html_deliveries(): ...
def test_contract_returns_typed_verified_html_deliveries_outcome(): ...
def test_contract_cannot_emit_undeclared_outcome(): ...
def test_mismatched_invocation_and_output_is_rejected_before_handler(): ...
def test_missing_contract_blocks_startup(): ...
```

测试使用 `tmp_path` 创建真实 HTML Artifact，通过 `evaluate()` 的公开返回值断言；不得直接测试私有 handler 字典。

- [ ] **Step 2: 实现 ContractEvaluation 与代码契约注册表**

Registry 必须：

1. 按 `invocation.success_contract_id` 选择唯一确定性契约；
2. 穷尽式缩窄闭合 Invocation 与 WorkerStructuredOutput 联合，只把同一 Definition 的具体类型组合传给具体 SuccessContract；不匹配组合在 handler 前失败；
3. 拒绝契约输出 WorkerRunDefinition 未声明的 Outcome 模型；
4. 验收失败时返回 `satisfied=False`、空 `verified_outcomes` 和稳定 `violations`；
5. 不执行重试、不分类 Failure、不调用 Judge、不决定 `partial_success` 或 `outcome_unknown`。

分派末尾使用 `assert_never()`；在 typecheck fixture 中证明漏掉新 Invocation、Worker 输出或 Outcome 变体会使 Pyright 失败。

- [ ] **Step 3: 实现 resume → asset 最小契约切片**

`resume.generate_optimized_resume` 至少检查：

- delivery 数量不少于 Invocation 请求的档位数量，且至少为一；
- 路径真实存在；分别规范化允许输出根目录与交付物真实路径后，交付物仍位于根目录内，拒绝 `..` 路径穿越和解析到根目录外的符号链接；
- 文件通过完整 HTML 文档校验；
- delivery 档位与 Invocation 冻结输入一致；
- 全部通过后才产生 `VerifiedHtmlDeliveriesOutcome`；其 `name` 固定为 `Literal["verified_html_deliveries"]`，`value` 固定为 `tuple[VerifiedHtmlDelivery, ...]`。

同时为本 Task 已登记的其余 resume/asset Run Kind 提供最小确定性契约；任何契约都不能把 Pydantic Schema 通过或旧 `completed` 状态直接当作 verified Outcome。

- [ ] **Step 4: 转绿**

```bash
cd backend && uv run pytest \
  tests/platform/test_worker_success_contract.py \
  tests/platform/test_worker_invocation_registry.py \
  tests/harness/test_outputs_scan.py -q
uv run pyright
```

---

## Task 3: 用 ExecutionPlan 表达 resume → asset 真实依赖

**Files:**

- Modify: `backend/career_os/platform/worker/plan.py`
- Create: `backend/tests/platform/test_execution_plan.py`
- Modify: `backend/career_os/platform/worker/bindings.py`
- Modify: `backend/typecheck/worker_invocation_contracts.py`
- Modify: `backend/career_os/platform/worker/__init__.py`

**Interfaces:**

```python
PlanNodeTerminalStatus: TypeAlias = Literal[
    "success",
    "partial_success",
    "needs_additional_input",
    "failed",
    "outcome_unknown",
    "cancelled",
    "superseded",
    "interrupted",
]


class ResumeAssetPlanNodeResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    plan_id: Annotated[str, Field(min_length=1)]
    node_id: Annotated[str, Field(min_length=1)]
    worker_run_id: Annotated[str, Field(min_length=1)]
    status: PlanNodeTerminalStatus
    verified_outcomes: tuple[ResumeAssetVerifiedOutcome, ...] = ()


class PlanAdvanceError(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: Literal[
        "plan_id_mismatch",
        "mapping_key_mismatch",
        "unknown_result_node",
        "node_not_running",
        "result_already_persisted",
        "worker_run_id_mismatch",
    ]
    mapping_key: str
    expected_plan_id: str
    actual_plan_id: str
    result_node_id: str
    expected_worker_run_id: str | None = None
    actual_worker_run_id: str


class PlanAdvanced(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    advanced: Literal[True]
    plan: ExecutionPlan
    consumed_node_ids: tuple[str, ...]


class PlanAdvanceRejected(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    advanced: Literal[False]
    plan: ExecutionPlan
    errors: Annotated[tuple[PlanAdvanceError, ...], Field(min_length=1)]


PlanAdvanceResult: TypeAlias = Annotated[
    PlanAdvanced | PlanAdvanceRejected,
    Field(discriminator="advanced"),
]


class ExecutionPlanBuilder:
    def build(
        self,
        proposals: tuple[InvocationProposal, ...],
        *,
        turn_run_id: str,
        target_scope: ExecutionScope,
        session_state: ResumeAssetSessionFacts,
        turn_request: ResumeAssetTurnRequest,
    ) -> PlanBuildResult: ...


class ExecutionPlanExecutor:
    def advance(
        self,
        plan: ExecutionPlan,
        results: Mapping[str, ResumeAssetPlanNodeResult],
    ) -> PlanAdvanceResult: ...

    def claim_next(
        self,
        plan: ExecutionPlan,
        *,
        worker_run_id: str,
    ) -> PlanClaimResult: ...
```

- `PlanBuilt`（计划已构建）：`built=True`，携带全部验证通过且可采用的不可变 ExecutionPlan。
- `PlanBuildRejected`（计划构建被拒绝）：`built=False`，不携带 Plan，保存至少一个闭合 `PlanBuildError`；错误码覆盖 Proposal、阶段、Gate、输入来源、Definition、binding、依赖歧义/环、跨 Gate 和写顺序。
- `PlanBuildResult`（计划构建结果）：以 `built` 区分上述两个分支；Coordinator 只有在 `PlanBuilt` 分支才能提交阶段推进。
- `build`（构建计划）：使用已经通过 selectable scopes 校验的 `target_scope` 准备 Node Spec、补充依赖与 Outcome 输入绑定、校验图，并只物化输入已经完整的 Invocation；`target_scope` 同时冻结任务列表类型和 Pipeline 阶段，禁止以 `pipeline/explore` 复合字符串或裸 `None` 表达范围。构建本身不提交阶段推进，任何错误都返回 `PlanBuildRejected`，不能抛出业务异常或返回带 invalid 节点的 Plan。
- `ResumeAssetPlanNodeResult`（切片计划节点结果）：冻结计划编号、节点编号、产生结果的 Worker Run 编号、闭合终态以及 `tuple[ResumeAssetVerifiedOutcome, ...]`；Task 4 再以完整 Outcome 联合发布最终 `PlanNodeResult`。
- `PlanAdvanceError`（计划推进错误）：使用闭合错误码保存 mapping key、结果节点编号以及期望/实际 Worker Run 编号，避免自由文本错误进入控制流。
- `PlanAdvanceResult`（计划推进结果）：以 `advanced` 判别成功或拒绝；成功返回新 Plan 和已消费节点，拒绝返回原 Plan 和非空结构化错误。
- `advance`（推进计划）：本批 mapping 只含新完成的 running 节点结果；先验证身份与尚未持久化结果，全部通过后才把结果写入节点并原子完成 `running → finished`，再从 Plan 中全部 finished 节点的持久化结果绑定下游输入、物化 Invocation。任一身份或重放错误返回原 Plan；方法不选择执行节点，也不产生新的 running 状态。
- `claim_next`（原子认领下一个节点）：按拓扑层级和 `order` 选择唯一 ready 节点，在同一个 Plan 状态转换中绑定 `worker_run_id`、完成 `ready → running` 并返回唯一 `PlanDispatch`。
- `PlanClaimResult`（计划认领结果）：同时携带更新后的 Plan 与可选 `PlanDispatch`；dispatch 中的 plan_id、node_id、Invocation 和 worker_run_id 必须与更新后的 running 节点完全一致。

- [ ] **Step 1: 写依赖与调度红灯测试**

覆盖：

- resume 与 asset 同时进入 Plan；
- resume 初始已物化 Invocation 且 ready；
- asset 初始只有 Node Spec、`invocation is None` 且 blocked；
- 模型不能提供或覆盖 `depends_on`；
- Required Outcome 引用 `bind.resume_verified_html_to_asset_register`，不保存 `target_input_field: str`；
- `bind_verified_html_deliveries(prepared, outcome)` 的静态返回类型是 `RegisterOutputsInput`；
- resume success 且 `VerifiedHtmlDeliveriesOutcome.value >= 1` 后，asset 输入校验通过、Invocation 被物化并 ready；
- resume 非 success 或 Outcome 为空时 asset `blocked_by_upstream`；
- Outcome 类型与 binding 声明不匹配、binding 不存在或目标模型不匹配时 Plan invalid，且不创建 asset Invocation；
- 两个上游都产生同一 Outcome 类型时，Required Outcome 仍按 `source_node_id` 绑定指定来源，不能按类型或 tuple 顺序任选；
- 重复 advance 不会为同一个 asset 节点生成第二个 Invocation；
- advance 不会把 ready 节点转换为 running，也不会返回可执行 dispatch；
- claim_next 原子完成唯一节点的选择、`ready → running`、worker_run_id 绑定和 dispatch 生成；
- ExecutionPlan 与 ExecutionPlanNode 都是 frozen + extra forbid；claim 返回新 Plan，原 Plan 仍保持 ready 且 worker_run_id 为空；
- ExecutionPlan、ExecutionPlanNode、Node Spec、Invocation、`ResumeAssetPlanNodeResult` 与切片 Outcome 的嵌套业务值全部满足深冻结不变量；直接修改嵌套集合或子模型失败，原 Plan 快照不变；
- 采用 claim 返回的新 Plan 后再次 claim，不会在已有 running 节点时返回第二个 dispatch；
- 空 worker_run_id、Plan 内重复 worker_run_id 或没有 ready 节点时 claim 失败且 Plan 不变；
- 结果 plan_id 与当前 Plan 不同、mapping key 与结果 node_id 不同、结果节点不存在、节点不是 running 或 worker_run_id 不匹配时，advance 返回对应闭合错误码，拒绝整批结果且 Plan 不变；
- finished 节点必须持有身份完全匹配的 `result`，其他状态不得持有结果；
- A、B 两个上游在不同 advance 调用完成的 fan-in 场景中，B 完成时只提交 B 的新结果，Executor 仍从 Plan 读取 A 已持久化结果并物化下游；
- 对 finished 节点重放相同或不同结果都返回 `result_already_persisted`，第一次结果不被覆盖；
- 一批结果中只要一个身份校验失败，其余合法结果也不被消费；修正错误后可使用原 Plan 重放整批结果；
- `ResumeAssetPlanNodeResult` 拒绝空 plan_id、空 node_id、空 worker_run_id、非终态状态和未知字段；
- `partial_success` 默认不解除依赖，只有下游 Definition 显式接受其具体 Outcome 时才允许绑定；
- asset materialize 不读取 `prior_results.resume`、运行时 context 或业务默认值；
- 被阻断的 asset 不产生 `worker_run_id`；
- 环、未知 Outcome、跨 Gate 动作和重复 order 被拒绝。
- 合法输入返回 `PlanBuilt`；上述任一构建错误返回不含 Plan 的 `PlanBuildRejected`，错误码和 Proposal/节点/Definition 身份可被公开断言。

运行：

```bash
cd backend && uv run pytest tests/platform/test_execution_plan.py -q
```

期望：红灯。

- [ ] **Step 2: 实现不可变计划模型与依赖规则**

复用 Task 1 已定义的 `RequiredOutcome` 和 `ExecutionPlanNodeSpec`，实现：

- `ExecutionPlanNode`（计划节点）：使用 `frozen=True, extra="forbid"`，切片阶段增加 `result: ResumeAssetPlanNodeResult | None`；其嵌套 Spec、Invocation 和结果只引用深冻结模型，Task 4 再替换为最终 `PlanNodeResult`；
- `ExecutionPlan`（执行计划）：使用 `frozen=True, extra="forbid"`，以 `execution_scope: ExecutionScope` 冻结任务列表类型和可选 Pipeline 阶段，`nodes` 使用 tuple，所有状态转换返回新 Plan，不原地修改任一嵌套节点；
- `PlanDependencyRule`（依赖规则）；
- `PlanDispatch`（计划派发命令）：冻结 plan_id、node_id、具体 Invocation 与 worker_run_id；
- `PlanClaimed` / `PlanNotClaimed`（已认领/未认领结果）：以 `claimed` 判别，未认领原因使用闭合 Literal；
- `PlanClaimResult`（计划认领结果）：上述两种结果的闭合联合；
- `ResumeAssetPlanNodeResult`（切片计划节点结果）：冻结 plan_id、node_id、worker_run_id、闭合终态和 resume/asset 具体 Outcome 联合；
- `PlanAdvanceError`（计划推进错误）：使用闭合身份错误码，不向控制流暴露自由文本；
- `PlanAdvanced` / `PlanAdvanceRejected`（已推进/拒绝推进结果）：以 `advanced` 判别，拒绝时返回原 Plan 和非空错误集合；
- `PlanAdvanceResult`（计划推进结果）：上述两个推进分支的闭合联合；
- `PlanBuildError`（计划构建错误）、`PlanBuilt` / `PlanBuildRejected`（已构建/构建拒绝）和 `PlanBuildResult`（计划构建结果）：以 `built` 判别，拒绝分支不携带 Plan；
- `InvocationSchedulingStatus`（调度状态）。

`PlanBuildResult` 必须显式定义为闭合判别联合：

```python
PlanBuildResult: TypeAlias = Annotated[
    PlanBuilt | PlanBuildRejected,
    Field(discriminator="built"),
]
```

`PlanBuilt`（计划已构建）只在全部校验通过时携带 `ExecutionPlan`；`PlanBuildRejected`（计划构建被拒绝）携带至少一个结构化错误且没有 Plan，禁止返回半有效计划。

第一条依赖规则固定为：

```text
asset.register_outputs
depends_on resume.generate_optimized_resume
binding_id = bind.resume_verified_html_to_asset_register
source = VerifiedHtmlDeliveriesOutcome
prepared input = RegisterOutputsPreparedInput
full input = RegisterOutputsInput
minimum=1
```

- [ ] **Step 3: 实现 Builder 与串行 Executor**

Builder 负责：

1. 为每个 Proposal 分配稳定 `node_id`；
2. 把动作级依赖模板解析为当前 Plan 的真实 `source_node_id`；
3. 调用 Registry `prepare()` 生成 Node Spec；
4. 校验 `binding_id`、binding 的来源/目标模型、图和顺序；
5. 对没有未满足 Required Outcome 的节点调用 `resolve()`，生成初始 ready Invocation；
6. 对依赖未来 Outcome 的节点保留 `invocation=None` 和 blocked；
7. 全部验证成功时返回 `PlanBuilt`；任一 Proposal、阶段、Gate、输入、binding 或图错误时聚合为 `PlanBuildRejected`，不返回部分 Plan。

Executor 负责：

1. 先校验本批全部 `ResumeAssetPlanNodeResult`：plan_id 等于当前 Plan、mapping key 等于 node_id、节点存在且为 running、节点尚无 result、worker_run_id 等于认领时冻结编号；任一错误都返回 `PlanAdvanceRejected` 和原 Plan，不消费任何结果；
2. 把本批合法结果持久化到对应节点并完成 `running → finished`，后续推进不要求调用方再次提交；
3. 从更新后 Plan 的全部 finished 节点读取带来源身份的 `ResumeAssetPlanNodeResult`，按 `RequiredOutcome.source_node_id` 校验来源和数量，再调用 Registry `resolve(spec, source_results=...)`；
4. 只有 resolve 成功后才把节点转换为 ready；
5. 上游不成功或 Outcome 缺失时转换为 blocked_by_upstream；
6. 保证同一节点只物化一次，重复 advance 返回同一 Invocation；
7. 全部结果身份校验通过后，`advance()` 返回 `PlanAdvanced`，其中包含持久化结果及重新计算状态的新 Plan和已消费节点编号；它不返回 dispatch，也不产生新的 running 状态；
8. `claim_next()` 按拓扑层级和 `order` 唯一排序，在一个不可分割的状态转换中选择一个 ready 节点、绑定非空且 Plan 内唯一的 `worker_run_id`、转换为 running，并返回与该节点一致的 `PlanDispatch`；
9. Plan 已有 running 节点时不认领其他节点；对 claim 后的新 Plan 重复调用不产生第二个 dispatch。

Coordinator 不自行绑定 Outcome、读取依赖字典、构造 WorkerInvocation，或分别改写节点的 scheduling_status 与 worker_run_id。调用方必须先采用 `PlanClaimResult.plan`，再使用同一结果中的 `PlanDispatch` 启动 Worker。

- [ ] **Step 4: 转绿**

```bash
cd backend && uv run pytest \
  tests/platform/test_execution_plan.py \
  tests/platform/test_worker_invocation_registry.py -q
uv run pyright
```

---

## Task 4: 在重写 Runner 与 Coordinator 前建立全部 15 个具体类型

**Files:**

- Modify: `backend/career_os/platform/worker/inputs.py`
- Create: `backend/career_os/platform/worker/profile_patches.py`
- Modify: `backend/career_os/platform/worker/models.py`
- Modify: `backend/career_os/platform/worker/outcomes.py`
- Modify: `backend/career_os/platform/worker/bindings.py`
- Modify: `backend/career_os/platform/worker/registry.py`
- Modify: `backend/career_os/platform/worker/contracts.py`
- Modify: `backend/career_os/platform/worker/plan.py`
- Modify: `backend/career_os/platform/worker/__init__.py`
- Create: `backend/career_os/platform/worker/requests.py`
- Modify: `backend/typecheck/worker_invocation_contracts.py`
- Add: `backend/career_os/platform/prompt/{identity,capability,market,opportunity,strategy}/runs/*.md`
- Create: `backend/career_os/platform/prompt/{identity,capability,market,opportunity,strategy}/invocation_system.md`
- Modify: `.agent/skills/career-inner-exploration/SKILL.md`
- Modify: `.agent/skills/career-jd-alignment/SKILL.md`
- Modify: `backend/tests/platform/test_worker_invocation_registry.py`
- Modify: `backend/tests/platform/test_worker_success_contract.py`
- Create: `backend/tests/platform/test_profile_patch_types.py`

本 Task 是后续统一 Runner、delegate、Coordinator 和 API 重写的硬前置。Tasks 1–3 只允许使用 `ResumeAssetWorkerInvocation` 与 `ResumeAssetWorkerRunDefinition` 内部切片别名；本 Task 必须删除这些临时别名并一次发布全部最终闭合联合。`requests.py` 同时发布 `InvocationAuthorizationFacts`（委托授权事实投影）和 `SessionRoutingFacts`（阶段路由事实投影）两个 frozen、`extra="forbid"` 的窄读模型，供 Task 6–7 在完整 Session 聚合发布前读取确定性事实；它们不是持久化模型或第二事实源，Task 8 发布 `SessionExecutionState` 后由聚合显式投影生成。

`strategy.career_plan` 不属于上述目录，本 Task 不创建它的 PreparedInput、Invocation、Definition、Prompt、Contract、ProfilePatch 或测试占位，也不建立 legacy Adapter。旧纯规划入口在本次系统重写中删除；后续 v2.2 独立 Spec/Plan 再扩展闭合联合并直接接入 pipeline。

本 Task 直接把基础 Prompt 重写为唯一 `invocation_system.md`，动作内容写入 `runs/<run_kind>.md`，并删除旧 `system.md` 与旧 loader 的运行时读取。业务 `SKILL.md` 同步完成职责清理；中间态不要求旧 Runner 或旧测试继续可运行。

- [ ] **Step 1: 为 15 行目录写完整性与静态类型红灯测试**

测试必须按 spec 第 7.1 节逐行验证下列具体类型目录，字段名、可选性、tuple/frozen 约束和确定性契约条件不得在实现时另行猜测：

| Worker.Run Kind | PreparedInput → Input | Invocation / WorkerStructuredOutput | VerifiedOutcome |
|---|---|---|---|
| `identity.exploration_first` | `ExplorationFirstPreparedInput` → `ExplorationFirstInput` | `ExplorationFirstInvocation` / `ExplorationFirstOutput` | `ExplorationDraftOutcome` |
| `identity.exploration_revisit` | `ExplorationRevisitPreparedInput` → `ExplorationRevisitInput` | `ExplorationRevisitInvocation` / `ExplorationRevisitOutput` | `ExplorationDraftOutcome` |
| `capability.exploration_first` | `CapabilityExplorationPreparedInput` → `CapabilityExplorationInput` | `CapabilityExplorationInvocation` / `CapabilityExplorationOutput` | `BankDeltaOutcome` |
| `capability.exploration_revisit` | `CapabilityRevisitPreparedInput` → `CapabilityRevisitInput` | `CapabilityRevisitInvocation` / `CapabilityRevisitOutput` | `BankDeltaOutcome` |
| `capability.jd_bank_deep_dive` | `JdBankDeepDivePreparedInput` → `JdBankDeepDiveInput` | `JdBankDeepDiveInvocation` / `JdBankDeepDiveOutput` | `BankDeltaOutcome` |
| `market.propose_plan` | `MarketPlanProposalPreparedInput` → `MarketPlanProposalInput` | `MarketPlanProposalInvocation` / `MarketPlanProposalOutput` | `MarketPlanProposalOutcome` |
| `market.revise_plan` | `MarketPlanRevisionPreparedInput` → `MarketPlanRevisionInput` | `MarketPlanRevisionInvocation` / `MarketPlanRevisionOutput` | `MarketPlanProposalOutcome` |
| `market.start_research` | `MarketResearchStartPreparedInput` → `MarketResearchStartInput` | `MarketResearchStartInvocation` / `MarketResearchAcceptedOutput` | `JobAcceptedOutcome` |
| `opportunity.evaluate` | `OpportunityEvaluationPreparedInput` → `OpportunityEvaluationInput` | `OpportunityEvaluationInvocation` / `OpportunityEvaluationOutput` | `OpportunityAssessmentOutcome` |
| `strategy.jd_application` | `JdApplicationStrategyPreparedInput` → `JdApplicationStrategyInput` | `JdApplicationStrategyInvocation` / `JdApplicationStrategyOutput` | `StrategyArtifactOutcome \| OptimizeTransitionOutcome` |
| `resume.collect_optimization_levels` | `CollectOptimizationLevelsPreparedInput` → `CollectOptimizationLevelsInput` | `CollectOptimizationLevelsInvocation` / `OptimizationLevelRequestOutput` | `OptimizationLevelRequestOutcome` |
| `resume.generate_optimized_resume` | `GenerateOptimizedResumePreparedInput` → `GenerateOptimizedResumeInput` | `GenerateOptimizedResumeInvocation` / `GenerateOptimizedResumeOutput` | `VerifiedHtmlDeliveriesOutcome` |
| `asset.reuse_outputs` | `ReuseOutputsPreparedInput` → `ReuseOutputsInput` | `ReuseOutputsInvocation` / `ReuseOutputsOutput` | `ReuseRecommendationOutcome` |
| `asset.register_outputs` | `RegisterOutputsPreparedInput` → `RegisterOutputsInput` | `RegisterOutputsInvocation` / `RegisterOutputsOutput` | `RegisteredDeliveriesOutcome` |
| `asset.delete_output` | `DeleteOutputPreparedInput` → `DeleteOutputInput` | `DeleteOutputInvocation` / `DeleteOutputOutput` | `DeletedOutputOutcome` |

每行还必须具有独立的具体 Node Spec、带 Literal `worker_id + run_kind` 的具体 `WorkerRunDefinition` 子类、`SuccessContract`、允许执行范围、operation、required/optional Skill、`execution_strategy`、可选 `deterministic_adapter_id` 与 Run Kind Prompt。`typing.assert_type` 必须覆盖全部 15 个 Definition 和 Invocation 的 `worker_id + run_kind` 分支，而不是只抽样 resume/asset。

执行策略固定为：

- deterministic：`market.start_research`、`resume.collect_optimization_levels`、`asset.register_outputs`、`asset.delete_output`，Adapter 编号分别使用同名稳定编号；
- ReAct：其余 11 个 Run Kind，`deterministic_adapter_id=None`。

本 Task 的目录结构测试只负责拒绝 ReAct 动作携带 Adapter 编号以及 deterministic 动作缺少 Adapter 编号。这里验证 Definition 的执行策略与稳定 Adapter 编号关系，不提前测试 Runner 分派、Harness 绕过或生产 Adapter 是否存在：`DeterministicWorkerAdapterRegistry` 和 `WorkerExecutionResult` 由 Task 5 建立，市场与产物生产 Adapter 分别在 Task 9、Task 10 依赖就绪后接线，Task 11 再统一拒绝未知/重复 Adapter 编号和绕过 Definition 的运行路径。

`market.start_research` 另增加红灯测试：输入必须是包含 `confirmation_id + plan_id + plan_version + plan_hash + confirmed_at + session_id` 的 `MarketPlanConfirmationRef`；原始 `MarketResearchAcceptedOutput` 不能绕过 Contract 直接构造 PlanNodeResult；确认不存在、跨 Session、版本或摘要错配、Job 未持久化或 job/plan/confirmation 身份错配时契约不满足；验证通过时产生 `JobAcceptedOutcome`。Task 5 建立 `WorkerExecutionAcceptedAsync` 传输分支后，再验证该状态本身不能直接成为 Plan 结果。

`asset.reuse_outputs` 另增加红灯测试：输出只能包含 `recommendation`，不能包含 `gate_prompt`、eligible candidates 或用户选择；推荐的 `output_id` 不属于 Invocation candidates 或理由为空时契约不满足；合法建议产生的 `ReuseRecommendationOutcome.eligible_candidates` 只能由 Contract 从 Invocation 冻结输入复制，不能信任 Worker 回传候选；Contract 不修改 Session 或创建 Gate。

所有写 Profile 的变体另增加红灯测试：identity 只能使用 `ExplorationProfilePatch`，capability 只能使用 `ExperienceBankProfilePatch`，opportunity 只能使用 `OpportunityAssessmentProfilePatch`，strategy.jd_application 只能使用 `JdStrategyProfilePatch`，resume generate 只能使用 `ResumeOptimizationProfilePatch`。错误 `patch_kind/value` 组合必须在输出解析 seam 失败；`typing.assert_type` 按 discriminator 缩窄具体 `value`，解析后的 Invocation/输出/Contract 链路不得出现任意 JSON。

- [ ] **Step 2: 逐行实现具体字段、契约和 Prompt**

按上表顺序逐个做红 → 绿。每个切片必须完整实现 spec 第 7.1 节规定的字段，并验证：

- PreparedInput 只含 Plan 创建时已有事实，完整 Input 才包含绑定后的 Required Outcome；
- PreparedInput、Input、Node Spec、Invocation、WorkerStructuredOutput 和 Outcome 均深冻结；
- 具体 Contract 只能产生 Definition 声明的 Outcome；
- 基础 Prompt 与 Skill 正文不重新猜测 Run Kind/required Skill mode，不要求加载 required Skill，不承担其他 Worker 职责；
- ReAct 动作的 Prompt 只描述允许能力与决策原则，不把 operation 固化为执行队列；
- `asset.reuse_outputs` Prompt 只要求模型形成候选范围内的复用建议，不要求输出 `reuse_confirm` 或推测用户将选择跳过、增量优化还是新建完整优化；Gate 由 Task 9 的 Harness interface 从已验证 Outcome 创建；
- `market.start_research` 在本 Task 只建立具体输入、输出、Outcome、Definition 与 Contract 类型，并固定生产 Adapter 编号；Task 9 在市场 confirmation 持久化依赖就绪后实现并接线该 Adapter。最终行为必须是：Adapter 执行唯一已授权 operation，把 Tool 接收结果与已持久化后台任务引用解析为 `WorkerExecutionAcceptedAsync(MarketResearchAcceptedOutput(job_id, plan_id, confirmation_id, accepted_at))`；Contract 验证任务/plan/confirmation 身份后产生 `JobAcceptedOutcome`，当前 Worker Run 立即 success，现有 `MarketResearchRunner` 独立继续，禁止等待后台任务终态；
- `profile_patches.py` 一次性建立五个 frozen + extra-forbid 具体补丁模型和按 `patch_kind` 判别的闭合联合；Harness 的 Profile Adapter 负责转换到现有存储接口，不能把通用 `path/op/value` 暴露回 Worker seam。

- [ ] **Step 3: 发布最终闭合联合并删除切片别名**

一次性建立并导出：

```python
PreparedExecutionPlanNodeSpec
WorkerInvocation
WorkerStructuredOutput
VerifiedOutcome
PlanNodeResult
AnyWorkerRunDefinition
ALL_WORKER_RUN_DEFINITIONS
```

其中 `AnyWorkerRunDefinition` 显式枚举 15 个带 Literal discriminator 的具体 Definition 子类，每个子类继承时展开五个具体泛型参数；`WorkerInvocation` 先按 `worker_id`、再按 `run_kind` 判别；最终 `PlanNodeResult.verified_outcomes` 使用完整 `VerifiedOutcome` 联合。删除 `ResumeAssetWorkerInvocation`、`ResumeAssetWorkerRunDefinition`、`ResumeAssetPlanNodeResult` 等 Tasks 1–3 临时别名，更新 Plan 模型为最终联合。缺少任一变体、只使用同一泛型基类的参数化别名、使用 `Any`/裸 `BaseModel` 或 Invocation/输出配对分支不穷尽时，Pyright 或启动目录测试必须失败。

- [ ] **Step 4: 跑完整类型目录门禁**

```bash
cd backend && uv run pytest \
  tests/platform/test_worker_invocation_registry.py \
  tests/platform/test_worker_success_contract.py \
  tests/platform/test_execution_plan.py -q
uv run pyright
```

只有本 Task 全部通过，才允许开始 Task 5 的 Runner 直接替换。

---

## Task 5: 建立并验证唯一 Invocation Runner seam

**Files:**

- Create: `backend/career_os/platform/skill/preloader.py`
- Create: `backend/career_os/agents/graphs/workers/deterministic_adapters.py`
- Create: `backend/career_os/agents/graphs/workers/invocation_runner.py`
- Create: `backend/career_os/agents/graphs/workers/invocation_react_runner.py`
- Create: `backend/career_os/agents/graphs/workers/invocation_mocks.py`
- Create: `backend/career_os/platform/operation/models.py`
- Create: `backend/career_os/platform/operation/canonical.py`
- Create: `backend/career_os/platform/operation/ledger.py`
- Create: `backend/career_os/platform/operation/registry.py`
- Create: `backend/career_os/platform/operation/__init__.py`
- Modify: `backend/career_os/platform/worker/models.py`
- Modify: `backend/career_os/agents/lc/tools.py`
- Modify: `backend/career_os/platform/prompt/loader.py`
- Modify: `backend/career_os/platform/skill/registry.py`
- Create: `backend/tests/platform/test_required_skill_preloader.py`
- Create: `backend/tests/platform/test_operation_registry.py`
- Create: `backend/tests/platform/test_durable_result_ledger.py`
- Create: `backend/tests/agents/test_worker_invocation_runner.py`
- Modify: `backend/tests/eval/test_workers_llm.py`
- Create: `backend/career_os/platform/prompt/resume/invocation_system.md`
- Create: `backend/career_os/platform/prompt/asset/invocation_system.md`
- Modify: `.agent/skills/resume-module-optimize/SKILL.md`
- Modify: `backend/typecheck/worker_invocation_contracts.py`
- Create: `backend/career_os/platform/prompt/resume/runs/collect_optimization_levels.md`
- Create: `backend/career_os/platform/prompt/resume/runs/generate_optimized_resume.md`
- Create: `backend/career_os/platform/prompt/asset/runs/reuse_outputs.md`
- Create: `backend/career_os/platform/prompt/asset/runs/register_outputs.md`
- Create: `backend/career_os/platform/prompt/asset/runs/delete_output.md`
- Modify: `backend/career_os/agents/graphs/workers/base.py`
- Modify: `backend/career_os/agents/graphs/workers/registry.py`
- Delete: `backend/career_os/agents/graphs/workers/react_runner.py`
- Delete: `backend/career_os/agents/graphs/workers/react_mocks.py`
- Modify: `backend/career_os/agents/state/worker.py`
- Delete: `backend/career_os/agents/lc/worker_llm.py`
- Modify: `backend/tests/agents/test_worker_react_runner.py`
- Delete: `backend/tests/agents/test_worker_emit.py`

**Interface:**

```python
class WorkerRunner(Protocol):
    def run(
        self,
        invocation: WorkerInvocation,
        *,
        runtime_context: WorkerRuntimeContext,
    ) -> WorkerExecutionResult: ...

    def resume(
        self,
        suspended_worker_run: SuspendedWorkerRun,
        committed_receipt: CommittedOperationReceipt,
        *,
        runtime_context: WorkerRuntimeContext,
    ) -> WorkerExecutionResult: ...


class DeterministicWorkerAdapter(Protocol):
    adapter_id: str

    def run(
        self,
        invocation: WorkerInvocation,
        *,
        runtime_context: WorkerRuntimeContext,
    ) -> WorkerExecutionResult: ...

    def complete_from_committed_receipt(
        self,
        invocation: WorkerInvocation,
        committed_receipt: CommittedOperationReceipt,
        *,
        runtime_context: WorkerRuntimeContext,
    ) -> WorkerExecutionResult: ...


class DeterministicWorkerAdapterRegistry:
    def get(self, adapter_id: str) -> DeterministicWorkerAdapter: ...

    def validate_startup(
        self,
        definitions: tuple[AnyWorkerRunDefinition, ...],
    ) -> None: ...


class WorkerRunnerRegistry:
    def resolve(self, invocation: WorkerInvocation) -> WorkerRunner: ...


class RequiredSkillPreloader:
    def preload_required(
        self,
        invocation: WorkerInvocation,
    ) -> RequiredSkillPreloadResult: ...


@dataclass(frozen=True)
class SkillPreloadAttempt:
    requirement: SkillRequirement
    status: Literal["loaded", "failed"]
    content_hash: str | None = None
    error: RequiredSkillPreloadError | None = None


@dataclass(frozen=True)
class RequiredSkillsPreloaded:
    preloaded: Literal[True]
    bundles: tuple[LoadedSkillBundle, ...]
    attempts: tuple[SkillPreloadAttempt, ...]


@dataclass(frozen=True)
class RequiredSkillsPreloadFailed:
    preloaded: Literal[False]
    error: RequiredSkillPreloadError
    bundles: tuple[()] = ()
    attempts: tuple[SkillPreloadAttempt, ...] = ()


RequiredSkillPreloadResult: TypeAlias = Annotated[
    RequiredSkillsPreloaded | RequiredSkillsPreloadFailed,
    Field(discriminator="preloaded"),
]
```

`WorkerRuntimeContext`（Worker 运行上下文）只保存 `session_id`（Session 编号，用于资源隔离）、`session_revision`（Session 修订号，用于过期检测）、Trace、Harness operation 调用能力和只读 `loaded_required_skills` 等运行依赖；不能保存聊天业务事实、完整 Session 字典，或覆盖 Invocation 的业务输入、Skill Requirement 和能力快照。当前 Harness 通过该能力调用以 `authorization_id` 幂等的领域 handler；本 plan 不把 ledger 变成执行器，后续全局失败 plan 由唯一 `OperationExecutor` 包装同一 handler。

`WorkerExecutionResult`（Worker 执行结果）按 `status` 判别：

- `WorkerExecutionCompleted`：携带已按当前 Definition 解析的具体 `WorkerStructuredOutput`；
- `WorkerExecutionFailed`：携带稳定 `code + message`，用于预检、LLM、Tool、循环上限和输出解析失败；
- `WorkerExecutionAcceptedAsync`：只携带 `MarketResearchAcceptedOutput`，仅允许 `market.start_research`；
- `WorkerExecutionAwaitingAuthorization`：携带绑定执行身份的 `SuspendedWorkerRun`；其中闭合 continuation 按 `continuation_kind` 保存 ReAct 的消息/迭代/Tool Call，或确定性 Adapter 的编号/Invocation/冻结 operation。
- `DeterministicWorkerAdapter.run`（运行确定性调用）：执行尚未提交的确定性动作；遇到需授权 operation 时只能返回冻结 continuation，不能越过 Harness。
- `complete_from_committed_receipt`（根据已提交回执完成调用）：只把原 Invocation 和已提交 receipt 转换为对应结构化输出/Worker 结果，禁止调用 Harness operation invoker、OperationRegistry、领域 handler 或其他副作用入口。
- `DeterministicWorkerAdapterRegistry.get`（获取确定性 Adapter）：按稳定 `adapter_id` 返回唯一已注册 Adapter。
- `DeterministicWorkerAdapterRegistry.validate_startup`（校验 Adapter 目录）：验证当前已接线 Definition 与 Adapter 编号的一致性；Task 5 的单元测试使用构造函数注入的 fake Adapter 覆盖四个 deterministic 分支，不依赖 Task 9 的市场确认存储或 Task 10 的产物索引。生产目录全部接线后的完整未知/重复编号门禁由 Task 11 执行。
- `WorkerRunnerRegistry.resolve`（解析 Worker Runner）：只按 Invocation 冻结的执行策略选择实现，不维护 Run Kind 分支表。

Runner 实现必须使用 `match` 或等价的显式分支先按 `worker_id`、再按 `run_kind` 缩窄 Invocation。分支内 `invocation.inputs` 必须是该动作的具体输入模型；禁止通过 `cast(Any, ...)`、裸 `BaseModel` 或字典反射绕开静态检查。

`WorkerRunner` 是统一执行 seam，不等于所有 Run Kind 都必须调用 LLM：

- ReAct 实现负责需要模型根据目标和中间结果自主选择 Tool/optional Skill 的 Run Kind；
- 确定性 Adapter 只负责 Definition 显式注册、输入完整、动作唯一且无推理价值的 Run Kind；
- Harness 只能按 Definition 已冻结的执行策略选择二者，不能逐个遍历 `allowed_operations` 来代替 ReAct；
- 确定性 Adapter 不得作为 ReAct 失败时的静默 fallback，也不得替未显式注册的 Run Kind 补默认执行路径。

Worker 原始输出只能停留在 Runner 内部的输出解析 seam。每个 Invocation 分支必须使用同一 Definition 的 `structured_output_model` 校验原始 JSON；成功时放入 `WorkerExecutionCompleted.structured_output`，失败时返回 `WorkerExecutionFailed`，不得用空输出伪装成功。不得先按 Worker 粗粒度 Schema 校验，再把结果交给 Contract 猜测 Run Kind。由于 Contract Registry 的公开参数是两个独立闭合联合，Invocation/输出是否属于同一 Definition 仍由 Registry 在运行时二次配对；该检查必须发生在具体 Contract handler 之前。

- [ ] **Step 1: 写统一接口和能力隔离红灯测试**

验证：

- stub 只接收 Invocation；
- mock 在缺少档位时返回契约错误，不自动补“标准”；
- resume 收集档位不暴露 `write_resume_html`、`list_skills` 或 `load_skill`；
- resume 生成只暴露 Invocation 允许的业务 operation，required Skill 不使 `load_skill` 或 `list_skills` 出现在 Tool Schema；
- asset 三种动作均不暴露 `list_skills` 或 `load_skill` operation；
- `allowed_operations` 只限制能力上限，不强制 LLM 调用全部 Tool，也不固定调用顺序；
- Fake ReAct LLM 可以在同一 Invocation 下选择零个、一个或多个允许 Tool，并根据 Tool 结果调整后续调用；
- optional Skill 只有在 Invocation 显式授权后才可见，是否加载由 Fake ReAct LLM 决定，未授权名称或 mode 被 Harness 拒绝；
- Prompt 由 Worker 基础 Prompt + Run Kind Prompt + 已预加载 required Skill 正文块 + Invocation 摘要组成；正文块按 Requirement 顺序排列并标记名称、mode 与内容哈希。
- 基础 Prompt 不再要求模型重新选择 Run Kind、required Skill mode 或调用 `load_skill` 加载 required Skill；
- Skill 正文不再要求当前 Worker 调用未授权 Tool、不再混入其他 Worker 职责，也不存在“必须调用”和“不得调用”同一 Tool 的冲突；
- asset reuse mock/Runner 只返回 `ReuseOutputsOutput(recommendation=...)`，不得返回 `gate_prompt`、用户选择或后续 Worker 队列；
- `RequiredSkillPreloader` 按 Requirement 顺序返回判别联合；成功分支含只读 bundle 与全部 attempt，失败分支的 bundles 固定为空，但 attempts 保留失败前成功项的哈希和最后失败项的结构化错误。
- identity/capability/strategy/resume 的 required Skill 名称与 mode 必须逐一覆盖 Task 4 的 Definition；asset、market、opportunity 和 resume collect 的空 Requirement 不访问 SkillRegistry。
- Pyright 能证明 resume generate 与 asset register 分支访问的是各自具体 `inputs` 类型。
- Runner、mock 与输出解析对 Task 4 的全部 15 个 Invocation/WorkerStructuredOutput 变体分派穷尽；新增变体但遗漏分支时 Pyright 失败。
- API Key 缺失、LLM 异常、Tool 错误、达到循环上限和输出解析失败都返回 `WorkerExecutionFailed`；不得违反接口返回裸 dict、`None` 或伪造的 WorkerStructuredOutput。
- ReAct 路径遇到需授权 Tool 时返回 `WorkerExecutionAwaitingAuthorization`，其中 `ReActOperationContinuation` 保存不可变消息 tuple、已完成迭代、待执行 Tool Call 编号/操作/规范化参数/摘要和剩余 Tool Calls。
- ReAct 恢复必须把同一 assistant 消息的 `remaining_tool_calls` 当作冻结有序批次；当前 confirmation 只授权 `pending_tool_call`，不扩散到兄弟调用。每个兄弟调用执行前重新校验 Tool 可见性、Operation Definition、当前资源/状态、参数 binding/摘要、预算、策略和授权要求：仍合法且无需授权者按原 `tool_call_id` 与顺序执行，需要授权者生成新的 confirmation 并再次暂停，失效者不产生副作用并追加结构化拒绝 Tool 结果。三调用 fixture 覆盖一次确认不扩散、恢复后上下文变化拒绝、第三条直接执行和第三条再次授权；全部 tool 消息齐全后才增加迭代。
- 恢复后失效的兄弟调用必须使用闭合 `OperationCallRejectedResult(status="rejected", operation_call_id, operation_name, code, reason)`，把其 canonical JSON 作为原 `tool_call_id` 的 tool 消息；稳定 `code` 只允许 Tool 不可见、operation 未注册、资源状态变化、参数 binding 变化、预算耗尽或策略拒绝。
- 确定性 Adapter 遇到需授权 operation 时同样返回 `WorkerExecutionAwaitingAuthorization`，但使用 `DeterministicOperationContinuation` 保存 Adapter 编号、稳定 `operation_call_id`、操作和规范化参数，不得伪造消息、迭代或 Tool Call。
- 每个确定性 Adapter 都实现 `complete_from_committed_receipt()`；测试使用会在任何 operation 调用时失败的 invoker，证明该接口只解析已提交结果而不重放副作用。receipt 只校验自身实际包含的 operation call、operation、参数和结果身份，Plan/节点/Worker Run/Invocation 身份由 Task 9 的活动快照恢复层验证。
- `PendingToolCall`、`DeterministicOperationContinuation` 和 `CommittedOperationReceipt` 在 JSON 解析时重算规范化参数/结果摘要；`WorkerMessageSnapshot` 拒绝非法角色字段组合，但允许 system/user/tool 的 `content=""`，只拒绝 `content is None`，assistant 则要求 `content is not None` 或 `tool_calls` 非空；业务空输入由 `ChatRequest` 校验。ReAct continuation 拒绝重复、重排或不属于最近 assistant 未完成后缀的 Tool Call。
- Pyright fixture 按 `continuation_kind` 把 `OperationContinuation` 缩窄为 ReAct/确定性具体类型，并以 `assert_never()` 固化恢复分派闭合性。
- `DurableResultLedgerRegistry` 能按唯一 `ledger_id` 返回 Adapter；`load_committed_result()` 只查询已提交 receipt，`save_committed_result()` 对相同冻结身份幂等且拒绝身份冲突，两者都不执行业务副作用；应用启动目录拒绝进程内 ledger、未知 operation 或含糊绑定。
- `DeterministicWorkerAdapterRegistry` 可以注入四个显式 fake Adapter，分别覆盖 collect、market start、asset register、asset delete 的分派和四分支 `WorkerExecutionResult`；测试不得要求尚未具备市场 confirmation 或 OutputIndexStore 依赖的生产 Adapter 提前存在。
- fake market Adapter 返回的 `WorkerExecutionAcceptedAsync` 不能直接构造 PlanNodeResult，必须经同一 Definition 的 Contract 验证并产生 `JobAcceptedOutcome`；其他 Run Kind 返回 accepted_async 时拒绝。

- [ ] **Step 2: 实现 RequiredSkillPreloader 纯加载模块**

在不接入 delegate 的前提下，先通过公开接口实现并验证：

- 依赖从构造函数注入的 `SkillRegistry` Adapter，不在方法内部创建 Registry；
- 按 `required_skills` 稳定顺序加载准确的名称与 mode；
- 全部成功时返回 `RequiredSkillsPreloaded(preloaded=True)`；`bundles` 保存 Requirement、正文与内容哈希，`attempts` 按相同顺序记录成功；
- Skill 不存在、mode 不存在、Worker 不允许或文件读取失败时返回 `RequiredSkillsPreloadFailed(preloaded=False)`；
- 失败分支的 `bundles` 固定为空，不能提供可启动 Runner 的部分结果；`attempts` 保留此前成功项的内容哈希与最终失败项的错误，供 Trace 使用；
- 校验 attempt 不变量：loaded 必须有 hash 且无 error，failed 必须有 error 且无 hash，失败项必须是 attempts 最后一项；
- required Skill 为空时不调用 SkillRegistry。

本 Step 只建立可替换、可独立测试的预加载模块；Task 6 再把它接入 Harness delegate seam。

- [ ] **Step 3: 按 Invocation 生成 LiteLLM Tool Schema**

直接以唯一函数替换旧 Worker 级 Tool Schema 入口：

```python
get_litellm_tools_for_invocation(invocation)
```

函数含义与作用：

- `get_litellm_tools_for_invocation`（获取本次调用可见工具）：只为 `allowed_operations` 中存在 schema 的 operation 生成 Tool 定义；返回值只是能力索引，不表示 Tool 必须执行，也不携带固定顺序。

`get_litellm_tools_for_worker(worker_id)` 在本 Task 直接删除。运行期 Tool 执行仍需 Harness 二次校验 Invocation；本 Task 先完成可见性，Task 6 完成执行校验。ReAct Worker LLM 根据目标和 Tool 返回自主决定是否调用、顺序与参数。

- [ ] **Step 4: 组合 Run Kind Prompt**

审计当前 resume、asset Worker Prompt，把稳定职责与安全限制写入唯一 `invocation_system.md`，把动作分支写入 `runs/<run_kind>.md`，并删除旧 `system.md` 的运行时读取。至少处理：

- 删除 `load_skill` 加载 required Skill 的指令；required Skill 正文由 Harness 预加载后直接注入；
- 删除让模型根据 context、`list_type` 或缺省值重新猜测 Run Kind/mode 的指令；
- 删除当前 Invocation 不可能获得的 Tool，以及 resume 维护 outputs index、asset 生成 HTML 等跨 Worker 职责；
- 删除 asset 基础 Prompt 和 `reuse_outputs` Prompt 中“由 Worker 输出 `reuse_confirm`/`gate_prompt`”的要求；Worker 只输出候选范围内的复用建议，Harness 在 Task 9 基于 `ReuseRecommendationOutcome` 创建 Additional Input Gate；
- 保留“根据目标和中间结果自主选择已授权 Tool”的 ReAct 规则；
- 对 optional Skill，只说明可按需选择，不要求固定加载。

同步审计 `.agent/skills/resume-module-optimize/SKILL.md`：消除 task `claim/complete` 的自相矛盾说明，把 outputs index 登记明确归还 `asset.register_outputs`，并保留简历生成过程对 `resume_read`、`write_resume_html` 等已授权 Tool 的自主使用方法。新增 `runs/<run_kind>.md` 后，在 `prompt.loader` 增加：

```python
def load_worker_run_prompt(invocation: WorkerInvocation) -> str: ...
```

`load_worker_run_prompt`（加载动作 Prompt）从已经解析的具体 Invocation 选择 `invocation_system.md` 与 Run Kind Prompt；找不到必须明确失败，不能读取旧 `system.md`、接受新的自由字符串或回退到另一个 Run Kind。

Runner 再通过纯函数 `build_worker_system_prompt(invocation, loaded_required_skills)`（构建 Worker 系统 Prompt）把基础 Prompt、Run Kind Prompt、预加载 Skill 正文块和 Invocation 摘要组合起来。该函数只能消费 `RequiredSkillPreloader` 返回的只读 bundle，不能按 Skill 名称重新读取文件；Requirement 非空但 bundle 缺失、重复、顺序错误或哈希不匹配时必须在第一次 Worker LLM 调用前失败。组合后的 Prompt 可以说明允许能力及选择原则，但不能把允许 Tool 展开为必执行队列。

- [ ] **Step 5: 建立 ReAct Runner、确定性 Adapter、mock 和 stub 的唯一 seam**

在 `invocation_runner.py` 建立新的统一入口：

```python
def run_worker_invocation(
    invocation: WorkerInvocation,
    *,
    runtime_context: WorkerRuntimeContext,
) -> WorkerExecutionResult: ...


def resume_worker_invocation(
    suspended_worker_run: SuspendedWorkerRun,
    committed_receipt: CommittedOperationReceipt,
    *,
    runtime_context: WorkerRuntimeContext,
) -> WorkerExecutionResult: ...
```

`run_worker_invocation`（运行类型化 Worker 调用）是唯一 Runner 入口，只接收已经冻结的 Invocation 与无业务事实的运行依赖。本 Task 直接删除旧四参数 Runner；尚未重写的 Coordinator 可以在中间态暂时不可运行。

`resume_worker_invocation`（恢复类型化 Worker 调用）只接收持久化的 `SuspendedWorkerRun`、已提交 `CommittedOperationReceipt` 和无业务事实的运行依赖；它是授权提交后的唯一 Runner 恢复入口。ReAct continuation 把 receipt 追加为原 Tool 消息；确定性 continuation 按冻结 `adapter_id` 取得同一 Adapter，并且只能调用 `complete_from_committed_receipt()`，不能再次调用 Adapter 的 `run()`。

新 `WorkerState` 在本 Task 直接替换旧状态，只保存 `invocation`，不保存可独立变更的 `worker_id`、`goal` 或完整 `session_state` 副本。Runner 在构造 Prompt 前必须验证 `loaded_required_skills` 与 Invocation 的 Requirement 一一对应；缺失、重复、顺序错误或内容哈希不匹配时直接返回预检错误。

同时在 `operation/canonical.py` 建立唯一 canonical JSON 和 SHA-256 实现：对象键排序、固定紧凑分隔符、UTF-8、`ensure_ascii=False`、`allow_nan=False`，摘要为规范字符串 UTF-8 字节的 SHA-256 小写十六进制；参数生成、账本、receipt 和 Session validator 都复用该实现。在 `worker/models.py` 建立 `WorkerMessageSnapshot`、`PendingToolCall`、`OperationCallRejectedResult`、`ReActOperationContinuation`、`DeterministicOperationContinuation`、按 `continuation_kind` 判别的闭合 `OperationContinuation`、`SuspendedWorkerRun` 和四分支 `WorkerExecutionResult`。ReAct Runner 在 Harness 返回“需要 operation authorization”时不得丢弃局部 state；它必须把当前 messages 重新解析为不可变消息模型，冻结 `completed_iterations`、当前及剩余 Tool Calls、规范化参数 JSON 和摘要。确定性 Runner 在 Adapter 执行前发现 operation 需要授权时，必须冻结 Adapter 编号、Invocation、稳定 `operation_call_id`、操作和规范化参数，不得创建虚假的 Worker 消息、迭代或 Tool Call。两种路径都返回 `WorkerExecutionAwaitingAuthorization`。本 Task 只建立暂停/恢复状态和纯 Runner 恢复入口；Task 9 接入 Session CAS 与双请求协议。

恢复入口先验证 `SuspendedWorkerRun` 外层 Plan/节点/Worker Run/Invocation 身份已由 Task 9 的活动快照恢复层匹配，再验证 `CommittedOperationReceipt` 实际携带的 authorization、operation call、operation、参数摘要和结果完整性，并按 `continuation_kind` 穷尽分派。ReAct 分支不得再次执行冻结的 pending Tool Call，而是把 receipt 的规范化结果追加为原 `tool_call_id` 对应的 tool 消息；本次 confirmation 只授权该调用。随后按原 assistant 消息的 `tool_call_id` 与顺序处理冻结的 `remaining_tool_calls`，每项执行前重新校验 Tool 可见性、OperationRegistry 定义、当前资源/状态、参数 binding/摘要、预算、策略和授权要求：无需授权且仍合法者执行；下一项需授权时生成新的 confirmation，把它设为 pending 并携带其余有序后缀再次暂停；状态变化导致失效时不产生副作用，把 `OperationCallRejectedResult` 的 canonical JSON 追加为绑定原编号的 tool 消息。只有这一批每个 Tool Call 都有匹配成功或拒绝 tool 消息后才增加 `completed_iterations` 并请求下一轮 LLM。确定性分支只调用原 Adapter 的 `complete_from_committed_receipt()`。两者都不得再次执行 operation、重新生成或重排 Tool Call、重新选择 Adapter 或重新读取业务输入。

Runner Registry 只读取 Definition 的 `execution_strategy + deterministic_adapter_id`。本 Task 建立 Adapter Protocol、Registry、`resume.collect_optimization_levels` 的生产 Adapter，以及可注入的测试 Adapter；市场与产物 Adapter 在依赖就绪的 Task 9/10 接线。ReAct Definition 必须走 ReAct Runner；每个 Task 接线后立即启用对应启动校验，最终目录不得包含未知或重复 Adapter。

本 Task 同时在 `operation/ledger.py` 建立 `DurableOperationResult`、`DurableResultLedger` Protocol 和 `DurableResultLedgerRegistry`，并在 `operation/registry.py` 建立 `OperationHandler`、`ResolvedOperation` 与 `OperationRegistry.resolve()` 的公开接口和可注入测试目录，使新 Runner 在决定暂停前只通过 operation 名称取得唯一 Definition/handler 绑定。`DurableResultLedger.load_committed_result()`（读取已提交结果）只按冻结授权、调用、operation 和参数摘要查询 receipt；`save_committed_result()`（保存已提交结果）只持久化领域 handler 已产生的规范化结果，并对相同身份幂等、不同身份冲突。账本不执行删除或其他业务副作用。当前 Harness 在 ledger 未命中时只调用 `resolve()` 返回的、以 `authorization_id` 幂等的领域 handler；handler 必须在自身事务或可恢复 journal 中同时保存副作用事实与 receipt，恢复时 Harness 先查询 ledger，已有结果便不重放 handler。Task 5 的 fake Registry 可以注册仅用于测试的 fake ledger 和 fake handler 来覆盖 ReAct 与确定性 awaiting_authorization，但应用启动目录只接受 `durability="persistent"` 且每个 operation 恰有一个同名 handler；生产 `asset.delete_output` 定义必须等 Task 10 的 `OutputIndexStore.delete_authorized()` 及其 deletion receipt 就绪后才注册。Tool Registry 与调用方都不能提供另一 handler。

新 mock/stub 只根据已经缩窄的 `worker_id + run_kind` 进入对应实现；Task 4 的 15 个变体都必须显式覆盖，并通过同一 WorkerExecutionResult 返回。旧 mock/stub 在本 Task 直接删除或重写。

- [ ] **Step 6: 转绿**

```bash
cd backend && uv run pytest \
  tests/platform/test_required_skill_preloader.py \
  tests/platform/test_operation_registry.py \
  tests/platform/test_durable_result_ledger.py \
  tests/agents/test_worker_invocation_runner.py \
  tests/agents/test_worker_react_runner.py \
  tests/eval/test_workers_llm.py -m "not llm" -q
uv run pyright
```

本 Task 只要求新 Runner seam 的定向测试和类型检查通过；旧 Coordinator 回归不作为中间门禁，最终系统回归在 Task 12 恢复。

---

## Task 6: 建立唯一 Invocation delegate

**Files:**

- Modify: `backend/career_os/platform/skill/preloader.py`
- Modify: `backend/career_os/harness/delegate.py`
- Modify: `backend/career_os/harness/executor.py`
- Modify: `backend/career_os/platform/tool/registry.py`
- Modify: `backend/tests/platform/test_required_skill_preloader.py`
- Modify: `backend/tests/harness/test_delegate_rules.py`
- Modify: `backend/tests/harness/test_delegate_capability_bundle.py`
- Modify: `backend/tests/agents/test_lc_tools.py`

**Interface:**

```python
def delegate_invocation(
    actor: str,
    invocation: WorkerInvocation,
    authorization_facts: InvocationAuthorizationFacts,
    *,
    runtime_context: WorkerRuntimeContext,
    skill_preloader: RequiredSkillPreloader,
    trace: TraceWriter | None = None,
) -> DelegatedInvocation | HarnessError: ...


class RequiredSkillPreloader:
    def preload_required(
        self,
        invocation: WorkerInvocation,
    ) -> RequiredSkillPreloadResult: ...
```

- `RequiredSkillPreloader.preload_required`（预加载必需 Skill）：按 Invocation 中结构化 `SkillRequirement(name, mode)` 的顺序加载全部 required Skill，并验证 Worker 与 mode 授权。
- `LoadedSkillBundle`（已加载 Skill 包）：保存 Requirement、正文和内容哈希，以只读 tuple 注入 Runtime Context。
- `RequiredSkillPreloadResult`（预加载结果）：以 `preloaded` 区分全部成功和失败；失败时 bundles 为空，但 attempts 保留已尝试 Requirement 的状态、哈希或错误。
- `RequiredSkillPreloadError`（预加载错误）：指出失败 Requirement 与结构化原因；它位于失败结果和最后一个 failed attempt 中，本 plan 将其转为 `required_skill_preload_failed` 并 fail-fast。
- `DelegatedInvocation`（已授权调用）：仅在全部 required Skill 加载成功后返回原不可变 Invocation 和包含 `loaded_required_skills` 的 Runtime Context。
- `check_invocation_delegate_rules`（检查类型化委托规则）：读取 Invocation 的 Worker、Run Kind、输入和当前阶段；旧 `check_delegate_rules` 在本 Task 删除。

- [ ] **Step 1: 写越权、快照与预加载红灯测试**

验证：

- resume.collect 不能执行 write operation；
- asset 不能执行 `list_skills` 或 `load_skill` operation；
- Invocation 未允许的 Tool 即使属于同一 Worker 也被拒绝；
- `InvocationAuthorizationFacts` 只包含委托规则需要的 Session、阶段、Gate 和资源状态身份；它由当前 Session 事实生成且不能反向写入，状态变化不改写已有 Invocation；
- opportunity 正式市场结果由 `prepare()` 从正式 Artifact 来源冻结为 Node Spec 输入，`resolve()` 只校验该快照，不从旧 prior result 猜测。
- required Skill 按 Definition 顺序、使用准确名称和 mode 加载；
- required Skill 全部成功后才返回 DelegatedInvocation，且 Runtime Context 中的加载结果是只读 tuple；
- Skill 不存在、mode 不存在、Worker 不允许或文件读取失败时返回 `required_skill_preload_failed`；
- 任一 required Skill 失败都不调用 WorkerRunner、Worker LLM 或业务 Tool，也不保留可用于启动 Worker 的部分加载结果；
- 第二个 required Skill 失败时，返回的 bundles 为空，但 attempts 含第一个 Skill 的 loaded/hash 和第二个 Skill 的 failed/error，Trace 两条均完整；
- required Skill 加载 Trace 关联 invocation_id、run_kind、Skill 名称、mode、内容哈希和状态，但不包含正文；
- required Skill 为空时不调用 SkillRegistry，resume.collect 与 asset 三种动作均直接通过该预检；
- mock 和 stub 不得自行补充或伪造 `loaded_required_skills`。

- [ ] **Step 2: 把 RequiredSkillPreloader 接入唯一 fail-fast delegate**

`RequiredSkillPreloader` 已由 Task 5 通过公开接口实现。本 Step 只负责 Harness 集成：

1. Harness 构造时注入 `RequiredSkillPreloader`，新 `delegate_invocation()` 不在内部创建 Preloader 或 SkillRegistry；
2. 阶段、Gate 和授权通过后，调用 `preload_required(invocation)`；
3. `preloaded=False` 时先把 `attempts` 全量写 Trace，再映射为 `HarnessError(code="required_skill_preload_failed")`；不得调用 Runner、LLM 或业务 Tool，且不得读取不存在的部分 bundles；
4. `preloaded=True` 时把 `bundles` 完整只读 tuple 写入新的 Runtime Context，不修改 Invocation；
5. 两个分支都从 attempts 记录 Requirement、内容哈希/错误码和状态，正文只存在于成功 bundles 与 Runtime Context；
6. 本 Task 不重试、不降级，后续全局失败 plan 复用该加载证据。

本 Step 直接以 Invocation delegate 替换并删除旧 `delegate_worker(actor, worker_id, goal, ...)`；中间态不要求旧 Coordinator 可运行。

- [ ] **Step 3: 增加 Invocation capability bundle 投影**

以 `_build_invocation_capability_bundle(invocation)` 直接替换旧 `_build_capability_bundle(worker_id)`：

- `required_skills`（必需 Skill Requirement）；
- `optional_skills`（可选 Skill Requirement）；
- `allowed_operations`（允许 operation）。
- `execution_strategy` 与 `deterministic_adapter_id`（执行路径快照）：仅供 Runner Registry 选择已注册实现，不暴露给模型改写。
- `loaded_required_skills`（已预加载 Skill）：仅来自 RequiredSkillPreloader，不允许调用方覆盖。

- [ ] **Step 4: 为 Tool 执行传入 Invocation 授权上下文**

扩展 Harness 内部执行上下文，使运行期校验至少包含：

```text
worker_id + invocation_id + run_kind + operation name + session_id
```

本 plan 对业务 Tool 只做 allow/deny；required Skill 预加载失败采用前述 fail-fast。两者的重试和 FailureResult 都由后续全局失败 plan 接管。

- [ ] **Step 5: 转绿**

```bash
cd backend && uv run pytest \
  tests/platform/test_required_skill_preloader.py \
  tests/harness/test_delegate_rules.py \
  tests/harness/test_delegate_capability_bundle.py \
  tests/agents/test_lc_tools.py \
  tests/agents/test_worker_invocation_runner.py -q
uv run pyright
```

本 Task 的完成门禁只验证唯一 delegate seam；旧委托测试直接重写或删除。

---

## Task 7: 重写为唯一 InvocationProposal analyze 路径

**Files:**

- Create: `backend/career_os/agents/lc/invocation_analyze.py`
- Modify: `backend/career_os/agents/lc/coordinator_llm.py`
- Create: `backend/career_os/platform/prompt/coordinator/invocation_analyze_system.md`
- Modify: `backend/career_os/harness/pipeline_routing.py`
- Modify: `backend/career_os/harness/pipeline_phase_advance.py`
- Modify: `backend/career_os/harness/explore_closure.py`
- Modify: `backend/tests/agents/test_coordinator_routing.py`
- Modify: `backend/tests/agents/test_coordinator_analyze.py`
- Modify: `backend/tests/agents/test_coordinator_explore_phase.py`
- Modify: `backend/tests/harness/test_pipeline_routing_phase.py`
- Modify: `backend/tests/harness/test_pipeline_phase_advance.py`

- [ ] **Step 1: 写 LLM/fallback 提议红灯测试**

验证：

- 新 `analyze_invocation_proposals()` 返回 `invocations`，不返回纯 `workers`；
- LLM 的每个 InvocationProposal 只能输出 `worker_id + run_kind`；`pipeline_phase` 仍是 analyze 顶层的目标阶段提议；
- 当前阶段始终进入 `selectable_phases`；
- 当前为 `jd_analysis` 且既有规则与 Gate 允许前向进入 `resume_strategy` 时，`selectable_phases` 包含两个阶段，模型索引包含 `strategy.jd_application`；
- 前向条件或 Gate 不满足时，`resume_strategy` 不进入 `selectable_phases`，对应 Run Kind 不进入模型索引；
- 目标 `pipeline_phase` 不在 selectable phases 中，或动作不允许在目标阶段执行时，提议被拒绝；
- 计算 selectable phases、构建模型索引和解析 LLM 返回均不修改 Session 或 Task Store；
- fallback 为每个确定性 Worker 选择唯一 Run Kind；
- LLM 不能提交依赖、Tool 或成功契约。

- [ ] **Step 2: 把阶段可选择性计算与阶段提交拆开**

在 `pipeline_phase_advance.py` 增加纯函数：

```python
def resolve_selectable_pipeline_phases(
    routing_facts: SessionRoutingFacts,
    user_message: str,
) -> frozenset[PipelinePhase]: ...
```

`resolve_selectable_pipeline_phases`（解析本轮可选择阶段）只读取 `SessionRoutingFacts` 中冻结的当前阶段、Gate 和进入条件事实，以及阶段图和用户消息。当前阶段必须始终保留；前向阶段只有通过既有 `can_enter_pipeline_phase` 等确定性规则后才进入集合。该函数不得调用 `apply_list_phase()`，不得修改 Session、Task Store 或 Gate。Task 8 发布完整聚合后，该投影只能由 `SessionExecutionState` 显式构造。

阶段推进只能由后续完整 `SessionExecutionState` transition 提交；Task 8 的 ExecutionPlan Coordinator 只有在目标阶段、全部 Proposal、输入来源和 Plan 都验证成功后才能返回包含新阶段的下一版聚合。不能为了生成模型索引提前推进阶段。

- [ ] **Step 3: 替换 Coordinator Prompt 与解析 schema**

模型可见索引改为：

```python
selectable_phases = resolve_selectable_pipeline_phases(
    session_state,
    user_message,
)
selectable_scopes = frozenset(
    PipelineExecutionScope(phase=phase)
    for phase in selectable_phases
)
worker_index = worker_registry.build_llm_index(
    selectable_scopes=selectable_scopes,
)
```

`selectable_phases`（可选择 Pipeline 阶段）是阶段规则的纯函数结果；`selectable_scopes`（可选择执行范围）把每个阶段转换为显式 `PipelineExecutionScope`，用于查询动作目录。新增 `analyze_invocation_proposals()` 在一次 analyze 中返回顶层 `pipeline_phase` 和 `invocations`。Harness 必须先把 `list_type="pipeline" + pipeline_phase` 解析为 `target_scope`，验证它属于 `selectable_scopes`，再验证每个动作允许在该范围执行；不得使用推进前的当前阶段过滤掉合法前向动作。

本 Task 直接以 `analyze_invocation_proposals()` 替换 `analyze_workers()`、字符串 `workers` Schema 和旧 Coordinator Prompt。新解析器复用现有 JD、探索和 market 硬前置条件，输出统一转换为 `InvocationProposal`；确定性 fallback 进入相同 Builder → Registry `prepare()` 流程。旧 Prompt、旧 Schema 和旧 loader 同时删除。

- [ ] **Step 4: 重写探索调度 helper**

以接受/返回 InvocationProposal 的探索调度 helper 直接替换旧 `list[str]` helper，仍保持 identity/capability 一次只执行一个的业务规则。

- [ ] **Step 5: 转绿**

```bash
cd backend && uv run pytest \
  tests/agents/test_coordinator_routing.py \
  tests/agents/test_coordinator_analyze.py \
  tests/agents/test_coordinator_explore_phase.py \
  tests/harness/test_pipeline_routing_phase.py \
  tests/harness/test_pipeline_phase_advance.py -q
```

本 Task 只运行最终 Proposal analyze 接口测试；旧字符串 analyze 测试直接删除或重写。

---

## Task 8: 建立并验证唯一 ExecutionPlan Coordinator 路径

**Files:**

- Create: `backend/tests/agents/test_coordinator_execution_plan.py`
- Create: `backend/tests/platform/test_plan_result_presenter.py`
- Create: `backend/career_os/agents/graphs/execution_plan_coordinator.py`
- Create: `backend/career_os/platform/worker/presentation.py`
- Create: `backend/career_os/platform/worker/transitions.py`
- Create: `backend/career_os/platform/store/execution_state.py`
- Modify: `backend/career_os/platform/worker/requests.py`
- Modify: `backend/career_os/agents/state/coordinator.py`
- Modify: `backend/career_os/agents/lc/invocation_analyze.py`
- Modify: `backend/career_os/platform/prompt/loader.py`
- Modify: `backend/career_os/harness/explore_guidance.py`
- Modify: `backend/career_os/harness/session_activity.py`

本 Task 在 Coordinator 接口发布前先定义最终 `ExecutionPlanRequest` 闭合联合、`SessionTaskState`、各阶段 `SessionArtifactState`、闭合 `SessionPendingGate`、`CurrentExecution` 和 `SessionExecutionState`。Task 4 的两个窄事实投影改为只能从该聚合构造；它们不持久化，也不能成为 Handler 或 RequestService 的参数。Task 9 只实现该既定 schema 的 Store、API 解析与生命周期 CAS，不再晚到修改 Handler 的核心类型。

- [ ] **Step 1: 写 Coordinator Plan 执行红灯测试**

通过唯一入口 `run_execution_plan_turn()`（运行类型化执行计划本轮编排）验证：

- resume → asset 建立两个节点；
- Plan 创建时 resume 已有 Invocation，asset 只有 Node Spec 且 `invocation is None`；
- 第一轮只执行 resume；
- resume 成功 Outcome 满足后，Executor 才绑定 asset 输入并物化 asset Invocation；
- 两个上游分两次完成的 fan-in 只向第二次 `advance()` 提交新结果；先前结果从 ExecutionPlan finished 节点读取，下游仍能正确物化；
- resume 失败或空交付物时 asset 不执行；
- `pending_workers` 和 `current_worker_id` 不再出现在公开结果；
- 一次只有一个 Plan 节点 running；
- `advance()` 只产生 ready 状态，不直接返回待执行节点；
- `claim_next()` 在同一个结果中完成唯一 ready 节点的选择、`ready → running`、worker_run_id 绑定和 `PlanDispatch` 生成；
- Coordinator 采用 claim 返回的新 Plan 后才能执行 dispatch；已有 running 节点时重复 claim 不启动第二个 Worker；
- Worker 结果只有携带与当前 running 节点一致的 node_id 和 worker_run_id 才能结束节点；错配结果不推进 Plan；
- 合法前向目标阶段只在 Plan 构建成功后提交；Proposal、输入或 Plan 校验失败时当前阶段保持不变；
- Invocation 物化前 Trace 使用 plan_id + node_id，物化后再关联 invocation_id；
- asset 不从 `prior_results` 或 delegate context 补 deliveries。
- `PlanResultPresenter` 只从 Plan 终态与 verified outcomes 生成 `synthesis_draft + artifact_refs`；resume/asset 链完成后不会展示 asset 角色说明，最终润色失败时仍返回确定性草稿；
- 显式 `list_type="plan"` 返回不属于本期闭合 pipeline 目录的结构化错误；代码中不存在 LegacyCareerPlanAdapter、旧四参数 Runner、字符串 Worker 队列、旧通用输出 Schema 或 summary 增强 seam；
- Task 8 的 Coordinator 测试必须通过 `CoordinatorRuntimeContext` 注入 fake market/asset 确定性 Adapter；这些 fake 只返回契约可验证的结构化结果，不读取 Task 9 尚未建立的市场确认存储或 Task 10 尚未建立的产物索引，也不能进入默认 Adapter 目录。
- 每个 `ExecutionPlanTurnResult` 分支都携带闭合 `ExecutionPlanStateTransition`：构建拒绝返回 `NoSessionStateTransition`；普通完成返回 `CommitExecutionPlanTurnTransition`；等待授权返回 `SuspendExecutionPlanTransition`。活动 Plan 恢复完成时由 Task 9 的 ResumeHandler 构造 `FinalizeExecutionPlanTransition`。Task 8 只返回完整下一版聚合，不写 Session。

`PlanPresentation`（计划展示结果）包含 `synthesis_draft`（确定性回复草稿）和 `artifact_refs`（仅来自 verified outcomes 的稳定产物引用）。`PlanResultPresenter.render(plan)`（渲染计划结果）只读取已持久化 Plan 终态、节点结果与 verified outcomes；它不读取 `last_worker_result`、`prior_results`、`user_visible_summary` 或 Worker 角色说明。

- [ ] **Step 2: 以 ExecutionPlanCoordinatorState 替换旧 Coordinator 状态**

新增 `ExecutionPlanCoordinatorState`（执行计划协调状态），只供 `run_execution_plan_turn()` 使用，并包含：

```text
turn_run_id
execution_plan
active_plan_node_id
```

本 Task 直接删除旧 `CoordinatorState.pending_workers/current_worker_id`；中间态不保留第二套 Coordinator 状态。

字段含义与作用：

- `turn_run_id`（本轮运行编号）：关联当前用户消息。
- `execution_plan`（执行计划）：保存本轮 Node Spec、可选 Invocation、依赖、调度状态，以及 finished 节点上已持久化的 `PlanNodeResult`；它是节点结果的唯一事实来源。
- `active_plan_node_id`（活动计划节点编号）：节点标识在 Invocation 物化前后保持稳定；运行时指向当前唯一 running 节点。

不得另设 `plan_node_results`、`prior_results` 或 Coordinator 侧结果字典作为依赖输入。Coordinator 只把本次刚完成节点的结果提交给 `advance()`，随后采用返回的新 ExecutionPlan；后续依赖重算从 Plan 节点的 `result` 字段读取累积事实。

- [ ] **Step 3: 组装唯一 ExecutionPlan Coordinator 接口**

在 `execution_plan_coordinator.py` 建立：

```python
@dataclass(frozen=True)
class CoordinatorRuntimeContext:
    invocation_registry: WorkerInvocationRegistry
    plan_builder: ExecutionPlanBuilder
    plan_executor: ExecutionPlanExecutor
    worker_runner: WorkerRunner
    success_contracts: DeterministicSuccessContractRegistry
    presenter: PlanResultPresenter
    trace_writer: TraceWriter


class ExecutionPlanTurnCompleted(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["completed"]
    execution_plan: ExecutionPlan
    presentation: PlanPresentation
    state_transition: Annotated[
        CommitExecutionPlanTurnTransition | FinalizeExecutionPlanTransition,
        Field(discriminator="transition_kind"),
    ]


class ExecutionPlanTurnRejected(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["rejected"]
    errors: tuple[PlanBuildError, ...]
    state_transition: NoSessionStateTransition


class ExecutionPlanTurnAwaitingAuthorization(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["awaiting_authorization"]
    execution_plan: ExecutionPlan
    suspended_worker_run: SuspendedWorkerRun
    state_transition: SuspendExecutionPlanTransition


ExecutionPlanTurnResult: TypeAlias = Annotated[
    ExecutionPlanTurnCompleted
    | ExecutionPlanTurnRejected
    | ExecutionPlanTurnAwaitingAuthorization,
    Field(discriminator="status"),
]


def run_execution_plan_turn(
    *,
    session_state: SessionExecutionState,
    turn_request: NewExecutionPlanTurnRequest,
    runtime_context: CoordinatorRuntimeContext,
) -> ExecutionPlanTurnResult: ...
```

`CoordinatorRuntimeContext`（协调器运行上下文）是深模块的显式依赖集合，作用是让测试替换 Runner、确定性 Adapter、Registry 和 Trace，而不从全局单例或可变 Session 字典补业务事实。

`ExecutionPlanTurnResult`（执行计划本轮内部结果）按 `status` 穷尽完成、构建拒绝和等待授权三种结果；它携带尚未提交的 transition，只能由 RequestService 消费。已终结 confirmation 由 RequestService 从终态回执直接构造公开结果，不进入新 Turn Handler。

`transitions.py` 中四个变体的最小字段和作用固定为：

- `NoSessionStateTransition`（不修改会话状态）：包含 `transition_kind="none"` 和结构化原因，用于 Plan 构建拒绝或命中已终结 confirmation。
- `CommitExecutionPlanTurnTransition`（提交同步 Plan 本轮终态）、`SuspendExecutionPlanTransition`（暂停等待授权的 Plan）和 `FinalizeExecutionPlanTransition`（终结授权暂停 Plan）都包含 `expected_session_revision + next_state: SessionExecutionState`；各 validator 分别证明同步完成后 `NoCurrentExecution + last_terminal_execution_plan`、`AuthorizationSuspendedExecution` 或终态回执形态。`AsynchronousExecution` 预留给未来真正跨请求且不等待授权的 Plan，本期没有请求分支可以构造它；已登记的后台市场 Job 也不创建该分支。RequestService 固定映射到 `commit_execution_turn()`、`suspend_execution_turn()`、`resuspend_active_execution_plan()` 或 `finalize_active_execution_plan()`，不能把全部 transition 错写成同一个 Store 调用。

阶段、Gate、Task 控制状态、Artifact 引用和 Plan 必须已经组合进完整 frozen `next_state`，不得用任意 patch 字典或 Presenter 文本表达状态变化。

`run_execution_plan_turn()`（运行类型化执行计划新本轮）只读取冻结 `SessionExecutionState + NewExecutionPlanTurnRequest` 并返回尚未提交的 transition，不持有 SessionStore。聊天分支可以调用 analyze；市场启动、产物删除和 Gate 决策分支从具体请求生成唯一 Harness Proposal，不能由 API 额外传入 `preset_proposals`。它直接替换旧 `run_coordinator_turn()` 编排实现。

- [ ] **Step 4: 让 analyze 构建 Plan，让 delegate 执行 ready 节点**

ExecutionPlan Coordinator 不自行 pop 队列。流程固定为：

```text
analyze proposals
→ parse list_type + pipeline_phase into target_scope
→ validate target_scope against selectable_scopes
→ ExecutionPlanBuilder.build
→ match PlanBuildResult
  ├── PlanBuildRejected: preserve phase and return structured validation result
  └── PlanBuilt: adopt plan with prepared Node Specs and input-complete Invocations
→ ExecutionPlanExecutor.advance
→ return CommitExecutionPlanTurnTransition for validated forward phase
→ allocate worker_run_id
→ ExecutionPlanExecutor.claim_next
→ adopt claimed Plan
→ retain immutable PlanDispatch and delegate only PlanDispatch.invocation
→ record node result with plan_id/node_id/worker_run_id copied from that PlanDispatch
→ advance persists result on the finished node
→ bind verified Outcomes
→ materialize newly-unblocked Invocation
→ advance again
```

`advance()` 不得把 ready 节点改成 running。Coordinator 也不得读取 ready 节点后自行写 `active_plan_node_id`、`scheduling_status` 或 `worker_run_id`；这些值只能来自 `claim_next()` 返回的更新 Plan 和 `PlanDispatch`。如果 claim 返回未认领结果，本轮不得调用 WorkerRunner。

本 plan 的 `WorkerRunner` 只接收 `WorkerInvocation + WorkerRuntimeContext`，其中 RuntimeContext 不含业务事实或完整 Session 字典。Coordinator 必须在调用期间保留完整且不可修改的 `PlanDispatch`，局部结果 Adapter 只能从该 dispatch 复制 plan_id、node_id 和 worker_run_id，不能从 Runner 输出、当前活动节点或新生成编号推断身份。后续全局失败 plan 实施后，由 `RunEngine.start_worker(dispatch)` 直接消费这个包络。

前向阶段提交必须发生在 Builder 完成目标阶段、Proposal、Gate、输入来源与图校验之后。若 Plan 构建失败，Coordinator 返回结构化校验结果，不能保留索引计算或 LLM 提议造成的阶段修改。

全局失败 plan 实施前，Task 5 的闭合 `WorkerExecutionResult` 通过一个局部 Adapter 进入契约 seam。Adapter 对 `WorkerExecutionCompleted` 必须调用 `DeterministicSuccessContractRegistry.evaluate()`：只有 `satisfied=True` 才能生成 success 和 `verified_outcomes`；契约不满足或 `WorkerExecutionFailed` 时生成非 success 且 Outcome 为空。`WorkerExecutionAwaitingAuthorization` 不是终态，不得构造 PlanNodeResult，而是进入 Task 9 的暂停协议。对 `market.start_research`，`WorkerExecutionAcceptedAsync` 不能直接复制为 PlanNodeResult；Adapter 必须验证后台 Job 已创建并持久化、引用可追踪且 `MarketResearchRunner.start()` 已接受后台启动，再由该 Definition 的确定性 Contract 产生 `JobAcceptedOutcome`。契约满足后当前 Worker Run 和节点立即 success/finished，后台 Job 独立继续，不等待终态。其他 Run Kind 的 accepted_async 一律拒绝。不得把 `structured_output`、Pydantic Schema 通过或执行状态直接提升为 verified Outcome，也不要在 Coordinator 分散判断契约细节或错误字符串。

- [ ] **Step 5: 删除旧阶段、Artifact 与纯规划旁路**

删除 Coordinator 对 TaskStore 阶段、旧 Session Artifact 文件和 `list_type="plan"` 旁路的读写。阶段、Gate 和 Artifact 引用只从 `SessionExecutionState` 读取并通过 transition 返回；本 Task 不建立兼容投影。

- [ ] **Step 6: 转绿**

```bash
cd backend && uv run pytest \
  tests/agents/test_coordinator_execution_plan.py \
  tests/agents/test_coordinator_c3.py \
  tests/agents/test_coordinator_trace.py \
  tests/agents/test_coordinator_phase_synthesis.py \
  tests/agents/test_synthesis_pipeline_context.py \
  tests/platform/test_plan_result_presenter.py -q
```

---

## Task 9: 重写类型化 API、SessionExecutionState 聚合和三类 Gate 生命周期

**Files:**

- Modify: `backend/career_os/api/chat.py`
- Create: `backend/career_os/api/execution_plan_requests.py`
- Modify: `backend/career_os/agents/graphs/execution_plan_coordinator.py`
- Modify: `backend/career_os/harness/gate.py`
- Modify: `backend/career_os/harness/pipeline_gates.py`
- Modify: `backend/career_os/platform/store/execution_state.py`
- Modify: `backend/career_os/platform/store/session.py`
- Modify: `backend/career_os/platform/store/__init__.py`
- Delete: `backend/career_os/platform/store/task.py`
- Modify or Delete: `backend/career_os/platform/tool/handlers/task.py`
- Modify: `backend/career_os/platform/pipeline_template.py`
- Modify: `backend/career_os/api/explore_intake.py`
- Modify: `backend/career_os/api/sessions.py`
- Modify: `backend/career_os/agents/lc/coordinator_llm.py`
- Modify: `backend/career_os/harness/delegate.py`
- Modify: `backend/career_os/harness/jd_change.py`
- Modify: `backend/career_os/harness/market_research_result.py`
- Modify: `backend/career_os/harness/pipeline_intent_transition.py`
- Modify: `backend/career_os/harness/pipeline_jd_context.py`
- Modify: `backend/career_os/harness/pipeline_phase_advance.py`
- Modify: `backend/career_os/harness/pipeline_phase_transition.py`
- Modify: `backend/career_os/harness/pipeline_routing.py`
- Modify: `backend/career_os/harness/session_activity.py`
- Create: `backend/career_os/platform/store/writer_lease.py`
- Modify: `backend/career_os/main.py`
- Modify: `backend/career_os/platform/operation/models.py`
- Modify: `backend/career_os/platform/operation/registry.py`
- Modify: `backend/career_os/platform/market_research/models.py`
- Modify: `backend/career_os/platform/market_research/plans.py`
- Modify: `backend/career_os/agents/graphs/workers/deterministic_adapters.py`
- Modify: `backend/career_os/api/market_research.py`
- Modify: `backend/tests/api/test_chat_intent_phase.py`
- Modify: `backend/tests/api/test_explore_gate_phase.py`
- Create: `backend/tests/api/test_active_execution_plan_session.py`
- Create: `backend/tests/platform/test_data_directory_writer_lease.py`
- Modify: `backend/tests/platform/test_operation_registry.py`
- Modify: `backend/tests/platform/test_durable_result_ledger.py`
- Modify: `backend/tests/platform/test_market_research_plan_intent.py`
- Modify: `backend/tests/platform/test_market_research_service_recovery.py`
- Create: `backend/tests/harness/test_reuse_decision_gate.py`
- Create: `backend/tests/api/test_current_tasks_api.py`
- Create: `backend/tests/platform/test_session_task_state.py`
- Modify: `backend/tests/e2e/test_resume_levels.py`
- Modify: `backend/tests/e2e/test_asset_register.py`
- Modify: `backend/tests/e2e/test_strategy_asset.py`

- [ ] **Step 1: 写确定性 Gate/入口红灯测试**

验证：

- `optimize_confirm` 确认后新 Turn 创建 resume generate + asset register Plan；
- 档位缺失时只创建 `resume.collect_optimization_levels`；
- 用户选择档位后创建新 Turn 和新 Plan；
- 市场方案第一次确认生成并持久化 `confirmation_id`，同一内容/版本重复确认返回同一编号，修订清除旧编号且再次确认生成新编号；
- `market_action=start_confirmed_plan` 只有在 `MarketPlanConfirmationRef` 的 confirmation、Session、版本和摘要都与存储一致时创建 `market.start_research` Proposal；
- `market.start_research` 默认 Adapter 在本 Task 接线：先创建并持久化后台 Job，再调用 `MarketResearchRunner.start()`；只有 Runner 接受后台启动后才返回 `WorkerExecutionAcceptedAsync`，Success Contract 随后产生 `JobAcceptedOutcome`，当前 Worker Run 与 Plan 节点立即 success。后台 Job 独立继续，不等待其终态；Runner 拒绝启动或抛错时当前节点不能 success。本 Task 不创建 Job Run 或 Job ExecutionPlan；
- Workflow Transition Gate 不把 resume/asset 提前放进 strategy Plan；
- 四类 Workflow Transition Gate 的 reject 逐个测试：`explore_complete` 清除 Gate 并重新开放 explore；`market_research_required` 清除 Gate、停留当前阶段且不创建 Plan/Job；`market_result_confirmation` 保留 `latest_result`、保持 `accepted_result=None`、阻断下游并创建闭合 `MarketResultFollowUpGate`，新 Turn 才能选择修改条件重跑、原条件重跑或暂停；`optimize_confirm` 清除 Gate、停留 resume_strategy 且不创建 resume/asset Plan。任何旧 `gate_id` 都不能复用；
- `asset.reuse_outputs` 的 Worker 输出和 Contract 结果都不含 `gate_prompt`，合法 `ReuseRecommendationOutcome` 完成当前 Plan 后由 Harness 创建 `reuse_confirm`；
- `reuse_confirm` 保存来源 plan/node 身份、已验证 `eligible_candidates` 和闭合 allowed actions，不保存 WorkerInvocation、默认选择或自由文本动作；
- 含糊、冲突、候选越界、应选而未选产物，或新建时错误携带产物的输入保持原 Gate pending，不创建 Proposal 或 Plan；
- `skip_optimization` 创建新 Turn 的终态空 Plan，返回选定既有交付物，不执行 resume 或 `asset.register_outputs`；
- `incremental_optimize` 在新 Turn 使用选定 delivery 作为 resume_ref；档位齐全时创建 resume generate + asset register Plan，档位缺失时只创建 collect levels Plan；
- `new_full_optimize` 在新 Turn 使用当前基线简历引用，且不得绑定历史 delivery；档位分支规则与增量优化相同；
- Gate 已被消费、来源 Plan/节点不匹配或候选已失效时拒绝复用旧决策，不静默转为新建。
- 使用注入的 fake durable ledger 执行通用授权集成测试：ReAct fixture 第一次 HTTP 请求在副作用前生成 `confirmation_id + authorization_id`，并以 compare-and-set 序列化消息、迭代、当前/剩余 Tool Calls 和全部运行身份；确定性 fixture 序列化 Adapter、Invocation、稳定 `operation_call_id`、冻结 operation 和参数，且不生成虚假消息或 Tool Call。两种路径都只有存储成功后才返回暂停。
- `/v1/chat` 只有结构化 `operation_confirmation={confirmation_id, decision}` 能改变授权状态；普通聊天仍要求消息或附件，授权请求可在携带 `session_id` 时使用空消息，`market_action` 与 `operation_confirmation` 互斥。仅发送自然语言“同意”不得授权。
- `ExecutionPlanRequestResult` 的传输映射穷尽测试：completed 产生 token/done；awaiting authorization 产生 `operation_confirmation_required` SSE 事件并携带编号、operation 摘要、可选删除目标摘要和提交修订号；业务 rejected 使用闭合 request error；conflict 返回 409；already finalized 返回首次业务结果或稳定拒绝/中断状态。前端确认/拒绝必须发送结构化对象；
- 第二次 HTTP 请求携带同一 Session 和结构化 confirmation 后，不调用 Coordinator analyze、不创建新 Plan/Invocation/Worker Run；`decision="confirm"` 在 operation receipt 提交后调用 `resume_worker_invocation()`，ReAct 分支不重新生成 Tool Call，并把 receipt 结果追加到原 `tool_call_id`；确定性分支不重新选择 Adapter，只调用 `complete_from_committed_receipt()` 完成原 Worker Run；两种副作用都只提交一次。终态后 `finalize_active_execution_plan()` 在同一次 CAS 中保存完整终态 Plan、confirmation 终态回执并清除活动快照。
- `decision="reject"` 原子完成 `waiting → rejected`，不执行 continuation；当前节点用原身份产生 `cancelled` 结果，下游转为 `blocked_by_upstream`，Trace 记录拒绝，并通过 `finalize_active_execution_plan()` 原子保存终态 Plan/回执和清除活动快照。重复拒绝在快照已清除后仍从 `operation_confirmation_receipts` 幂等返回同一终态回执，已经 authorized/committed 或身份错配不能改写为 rejected。
- 同一 assistant 消息包含三个 Tool Call 时，第二条的 confirmation 只授权第二条，不得扩散到第三条；第二条授权恢复后第三条保持原顺序和 `tool_call_id`，并在执行前重新校验 Tool 可见性、Operation Definition、当前资源/状态、参数 binding/摘要、预算、策略和授权要求。第三条无需授权且仍合法则执行并追加结果；需要授权则生成新的 `confirmation_id + authorization_id`、以第三条为新 pending 再次暂停；恢复后上下文变化使第三条失效时不产生副作用，并追加绑定第三条编号的结构化拒绝 Tool 结果。三个调用都有匹配成功或拒绝 tool 消息后才能增加迭代并调用 LLM。
- 确认消费持久化为 `waiting → authorized`；同一 confirmation 在 authorized 状态可幂等读取，但恢复请求还必须用唯一 `resume_attempt_id` compare-and-set 认领 `active_resume_attempt_id`，只有认领者可以执行 continuation 中冻结的 operation。
- 副作用存储以 `authorization_id` 为幂等键；持有恢复尝试的请求取得结果后构造 `CommittedOperationReceipt`，由 SessionStore 在一次 compare-and-set 中同时保存规范化结果、结果摘要、`authorized → operation_committed` 和尝试释放。模拟 operation 前失败时可以释放本次认领；模拟 operation 已提交但 receipt 尚未保存时，后续恢复从底层账本取得同一结果并补交 receipt，不重复副作用。
- 模拟 receipt 已保存但 Runner 尚未继续即中断，后续请求按 `continuation_kind` 恢复：ReAct 分支重建绑定原 `tool_call_id` 的消息，确定性分支只调用 Adapter 的 `complete_from_committed_receipt()`；测试注入会在任何 operation 执行时失败的 invoker，证明两者都不再次执行 operation。只有 ReAct Run 后续遇到新授权点时才通过 `resuspend_active_execution_plan()` 原子替换活动快照。
- Session JSON 往返拒绝非法授权快照：`waiting` 不得携带 claim/receipt，`authorized` 不得携带 receipt，`operation_committed` 必须携带 receipt；receipt 的 authorization、operation call、operation 和参数摘要必须与外层一致，Plan/节点/Invocation/continuation 的交叉身份也必须一致；规范化参数/结果与其 SHA-256 摘要必须一致，消息角色字段组合合法，当前及剩余 Tool Calls 必须是最近 assistant 消息尚未完成的唯一有序后缀。
- 恢复分支在 `finally` 先按 `authorization_id` 核对底层提交事实：已有结果则完成 receipt 提交，确认未提交才释放相同 `resume_attempt_id`；应用进程退出后，新实例取得 `DataDirectoryWriterLease` 才能启动扫描且不接管旧 claim。已持久化为 rejected 的快照继续按原决定收敛为 `cancelled/rejected`，其余旧实例快照收敛为 `interrupted`；两者都阻断下游、写入带稳定 confirmation/Plan 身份的 Trace，并通过 `finalize_active_execution_plan()` 原子保存终态 Plan/回执和清除快照。重复扫描或重复 confirmation 不重复写终态；Trace exactly-once 投递留给全局失败机制，本 Task 只断言重复事件身份相同可去重。
- 错误、缺失、跨 Session 的 confirmation，变化的参数摘要、Session 修订号或运行实例编号都拒绝恢复；committed confirmation 只能恢复 receipt 或返回已提交状态，不再次执行。两个并发请求可以观察同一 authorized 状态，但最多一个认领恢复执行权。
- 聊天 confirmation 生成 `ChatOperationConfirmationBinding`；删除 confirmation 生成包含 URL `output_id + expected_index_version` 的 `DeleteOutputConfirmationBinding`。RequestService 交叉验证该 binding 与授权快照，API 不读取 `current_execution` 自行完成校验；
- `SessionExecutionState` 往返同时保存阶段、Gate、Task 控制状态、Artifact 引用与版本、唯一 `CurrentExecution` 分支、最近终态 Plan 和 confirmation 回执；普通 Turn 的下一版聚合只执行一次 CAS，不能出现阶段、Gate、Artifact 或 Plan 的部分更新，同一当前 Plan 不能重复保存在普通与活动字段中。
- `SessionTaskState` 保存当前唯一 pipeline 的完整生命周期、当前里程碑和 frozen `SessionTaskItem`；验证 task/sort 编号唯一、milestone/parent 引用存在、blocked_by 无自引用/重复/环以及 lifecycle 与任务状态一致。任务创建、认领、完成和阶段切换不再读写 TaskStore。`GET /v1/tasks` 只从该字段返回当前任务投影，不保留历史任务列表；历史由终态 Plan 与 Trace 审计。`SessionArtifactState` 使用 exploration/market/opportunity/strategy/resume 的具体 frozen 子模型，只保存稳定 Artifact 引用、版本和业务关系；市场状态以 `latest_result` 与 `accepted_result` 区分可审计结果和可满足下游的已接受结果。
- `CurrentExecution = NoCurrentExecution | AsynchronousExecution | AuthorizationSuspendedExecution` 按 `execution_kind` 判别；同步 Plan 只在请求内运行，完成后 `current_execution=NoCurrentExecution` 且完整 Plan 进入 `last_terminal_execution_plan`。`AsynchronousExecution` 只表示真正跨请求、尚未结束且不等待授权的 Plan，本期没有请求分支构造它；后台市场 Job 使用独立 Job 状态。`pending_gate` 非空时只能选择 `NoCurrentExecution`。
- `SessionExecutionState.initial(session_id)` 固定创建 revision 0、explore 阶段、not_started Task、五类空 Artifact、无 Gate、无当前执行、无终态 Plan 和空 confirmation receipts；调用方不得各自拼装默认值。模型 JSON 往返只验证单快照关系；Artifact 版本回退由 SessionStore 的每个命名 CAS 比较 current/next 后拒绝，并以旧状态→新状态测试覆盖。
- `ExecutionPlanRequestService` 用真实 SessionStore、fake `ExecutionPlanTurnHandler` 和 fake `ExecutionPlanResumeHandler` 验证：两个 Handler 都只收到冻结聚合且不能写 Store；普通 Turn 一次命名 CAS；confirmation 按授权、claim、receipt、resuspend/finalize 的命名迁移分别 CAS；receipt 提交前不得调用 ResumeHandler。
- `ExecutionPlanRequestRejected` 穷尽覆盖 PlanBuildRejected、非法/失效 Gate、unsupported 纯规划请求、产物不存在、索引版本冲突、市场 confirmation 失效和 operation binding 错误；每种错误都有稳定 code，不能塞回 `PlanBuildError` 或异常字符串。
- `ExecutionPlanRequestService.handle()` 逐个覆盖 `ChatTurnRequest`、`MarketStartRequest`、`DeleteOutputRequest`、`GateDecisionRequest` 和 `OperationConfirmationRequest`；测试证明附件、市场确认引用、`output_id + expected_index_version` 和 Gate 决策进入具体 PreparedInput，不经过 `preset_proposals` 或 `request_context: dict[str, Any]`。删除请求只携带外部事实；RequestService 内部注入的 resolver 从同一 OutputIndexStore 版本快照解析并冻结只含产物身份、所属 Session、类型、展示名和观察版本的 target summary，API 与 TurnHandler 都不能预读 Store 或接受 `frozen_target`。
- Handler 返回的 `ExecutionPlanTurnResult` 保留尚未提交 transition；RequestService 成功提交后只返回不含 transition、携带 `committed_session_revision` 的 `ExecutionPlanRequestResult`。冲突、构建拒绝和已终结 confirmation 返回观察修订号，API 无法重复应用 transition。
- 授权暂停执行清除后重复 confirmation 返回 `OperationConfirmationAlreadyFinalized`；紧凑终态回执必须保存 operation 名称、调用编号和参数摘要。completed 分支由 RequestService 以这些身份从 durable ledger 读取首次规范化结果并转换为闭合 replay result，rejected/interrupted 分支不返回业务结果；即使 `last_terminal_execution_plan` 已被后续 Plan 替换，也不重新规划、授权、执行或伪造旧 presentation。
- Session 持久化同时包含 `last_terminal_execution_plan`（最近完整终态 Plan）和按 `confirmation_id` 唯一的 `operation_confirmation_receipts`（紧凑终态回执集合）；同一回执重复写幂等，不同 Plan 摘要、节点终态或身份冲突。当前 plan 不删除回执，TTL/归档留给全局失败机制。
- 同一 `DATA_DIR` 的实例 A 持有写入租约时，实例 B 启动明确失败；实例 A 退出释放租约后实例 B 才能启动并扫描。两个进程不能同时运行 Session CAS。模拟临时文件写入中断、原子 replace 前中断和 replace 后响应前中断，旧文件或新文件始终有一份完整 JSON，`session_revision` 不倒退。

- [ ] **Step 2: 直接重写默认 `/v1/chat`**

在 `chat.py` 以 `_parse_execution_plan_request()`（解析闭合执行计划请求）和 `run_execution_plan_chat_request()`（执行类型化聊天请求）直接替换旧入口：

- `_parse_execution_plan_request()` 把 Chat DTO、市场确认、删除 URL/body、Gate 解析结果或 operation confirmation 转成唯一 `ExecutionPlanRequest` 具体分支，不返回 Proposal、任意 request context 或 `list[str]`；
- `run_execution_plan_chat_request()` 只接收 `ExecutionPlanRequest` 并调用 `ExecutionPlanRequestService.handle(request)`；请求模块内部加载 Session、对新 Turn 调用 Task 8 的纯 `run_execution_plan_turn()` 并提交返回的状态迁移；
- 删除 `_apply_pending_gate()`、`run_coordinator_turn(..., pending_workers=...)` 和旧 handler 绑定；不提供请求参数或测试开关选择旧路径；
- API 集成测试直接验证默认 HTTP 入口与最终 Session 聚合。

`ChatRequest`（聊天请求）增加 `operation_confirmation: OperationConfirmationInput | None`；普通聊天继续要求 message 或 attachment，只有携带 `session_id + operation_confirmation` 时 message 可以为空。两阶段删除端点转换成同一个内部确认命令，不另建状态机或临时拒绝分支。

`execution_plan_requests.py` 定义 `ExecutionPlanTurnHandler` 和 `ExecutionPlanResumeHandler`。二者都是 persistence-free seam：可以调用 LLM、Runner 和 Harness operation seam，但不能持有或写入 SessionStore。RequestService 注入唯一 SessionStore、两个 Handler 和 Harness operation invoker；普通 Turn 执行“加载聚合 → TurnHandler → 校验 transition → 对应命名 CAS → 转换公开结果”，恢复请求执行命名 CAS 协议并只在 receipt 持久化后调用 ResumeHandler。

```python
class ExecutionPlanTurnHandler(Protocol):
    def __call__(
        self,
        *,
        session_state: SessionExecutionState,
        turn_request: NewExecutionPlanTurnRequest,
        runtime_context: CoordinatorRuntimeContext,
    ) -> ExecutionPlanTurnResult: ...


class ExecutionPlanResumeHandler(Protocol):
    def __call__(
        self,
        *,
        session_state: SessionExecutionState,
        suspended_worker_run: SuspendedWorkerRun,
        committed_receipt: CommittedOperationReceipt,
        runtime_context: CoordinatorRuntimeContext,
    ) -> ExecutionPlanTurnResult: ...


class ExecutionPlanRequestService:
    def handle(
        self,
        request: ExecutionPlanRequest,
    ) -> ExecutionPlanRequestResult: ...
```

`session_state`（Session 执行聚合参数）是 Handler 可读的冻结事实快照；`turn_request`（新本轮请求）是聊天、市场、删除或 Gate 决策的具体冻结分支；`committed_receipt`（已提交 operation 回执）证明当前确认的副作用结果已经进入聚合，ResumeHandler 不接收原始 confirmation，也不能再次执行该 operation。`ExecutionPlanRequestResult` 不含内部 transition。

应用组合根显式构造唯一 `CoordinatorRuntimeContext`、SessionStore、TurnHandler、ResumeHandler 和 RequestService。`CoordinatorRuntimeContext` 不包含 SessionStore，API 层不能自行创建第二组 Registry、Runner、Adapter 或 Store。

若 `current_execution` 是 `AuthorizationSuspendedExecution`，RequestService 只接受来源 binding 与快照完全匹配的 `OperationConfirmationRequest` 并进入恢复分支；其他请求返回绑定冲突。reject 走 cancelled 收敛；confirm 依次完成授权、claim、冻结 operation、receipt 提交，再把 `SessionExecutionState + SuspendedWorkerRun + CommittedOperationReceipt` 交给 ResumeHandler。ResumeHandler 调用 `resume_worker_invocation()` 并推进或再次暂停 Plan，不调用 analyze、不重建 Invocation、不重选 Adapter，也不重跑整个 Worker。

在 `gate.py` 增加：

```python
def create_reuse_decision_gate(
    plan_result: PlanNodeResult,
) -> ReuseDecisionGate | HarnessError: ...


def resolve_reuse_decision(
    user_message: str,
    pending_gate: ReuseDecisionGate,
) -> ReuseDecision | GateDecisionUnresolved: ...
```

- `create_reuse_decision_gate`（创建复用决策 Gate）：只接受包含 `ReuseRecommendationOutcome` 的已完成来源节点结果，复制 plan/node 身份和 Outcome 中由 Contract 从 Invocation 固定的 `eligible_candidates`，生成不可变的 `reuse_confirm`；它不能读取 Worker 原始输出或自行补候选。
- `resolve_reuse_decision`（解析复用决策）：把用户输入解析为 `skip_optimization`、`incremental_optimize` 或 `new_full_optimize`，校验选定交付物与 Gate 的 `eligible_candidates` 之间的关系；它不修改 Session、不创建 Proposal，也不设置默认动作。
- `ReuseDecisionGate`（复用决策 Gate）：持久化等待用户补充的闭合输入，字段包括来源 Plan、建议节点、不可变 `eligible_candidates` 和允许动作。
- `ReuseDecision`（复用决策）：用户下一 Turn 的已验证控制输入；Harness 使用它选择终态空 Plan、增量优化 Plan 或新建完整优化 Plan。
- `GateDecisionUnresolved`（决策未解析）：保留含糊、冲突或引用越界的结构化原因；调用方保持原 Gate pending。

`SessionStore` 对两类不同生命周期的数据使用不同命名 CAS：

- `ReuseDecisionGate` 属于 Additional Input Gate，只保存由上个已结束 Plan 的 Outcome 派生的决策输入，不保存上个 Plan 或 WorkerInvocation。Harness 先构建并验证新 Turn 的 Plan，再以来源 Gate 身份 compare-and-set 清除 Gate并发布新 Plan。
- `AuthorizationSuspendedExecution` 只用于 `operation_authorization`，必须在 `current_execution` 的唯一分支中保存当前尚未结束的完整 ExecutionPlan、`SuspendedWorkerRun`、按 `continuation_kind` 判别的 `OperationContinuation`、`runtime_instance_id` 和 `OperationAuthorizationWait`。第一次请求用 `suspend_execution_turn(next_state)` 原子发布完整聚合；后续 confirm 用 `authorize_operation_confirmation(next_state)` 完成或幂等读取 `waiting → authorized`，再用 `claim_authorized_operation(next_state)` 写入 `active_resume_attempt_id` 独占执行权；reject 用 `reject_operation_confirmation(next_state)` 完成 `waiting → rejected` 并进入 cancelled 收敛。提交前失败用 `release_authorized_operation_attempt(next_state)`；底层结果返回后用 `commit_authorized_operation_result(..., receipt, next_state)` 原子保存 receipt；再次暂停和终结分别使用完整 `next_state` 的 `resuspend_active_execution_plan()` 与 `finalize_active_execution_plan()`。

`CommittedOperationReceipt`（已提交操作回执）至少包含 `authorization_id`（授权编号，用作底层幂等键）、`operation_call_id`（操作调用编号；ReAct 分支等于原 Tool Call 编号，确定性分支由 Harness 预先生成）、`operation_name`（操作名称）、`arguments_hash`（规范化参数摘要）、`canonical_result_json`（规范化结果）、`result_hash`（结果摘要）和 `committed_at`（提交时间）。receipt 必须与 `operation_committed` 原子保存，不能先推进状态再单独写结果。

本 Task 扩展 Task 5 已建立的独立 `OperationDefinition`、`OperationRegistry` 与 `DurableResultLedgerRegistry`：`operation_name`（操作名称）统一连接 Invocation、Tool 映射、授权与 Trace；`requires_authorization`（是否需要用户授权）声明是否进入暂停协议；`durable_result_ledger_id`（持久化结果账本编号）指向可按 `authorization_id` 保存和查询首次规范化 receipt 的唯一账本。`ToolDefinition` 不增加这些字段，只保留模型可见调用形式。凡 `requires_authorization=True` 的 operation 都必须拥有非空且可解析的 durable ledger，并绑定一个以 `authorization_id` 幂等的领域 handler；不需要授权的 operation 必须没有 ledger 绑定。本 Task 用依赖注入的 fake ledger 与 fake handler 验证通用 SessionStore 协议，`asset.delete_output` 在 Task 10 接入 `OutputIndexStore.delete_authorized()` 和 `deletion_receipts` 后才允许进入默认启动目录。没有 ledger 的 operation 不得进入暂停/恢复路径。

`OperationRegistry.resolve()`（解析操作）按名称返回唯一冻结 `ResolvedOperation(definition, handler)`；`OperationRegistry.validate_startup()`（校验操作目录）验证 operation 名称唯一、每项恰有一个同名 handler、授权字段组合、ledger 存在且声明持久化，并确保全部 Worker Definition 的 `allowed_operations` 都能解析。当前 Harness 只能调用该绑定；后续全局失败机制的唯一 `OperationExecutor` 也调用同一 `resolve()`，不能接受调用方 handler，`OperationPolicyRegistry` 与它共同消费该 Registry，不得复制 operation 授权元数据或保留第二条执行 seam。

`execution_state.py` 一次定义 `SessionTaskItem/SessionTaskState`、五类阶段 Artifact 状态、闭合 `SessionPendingGate`、`NoCurrentExecution/AsynchronousExecution/AuthorizationSuspendedExecution` 和 `SessionExecutionState`。聚合固定写入单个 `execution-state.json`；同步 Plan 不进入当前槽位，跨请求 Plan 只存在于唯一 `current_execution` 分支。新系统只从干净 DATA_DIR 创建 schema v1，不读取或迁移旧 Session、Task、Artifact 文件。

`writer_lease.py` 建立 `DataDirectoryWriterLease.acquire(...)`。SessionStore 每次只发布一个聚合 JSON；临时文件、fsync、replace 和父目录同步保证旧版或新版聚合至少一份完整存在，不再需要跨 Session state/artifact/TaskStore 的事务或兼容投影。

市场方案存储同步增加 `confirmation_id`：draft 和 revise 后必须为空；第一次确认生成；同版本重复确认幂等；修订后的新确认生成新编号。API 的确认响应、启动请求、后台 Job 引用和 `MarketResearchAcceptedOutput` 都携带该编号。

- [ ] **Step 3: 明确三类 Gate**

本 plan 只落实创建 Plan 的生命周期差异：

- Operation Authorization：同 Plan 等待；允许在同一 Session、同一运行实例内跨第一次暂停请求和后续确认/恢复请求继续；确认状态只推进一次 `waiting → authorized`，但同一 confirmation 可幂等观察 authorized，执行权由 `active_resume_attempt_id` 单独串行化，在 `operation_committed` 前必须保留可重试的 continuation；
- Workflow Transition：当前 Plan 结束，确认后新 Turn；reject 必须按 Gate 名称穷尽：`explore_complete` 重新开放 explore，`market_research_required` 停留当前阶段且不启动研究，`market_result_confirmation` 保留未接受结果并创建 `MarketResultFollowUpGate`，`optimize_confirm` 停留 resume_strategy 且不执行 resume/asset。消费后的 Gate 编号不得复用；
- Additional Input：当前 Plan 结束，补充后新 Turn；优化档位、闭合三选一 `reuse_confirm` 和市场结果后续选择都属于此类。`MarketResultFollowUpGate` 只允许修改条件重跑、原条件重跑或暂停，任何重跑都在新 Turn 创建新 Plan。

完整 Run 状态、授权 TTL 和通用失败传播由全局失败 plan 实现；本 plan 只实现授权所需的最小 terminal convergence：用户拒绝为当前节点 `cancelled`，包括重启扫描遇到已经持久化的 rejected 快照；未完成拒绝收敛的其他旧运行实例快照才把当前节点标为 `interrupted`。两者都把下游置为 `blocked_by_upstream`，并通过 `finalize_active_execution_plan()` 原子保存完整终态 Plan、confirmation 终态回执和清除活动快照。confirmation 必须绑定 Session、Plan、节点、Worker Run、Invocation、operation 和参数摘要。

- [ ] **Step 4: 转绿**

```bash
cd backend && uv run pytest \
  tests/api/test_chat_intent_phase.py \
  tests/api/test_explore_gate_phase.py \
  tests/api/test_active_execution_plan_session.py \
  tests/platform/test_data_directory_writer_lease.py \
  tests/platform/test_operation_registry.py \
  tests/platform/test_market_research_plan_intent.py \
  tests/platform/test_market_research_service_recovery.py \
  tests/harness/test_reuse_decision_gate.py \
  tests/e2e/test_resume_levels.py \
  tests/e2e/test_asset_register.py \
  tests/e2e/test_strategy_asset.py -q
```

---

## Task 10: 引入稳定产物 ID、授权和版本化索引

**Files:**

- Create: `backend/career_os/platform/output/models.py`
- Create: `backend/career_os/platform/operation/output_index_ledger.py`
- Modify: `backend/career_os/platform/store/output.py`
- Modify: `backend/career_os/platform/tool/handlers/outputs.py`
- Modify: `backend/career_os/agents/graphs/workers/deterministic_adapters.py`
- Modify: `backend/career_os/agents/lc/tools.py`
- Modify: `backend/career_os/api/sessions.py`
- Modify: `backend/career_os/api/execution_plan_requests.py`
- Modify: `backend/career_os/harness/chat_attachments.py`
- Modify: `backend/career_os/harness/executor.py`
- Modify: `backend/career_os/platform/operation/registry.py`
- Create: `backend/tests/platform/test_output_index.py`
- Modify: `backend/tests/store/test_output.py`
- Modify: `backend/tests/harness/test_outputs_scan.py`
- Create: `backend/tests/api/test_outputs_api.py`
- Modify: `backend/tests/platform/test_durable_result_ledger.py`
- Modify: `backend/tests/e2e/test_asset_register.py`
- Modify: `web/src/components/OutputsPanel.tsx`
- Modify: `web/src/lib/chatAttachments.ts`

- [ ] **Step 1: 写身份、版本、授权和干净初始化红灯测试**

通过 `OutputIndexStore` 公开接口验证：

- 唯一索引文件是 `settings.data_dir / "outputs-index.json"`；schema v2 快照包含非负全局 `index_version` 和跨 Session 冻结条目，每个活动条目拥有全局唯一、登记后不变的 `output_id`；
- `read_snapshot(session_id=None)` 返回全部条目，提供 Session 时只过滤 entries 且保留同一个全局版本；其他 Session 成功写入后，基于旧全局版本的写请求得到版本冲突；
- 路径、文件名或展示字段变化不改变 `output_id`，调用方不能用路径查找或删除产物；
- `GET /outputs` 的公开条目不返回内部 `path`；`GET /outputs/{output_id}/view` 由索引校验活动条目并解析内部路径，旧 `/outputs/view?path=...` 路由不存在；
- 前端产物列表、打开、拖拽和聊天附件只传 `output_id`；`OutputAttachmentRef` 持久化 `output_id`，后端在当前 Session/作用域内解析路径，伪造或跨 Session 编号被拒绝；
- `register(..., expected_index_version=N)` 只有在当前版本为 N 时成功，为新交付物生成编号并返回 N+1；版本冲突不写文件索引、不递增版本；
- `OutputDeleteAuthorization` 绑定 `authorization_id + session_id + output_id + operation=delete_output + expected_index_version`；第一次成功删除只发生一次，相同编号与完全相同绑定的重试返回持久化的首次成功结果且不递增版本，相同编号的不同绑定、跨 Session 或版本冲突明确拒绝；
- `delete_authorized()` 只在存储内部用 `output_id` 解析路径，通过同文件系统隔离区 + 删除 journal + 索引 atomic replace 实现可恢复提交；成功后文件和索引项同时消失且版本严格递增 1，提交前失败回滚，模拟崩溃后的首次读取能幂等完成或回滚；
- 成功快照在删除条目和递增版本的同一次 atomic replace 中追加 `OutputDeletionReceipt`；模拟“索引已提交、响应或 journal 清理前中断”后，重放同一授权返回 receipt 中的原 `new_index_version`，不再次删除；
- 第一次 `POST /outputs/{output_id}/delete-confirmations` 接收 `session_id + expected_index_version`，构造固定 `asset.delete_output` Proposal 并经共享类型化 Plan 请求服务运行到授权点；响应返回 `confirmation_id + 删除对象摘要`，且在活动 Plan 快照持久化前不响应、在本请求中不删除文件或修改索引；
- 第二次 `POST /outputs/{output_id}/delete-confirmations/{confirmation_id}/confirm` 校验 Session、URL `output_id`、冻结版本和全部授权 binding，恢复原 Plan 且不运行 Coordinator analyze、不创建新 Plan/Invocation/Worker Run；合法请求只提交一次删除，相同绑定的重复确认返回首次结果，错 Session、产物、版本或 confirmation 明确拒绝；
- 把 Task 9 的通用双请求授权 fixture 替换为真实 `asset.delete_output + OutputIndexStore` 集成：deterministic Adapter/operation 首次结果生成 `OutputDeletionReceipt`，SessionStore 再原子保存 `CommittedOperationReceipt`；分别覆盖两个 receipt 之间和 Session receipt 后/Runner 继续前的中断点；
- 干净 `DATA_DIR` 中索引不存在时直接创建 `index_version=0, outputs=(), deletion_receipts=()`；存在旧 `profile.outputs_index` 也不得读取、迁移、合并或清理；
- 新文件存在后永不读取、合并或清理旧 Profile 列表；旧字段作为可丢弃历史数据保持不可见，不设置迁移或清理崩溃点测试。

- [ ] **Step 2: 建立强类型 OutputIndexStore seam**

在 `platform/output/models.py` 建立并逐字段解释：

- `RegisteredDeliveryRef`（已登记交付物引用）：包含稳定 `output_id`、内部 `path`、`session_id`、可选档位和创建时间；
- `OutputIndexSnapshot`（产物索引快照）：包含 `schema_version=2`、`index_version`、冻结 entries 和永久保留的 `deletion_receipts`；
- `OutputDeleteAuthorization`（产物删除授权）：包含授权身份及其绑定上下文；同一绑定可幂等读取首次结果，不能再次产生副作用；
- `OutputDeletionReceipt`（产物删除回执）：除 `authorization_id + session_id + output_id + expected_index_version + new_index_version + deleted_at` 外，还包含通用持久化结果所需的 `operation_call_id + operation_name + arguments_hash + canonical_result_json + result_hash`，作用是让响应丢失或进程重启后的同一请求返回首次提交结果，并可无损映射为 `DurableOperationResult`；
- `OutputRegistrationResult`（产物登记结果）与 `OutputDeletionResult`（产物删除结果）：使用 Literal discriminator 表达成功或版本/授权冲突，成功分支返回新索引版本。

`OutputIndexStore.read_snapshot/register/delete_authorized` 是索引读取和修改的唯一公开接口。构造函数从 `settings.data_dir` 派生唯一 `outputs-index.json` 路径；版本比较、路径规范化、同文件系统隔离、删除 journal、receipt、索引 atomic replace、崩溃恢复和失败回滚都封装在该模块内。ProfileStore、handler、API、Worker Contract 不得读写 `profile.outputs_index` 或索引 JSON。

`OutputIndexDeletionLedgerAdapter`（产物删除账本适配器）使用固定 `ledger_id="output_index_deletions"`，并与删除 handler 共享同一个 `OutputIndexStore`。`load_committed_result()` 只把已经存在的 `OutputDeletionReceipt` 映射为 `DurableOperationResult`；`save_committed_result()` 不能单独创建 receipt，只有 Store 的删除提交协议可在同一 journal/索引发布过程中保存删除事实与完整 receipt，外部对不存在删除事实的保存请求返回 `deletion_fact_missing`。重建 Store 与 Adapter 后必须仍能读取首次结果。

- [ ] **Step 3: 重写 asset Invocation、Contract、Tool 和 API**

- `RegisterOutputsPreparedInput` 增加 `expected_index_version`；输出和 `RegisteredDeliveriesOutcome` 增加 `new_index_version`。Contract 验证每个登记项的 `output_id`、输入一一对应关系和版本严格 +1。
- `DeleteOutputPreparedInput` 与物化后的 `DeleteOutputInput` 固定为 `output_id + expected_index_version`；`authorization_id` 不是用户或 Proposal 提供的业务输入，而是在确定性 Runner 把冻结 operation 交给 Harness、进入授权暂停时生成，并保存在 `OperationAuthorizationWait + DeterministicOperationContinuation` 中。恢复执行时 Harness 用该编号构造 `OutputDeleteAuthorization`；输出改为 `deleted_output_id + new_index_version`。Contract 通过 Invocation、结构化输出和注入的索引 verifier 验证产物、冻结版本、删除事实和版本严格 +1，授权身份一致性由授权快照、`OutputDeletionReceipt` 与 `CommittedOperationReceipt` 的交叉校验保证。
- 删除 API 改为独立两阶段端点，但不建立第二条执行链。第一次 `POST /outputs/{output_id}/delete-confirmations` 只把 `session_id + output_id + expected_index_version` 构造成 `DeleteOutputRequest`；Task 9 的共享 RequestService 在内部从索引解析、校验并冻结对象摘要，再运行到授权点。Handler 内部生成唯一固定的 `asset.delete_output` Proposal。只有 `AuthorizationSuspendedExecution + SuspendedWorkerRun + DeterministicOperationContinuation + confirmation_id + authorization_id` 已写入唯一 `current_execution` 分支后才返回 `confirmation_id + 删除对象摘要`，且不产生删除副作用。第二次 `POST /outputs/{output_id}/delete-confirmations/{confirmation_id}/confirm` 接收同一 `session_id + expected_index_version`，把 URL `output_id` 与请求版本包装为 `DeleteOutputConfirmationBinding`，由同一 RequestService 校验 Session、冻结版本与全部授权 binding 后恢复原 Plan，不重新 analyze 或创建执行身份；API 不读取活动执行或自行取 authorization。`confirmation_id` 不能直接冒充 operation 授权编号，相同绑定的重复确认必须从 durable ledger 返回首次类型化结果。
- GET `/outputs` 改为从全局 OutputIndexStore 返回 `schema_version + index_version + outputs_index`；`session_id`/`kind` 只过滤 entries，不产生 Session 私有版本。
- GET `/outputs` 的公开条目删除内部 `path`，查看改为 `GET /outputs/{output_id}/view`；旧 path query 路由直接删除。
- `OutputsPanel` 的列表 key、查看 URL 和拖拽 payload 统一使用 `output_id`；`chatAttachments` 与后端 `OutputAttachmentRef` 只交换 `output_id`，由后端在 Session/索引范围内解析内部路径。Gate、复用选择和后续 Invocation 也只保存稳定编号。
- 所有运行时读写直接改用 OutputIndexStore，并以搜索门禁禁止引入 ProfileStore 双事实来源。
- `asset.reuse_outputs`、`ReuseDecisionGate` 和三个用户选择统一引用 `output_id`，清除 `delivery_id`/路径身份的遗留命名。
- 在 OutputIndexStore、登记结果、删除授权和崩溃恢复协议完成后，接线 `asset.register_outputs` 与 `asset.delete_output` 两个生产确定性 Adapter；Adapter 只调用上述公开 Store seam，并通过统一 `WorkerExecutionResult` 返回结构化结果，不能直接读写索引 JSON 或 Profile 旧字段。
- 只有完成上述接线并通过真实双请求测试后，才把 `asset.delete_output` 的 `requires_authorization=True + durable_result_ledger_id="output_index_deletions"` 加入生产 operation 目录；Task 9 的 fake ledger 不得进入生产注册表。
- 生产 operation 目录把 `delete_output` 的唯一 handler 和 `OutputIndexDeletionLedgerAdapter` 绑定到同一个 `OutputIndexStore`；Harness 只通过 `OperationRegistry.resolve("delete_output")` 取得该 handler，不允许删除 API 或 Tool 调用方传入另一实现。
- 不保留旧 API 兼容响应，也不得把用户路径反查为 `output_id`。

- [ ] **Step 4: 转绿并检查原子性**

```bash
cd backend && uv run pytest \
  tests/platform/test_output_index.py \
  tests/platform/test_durable_result_ledger.py \
  tests/store/test_output.py \
  tests/harness/test_outputs_scan.py \
  tests/api/test_outputs_api.py \
  tests/api/test_active_execution_plan_session.py \
  tests/e2e/test_asset_register.py -q
cd ../web && npm run build
```

测试结束后用搜索确认运行时代码中不存在按外部 path 查看/附件/删除、无 expected version 的索引写入或把 `delivery_id` 当稳定身份的入口。

---

## Task 11: 完成最终路径集成、启用启动校验并清除旧事实来源

**Files:**

- Modify: `backend/career_os/platform/worker/registry.py`
- Modify: `backend/career_os/platform/worker/contracts.py`
- Modify: `backend/career_os/platform/worker/bindings.py`
- Modify: `backend/career_os/platform/operation/registry.py`
- Modify: `backend/career_os/platform/operation/ledger.py`
- Modify: `backend/career_os/platform/tool/registry.py`
- Modify: `backend/career_os/harness/executor.py`
- Modify: `backend/career_os/api/chat.py`
- Modify: `backend/career_os/api/execution_plan_requests.py`
- Modify: `backend/career_os/runtime/sse.py`
- Modify: `backend/career_os/agents/graphs/coordinator.py`
- Modify: `backend/career_os/agents/graphs/execution_plan_coordinator.py`
- Modify: `backend/career_os/agents/state/coordinator.py`
- Modify: `backend/career_os/agents/lc/coordinator_llm.py`
- Modify: `backend/career_os/agents/lc/tools.py`
- Modify: `backend/career_os/platform/prompt/loader.py`
- Modify or Delete: `backend/career_os/platform/prompt/coordinator/system.md`
- Modify or Delete: `backend/career_os/platform/prompt/{identity,capability,market,opportunity,strategy,resume,asset}/system.md`
- Modify: `backend/career_os/harness/explore_guidance.py`
- Modify: `backend/career_os/harness/session_activity.py`
- Delete: `backend/career_os/agents/schemas/workers.py`
- Modify: `backend/career_os/main.py`
- Modify: `web/src/hooks/useChatSSE.ts`
- Modify: `web/src/pages/ChatPage.tsx`
- Modify: `web/src/lib/sessionsApi.ts`
- Modify: `web/src/components/TaskProgress.tsx`
- Delete: `config/workers.registry.json`
- Modify: `backend/tests/api/test_chat_intent_phase.py`
- Modify: `backend/tests/api/test_explore_gate_phase.py`
- Modify: `backend/tests/agents/test_coordinator_c3.py`
- Modify: `backend/tests/agents/test_coordinator_trace.py`
- Modify: `backend/tests/agents/test_coordinator_phase_synthesis.py`
- Modify: `backend/tests/agents/test_synthesis_pipeline_context.py`
- Modify: `backend/tests/platform/test_worker_registry.py`
- Modify: `backend/tests/platform/test_worker_invocation_registry.py`
- Modify: `backend/tests/platform/test_operation_registry.py`
- Modify: `backend/tests/platform/test_durable_result_ledger.py`
- Create: `backend/tests/platform/test_tool_registry_schema_only.py`
- Create: `backend/tests/api/test_execution_plan_result_transport.py`

- [ ] **Step 1: 写启动完整性红灯测试**

通过临时 Registry 定义验证：

- 重复 `(worker_id, run_kind)`；
- 重复 definition_id；
- 未注册 operation；
- 不存在 Skill；
- required Skill 的 mode 不存在、mode 与 Worker 不匹配、required/optional 重复或两者重叠；
- 缺失 Prompt；
- 不存在或重复的 Success Contract id；
- 契约产出 WorkerRunDefinition 未声明的 Outcome；
- emitted Outcome 模型不属于闭合 `VerifiedOutcome` 联合；
- Definition 的准备输入、完整输入、Invocation、Contract 和 Outcome 泛型参数不一致；
- `AnyWorkerRunDefinition` 未显式枚举全部 15 个带 Literal `worker_id + run_kind` 的具体 Definition 子类，或退化为同一泛型基类的参数化别名、`WorkerRunDefinition[Any, ...]`、未参数化基类或其他宽泛别名；
- 15 个 Run Kind 中存在缺失、重复或未进入闭合联合的具体 Invocation；
- ReAct Definition 携带 `deterministic_adapter_id`，deterministic Definition 缺少/引用未知 Adapter，或 Adapter 编号重复；
- operation 标记 `requires_authorization=True` 但没有唯一、持久化且可按 `authorization_id` 读取首次规范化结果的 `durable_result_ledger_id`；
- `requires_authorization=False` 却携带 ledger、多个 ledger 使用同一编号、ledger 只提供进程内缓存，或 Worker Definition 的 allowed operation 未进入独立 `OperationRegistry`；
- `ToolDefinition` 或 `ToolRegistry` 仍保存/执行 handler，默认 Harness 仍能绕过 `OperationRegistry.resolve()` 调用旧 Tool handler，或同一 operation 在 ToolRegistry 与 OperationRegistry 存在两份可执行绑定；
- OutcomeBinding 的来源 Outcome、准备输入或完整输入与上下游 Definition 不一致；
- 已解析 seam 暴露裸 `BaseModel inputs`、`Any` 或字符串 Outcome 字典；
- PreparedInput、完整 Input、WorkerStructuredOutput、VerifiedOutcome 和 Plan 模型递归包含 `list`、`dict`、`set`、`MutableSequence`、`MutableMapping` 或未冻结 Pydantic 子模型；
- 依赖环；
- 同等条件下动作定义歧义。

本 plan 的 `DeterministicSuccessContractRegistry.validate_startup()` 是确定性契约完整性的唯一校验入口；`DurableResultLedgerRegistry.validate_startup()` 先验证账本编号、持久化级别和 operation 支持集合，`OperationRegistry.validate_startup(durable_ledgers=...)` 再验证 operation 授权元数据与账本绑定。后续全局失败 plan 必须复用这些 Registry，不能用声明目录常量或第二份 Registry 替换。

上述启动校验只验证 Adapter 声明的 `durability`、`supported_operations` 和 Registry 绑定一致性，不能证明实现真的跨进程持久化。`test_durable_result_ledger.py` 必须枚举默认启动目录中的每个 ledger Adapter：先由实例 A 提交首次结果，销毁实例 A，再使用同一持久化目录构造实例 B，断言实例 B 对相同 `authorization_id + operation_call_id + operation_name + arguments_hash` 返回同一规范化结果且不再次执行副作用。缺少该重启/重建一致性测试的 Adapter 不得进入默认目录。

- [ ] **Step 2: 启用启动校验并完成最终 API、Coordinator、Runner、Prompt 与状态集成**

该 Step 是一次性重写后的最终集成检查点，不承担迁移期切换。启动顺序固定为取得 `DataDirectoryWriterLease` → `DurableResultLedgerRegistry.validate_startup()` → `OperationRegistry.validate_startup(durable_ledgers=...)` → Worker/Contract/Binding Registry 校验 → 旧运行实例活动 Plan 扫描；任一租约或校验失败必须阻止应用启动。

1. 默认 `/v1/chat` 只使用 Task 9 的 `_parse_execution_plan_request()` 与 `run_execution_plan_chat_request()`，并只通过 `ExecutionPlanRequestService.handle()` 加载/提交 Session；旧入口必须已经删除；
2. 默认 API 只调用 `ExecutionPlanRequestService`；普通请求委托 TurnHandler 并提交一次完整聚合 CAS，活动 Plan confirmation 按命名 CAS 协议处理并在 receipt 提交后委托 ResumeHandler；
3. `runtime/sse.py`、`useChatSSE` 和 `ChatPage` 穷尽消费 `ExecutionPlanRequestResult`：等待授权使用独立 `operation_confirmation_required` 事件和明确的确认/拒绝控件，控件只提交结构化 confirmation；业务拒绝、冲突和已终结重放保持各自稳定语义；
4. `/v1/tasks` 与 `sessionsApi/TaskProgress` 只展示当前 `SessionTaskState`，删除旧 `lists/active_list_id` 历史列表契约；所有 TaskStore 调用方必须改写到 Session 聚合或删除，不建立兼容投影；
5. analyze、delegate、Runner、Tool Schema、Prompt 和结果展示分别只使用 `analyze_invocation_proposals()`、`delegate_invocation()`、`run_worker_invocation()`、`get_litellm_tools_for_invocation()`、`invocation_analyze_system.md + invocation_system.md + runs/<run_kind>.md` 与 `PlanResultPresenter.render()`；
6. 确认 `CoordinatorState/WorkerState` 已在前序 Task 重写为 ExecutionPlan/Invocation 形态，且不存在 `pending_workers/current_worker_id` 和可独立变化的 Worker 状态副本；
7. 显式 `list_type="plan"` 没有旧执行分流；直到后续纯规划链 Spec/Plan 落地前只返回结构化 unsupported 结果；
8. 搜索确认旧四参数 Runner、旧 delegate/capability 入口、旧字符串 analyze/schema、旧 `get_litellm_tools_for_worker()`、旧 `list[str]` 探索 helper、旧 Worker 级通用输出 Schema、`enhance_worker_summary_with_llm` 和旧 Prompt/loader 已在前序 Task 删除；
9. 把现有 `ToolDefinition.handler` 和 `ToolRegistry.execute()` 执行职责迁出：ToolRegistry 只返回模型可见名称、角色和参数 Schema；所有默认领域 handler 通过显式 Adapter 注册到 `OperationRegistry`，Harness 的 `execute_tool()` 先完成 Tool 可见性/参数校验，再只调用 `OperationRegistry.resolve(operation_name).handler`。删除旧 handler 字段和直接执行分支，并以启动测试证明每个 Tool 映射的 operation 恰有一个执行绑定；
10. 所有调用方和测试 fixture 只使用最终接口；旧契约测试直接删除或重写。Task 11 不负责维持任何迁移兼容状态。

用 `rg` 证明旧入口没有运行时引用，并运行默认 `/v1/chat` 的 Pipeline、Gate 暂停/恢复和 resume → asset 回归。纯规划链不在本 plan 的运行回归范围内。

- [ ] **Step 3: 删除手写 JSON 和旧加载路径**

删除 `config/workers.registry.json`，`WorkerInvocationRegistry` 不接受 JSON path。测试若需要自定义定义，直接注入闭合 `AnyWorkerRunDefinition` 联合中的定义。

- [ ] **Step 4: 转绿**

```bash
cd backend && uv run pytest \
  tests/platform/test_worker_registry.py \
  tests/platform/test_worker_success_contract.py \
  tests/platform/test_required_skill_preloader.py \
  tests/platform/test_worker_invocation_registry.py \
  tests/platform/test_operation_registry.py \
  tests/platform/test_durable_result_ledger.py \
  tests/platform/test_tool_registry_schema_only.py \
  tests/api/test_chat_intent_phase.py \
  tests/api/test_explore_gate_phase.py \
  tests/api/test_active_execution_plan_session.py \
  tests/agents/test_coordinator_execution_plan.py \
  tests/agents/test_coordinator_c3.py \
  tests/agents/test_coordinator_trace.py \
  tests/agents/test_coordinator_phase_synthesis.py \
  tests/agents/test_synthesis_pipeline_context.py -q
uv run pyright
```

---

## Task 12: 全量范围检查和强类型计划验收

**Files:**

- Verify only: `backend/tests/**`（最终测试只使用目标接口；本 Task 只搜索和运行验收）
- Verify only: `backend/career_os/harness/chat_attachments.py`
- Verify only: `web/src/components/OutputsPanel.tsx`
- Verify only: `web/src/lib/chatAttachments.ts`
- Verify only: `web/src/components/TaskProgress.tsx`
- Verify only: `web/src/hooks/useChatSSE.ts`
- Verify only: `web/src/pages/ChatPage.tsx`
- Verify only: `web/src/lib/sessionsApi.ts`
- Modify: `backend/typecheck/worker_invocation_contracts.py`
- Modify: `backend/pyproject.toml`
- Reference only: `docs/superpowers/specs/2026-07-23-global-failure-mechanism-design.md`

- [ ] **Step 1: 搜索并验证旧公开接口已经消除**

运行：

```bash
rg -n 'pending_workers|current_worker_id|plan_node_results|runner\\(worker_id|build_stub_worker_runner\\(|workers\\.registry\\.json|get_litellm_tools_for_worker' backend config
rg -n 'inputs: BaseModel|verified_outcomes: Mapping\\[str, Any\\]|resolve\\([^)]*verified_outcomes|target_input_field|WorkerRunDefinition\\[Any|AnyWorkerRunDefinition: TypeAlias = WorkerRunDefinition|ResumeAssetWorkerInvocation|ResumeAssetPlanNodeResult|StrategyCareerPlanDefinition|CareerPlanInvocation' backend/career_os/platform/worker backend/typecheck
rg -n 'WORKER_SCHEMAS|validate_structured_output|enhance_worker_summary_with_llm|user_visible_summary|session_state: dict\\[str, Any\\]' backend/career_os/agents backend/career_os/platform/worker
rg -n 'delete_output\\([^)]*path|DELETE.*encoded_path|selected_delivery_id|deleted_delivery_id|delivery_id' backend/career_os backend/tests
rg -n 'profile_patch.*Any|profile_patch.*dict|value.*JSON' backend/career_os/platform/worker backend/career_os/agents/lc
rg -n 'ProfileStore.*outputs_index|profile\\.outputs_index|patch\\(.*outputs_index' backend/career_os backend/tests
rg -n 'view\\?path|encoded_path|attachment\\.path|output_path|delivery_id|selected_delivery_id|deleted_delivery_id' web/src backend/career_os/harness/chat_attachments.py backend/tests/harness/test_chat_attachments.py
rg -n 'handler[=:]|ToolDefinition\\([^)]*handler|ToolRegistry.*execute|def execute\\(' backend/career_os/platform/tool/registry.py
rg -n 'TaskStore|platform\\.store\\.task|lists.*active_list_id' backend/career_os web/src backend/tests
rg -n 'OrdinaryExecution|ActiveExecution|frozen_target|API.*OutputIndexStore' backend/career_os backend/tests
```

期望：默认代码和全部测试 fixture 不再使用旧接口。`session_state: dict` 不得出现在解析后的 Runner、Turn/Resume Handler 或 RequestService 接口；这些位置只接受冻结 `SessionExecutionState` 或更窄模型。`list_type="plan"` 不得命中任何执行 Adapter。前端和聊天附件不得命中对外 path/view-query 或 `delivery_id` 身份；Tool Registry 不得保存可执行 handler；运行时不得引用 TaskStore、旧历史任务列表 DTO、`OrdinaryExecution/ActiveExecution` 旧名或让 API 预解析 `frozen_target`。

- [ ] **Step 2: 跑强类型定向测试**

```bash
cd backend && uv run pytest \
  tests/platform/test_worker_invocation_registry.py \
  tests/platform/test_worker_success_contract.py \
  tests/platform/test_execution_plan.py \
  tests/platform/test_profile_patch_types.py \
  tests/platform/test_output_index.py \
  tests/platform/test_market_research_plan_intent.py \
  tests/platform/test_required_skill_preloader.py \
  tests/agents/test_worker_invocation_runner.py \
  tests/agents/test_coordinator_execution_plan.py \
  tests/harness/test_delegate_rules.py \
  tests/harness/test_pipeline_phase_advance.py \
  tests/harness/test_chat_attachments.py \
	  tests/api/test_chat_intent_phase.py \
	  tests/api/test_active_execution_plan_session.py \
	  tests/api/test_execution_plan_result_transport.py \
	  tests/api/test_current_tasks_api.py \
	  tests/api/test_outputs_api.py \
	  tests/platform/test_session_task_state.py \
  tests/e2e/test_resume_levels.py \
  tests/e2e/test_asset_register.py \
  tests/e2e/test_strategy_asset.py -q
cd ../web && npm run build
```

- [ ] **Step 3: 跑全部非 LLM 回归**

```bash
cd backend && uv run pytest tests/ -m "not llm" -q
uv run pyright
cd ../web && npm run build
```

期望：pytest 与 Pyright strict 全部通过。真实 LLM Eval 不作为本 plan 的默认完成条件，但其 schema fixture 必须已按最终契约直接重写。

- [ ] **Step 4: 做格式与工作区检查**

```bash
git diff --check
git status --short
```

确认：

- 未触碰 `docs/assets/`；
- 没有实现 OperationPolicyRegistry 或全局重试；
- 没有实现 Failure 分类、语义 Judge 或最终 Run 状态聚合；
- 没有第二份 Success Contract Registry，所有 verified Outcome 都来自 `DeterministicSuccessContractRegistry`；
- 两份 spec 和 plan 链接仍有效；
- 删除 JSON 后没有残留运行时读取。
- 没有把路径或 `delivery_id` 当作产物稳定身份，所有索引修改都带预期版本；
- 活动 Plan 的暂停响应只在闭合 continuation 已持久化后返回：ReAct 分支保存消息、迭代和 Tool Call，确定性分支保存 Adapter、Invocation 与冻结 operation；恢复分支不会重新调用 Coordinator、重新生成 Tool Call、重新选择 Adapter 或重跑整个 Worker；
- `PlanBuildRejected` 不携带 Plan，且不会提交阶段推进；
- 纯规划链和 `strategy.career_plan` 没有进入本期闭合类型、Definition、Prompt 或 Contract，也不存在 LegacyCareerPlanAdapter 或旧 plan 旁路。
- 旧四参数 Runner、旧字符串 analyze、旧 Worker 级 Schema 与 `enhance_worker_summary_with_llm` 均无运行路径引用；结果展示只通过 PlanResultPresenter 读取 Plan/Outcome。

- [ ] **Step 5: 人工语义验收**

在确定性 Runner 下验证：

```text
optimize_confirm
→ 新 Turn
→ resume.generate_optimized_resume ready
→ asset.register_outputs blocked; invocation=None
→ claim_next 原子写入 resume running + worker_run_id 并返回唯一 PlanDispatch
→ Coordinator 采用 claim 后的 Plan，再执行该 PlanDispatch
→ Harness 预加载 resume-module-optimize
→ 预加载成功后才调用 resume WorkerRunner
→ resume 产出 VerifiedHtmlDeliveriesOutcome
→ 强类型 binder 构造 RegisterOutputsInput
→ RegisterOutputsInvocation 物化
→ asset ready
```

另验证合法前向路由：

```text
current_phase=jd_analysis
→ Harness 计算 selectable_phases={jd_analysis, resume_strategy}
→ 模型索引包含 strategy.jd_application
→ Coordinator 提议 pipeline_phase=resume_strategy
→ Proposal、Gate 与 Plan 校验成功
→ 提交 current_phase=resume_strategy
```

对应负向路径必须保证任一 Proposal、Gate、输入或 Plan 校验失败时不提交阶段推进。

另验证 fan-in：A 在第一次 `advance()` finished 并持久化结果，B 在第二次 `advance()` finished；第二次只提交 B 的新结果，下游仍同时读取 A、B 的 Plan 内结果并变为 ready，Coordinator 不存在平行结果字典。

另验证缺少档位时：

```text
resume.collect_optimization_levels
→ Additional Input Gate
→ 当前 Plan 结束
→ 用户选择后新 Turn、新 Plan
```

另验证复用决策：

```text
asset.reuse_outputs
→ ReuseOutputsOutput(recommendation)，无 gate_prompt
→ deterministic contract emits ReuseRecommendationOutcome
→ Harness 持久化 reuse_confirm Additional Input Gate
→ 当前 Plan finished
→ 下一 Turn 解析闭合 ReuseDecision
├── skip_optimization: 终态空 Plan；返回既有交付物；不运行 resume/register
├── incremental_optimize: selected delivery 成为 resume_ref；创建 resume → asset Plan
└── new_full_optimize: 当前基线简历成为 resume_ref；创建 resume → asset Plan
```

档位缺失时，增量优化和新建完整优化都先只创建 `resume.collect_optimization_levels` Plan。含糊、冲突、候选越界或来源身份过期时保持原 Gate pending，不创建 Plan，也不得默认选择新建。

另验证市场异步提交：

```text
confirm market plan
→ persist confirmation_id + plan version/hash/session
market.start_research
→ validated MarketPlanConfirmationRef
→ create and persist job/confirmation reference
→ MarketResearchRunner.start accepts background execution
→ WorkerExecutionAcceptedAsync
→ parse MarketResearchAcceptedOutput
→ deterministic contract emits JobAcceptedOutcome
→ current Worker Run / Plan node success
→ persisted market task remains independent in MarketResearchRunner
```

另验证 required Skill 第二项加载失败时，Runner 不启动、失败结果 bundles 为空，但 Trace 同时含第一项 `loaded + content_hash` 和第二项 `failed + error code`。

另执行真实双请求授权场景：

```text
request 1: POST /outputs/{output_id}/delete-confirmations
→ validate session_id + expected_index_version
→ build fixed asset.delete_output Proposal
→ shared typed Plan chain reaches operation_authorization
→ persist AuthorizationSuspendedExecution as the sole current_execution branch
  + SuspendedWorkerRun
  + deterministic adapter/invocation/operation_call_id/frozen operation
  + confirmation_id
→ return confirmation_id + frozen output summary; file/index unchanged

request 2: POST /outputs/{output_id}/delete-confirmations/{confirmation_id}/confirm
→ validate same session/output/version/binding
→ waiting → authorized by session revision
→ claim active_resume_attempt_id by compare-and-set
→ resume same plan/node/worker_run/invocation/operation_call without Coordinator analyze
→ delete by output_id through OutputIndexStore using authorization_id as idempotency key
→ atomically publish global index_version + 1 + OutputDeletionReceipt
→ build CommittedOperationReceipt from persisted result
→ commit_authorized_operation_result: receipt + authorized → operation_committed
→ deterministic adapter complete_from_committed_receipt
→ finalize_active_execution_plan:
  last_terminal_execution_plan + confirmation terminal receipt + clear active snapshot
```

断言第二次请求没有 Coordinator analyze、没有新 Plan/Invocation/Worker Run、没有重新生成 Tool Call或重新选择 Adapter；验证 receipt 提交后只由 ResumeHandler 恢复。重复 confirmation 在授权暂停快照清除后返回 `OperationConfirmationAlreadyFinalized`：completed 必须以终态回执中的 operation 身份从 durable ledger 读取并返回首次 `deleted_output_id + new_index_version`，rejected/interrupted 不返回业务结果；即使最近终态 Plan 已变化也不重放。另验证干净 DATA_DIR 只创建一个初始为空的全局 outputs-index.json，且不读取、迁移或清理旧 Profile 索引。

本 plan 不执行“当前 Bug 的最终干净环境系统级回归”；该任务属于全局失败 plan 的最终系统验收阶段，因为只有 operation 事实、运行完整性、确定性契约结果和可选 Judge 完成聚合后才有意义。本 plan 已独立验收空交付物不能产生 `verified_html_deliveries`，并确保 asset 不会因此物化或执行。

---

## Completion Criteria

1. 所有 7 类 Worker、本期 15 个 Run Kind 都在 Task 4、Runner/Coordinator 重写之前拥有唯一具体 Definition 子类、准备/完整输入、Node Spec、Invocation、WorkerStructuredOutput、Outcome 和 Contract 类型；`strategy.career_plan` 不在本期目录中。
2. Coordinator 只输出 InvocationProposal，不输出字符串 Worker 队列。
3. 模型索引覆盖当前阶段和 Harness 判定可合法前向进入的阶段；Registry 和 Plan 的 `ExecutionScope` 本期只接受 `list_type="pipeline" + 具体 phase`，不使用复合阶段字符串或裸 `None` 猜测范围。索引计算不修改状态，只有 `PlanBuilt` 才允许提交阶段推进，`PlanBuildRejected` 返回结构化错误且不携带 Plan。
4. Plan 创建 `ExecutionPlanNodeSpec`；依赖未来 Outcome 的节点不持有输入不完整的 WorkerInvocation。
5. `WorkerInvocationRegistry.resolve()` 是 Invocation 创建唯一入口，只接收带来源身份的 `source_results`，按 `RequiredOutcome.source_node_id` 完成全部输入绑定后返回按 `worker_id + run_kind` 判别的闭合联合。
6. ExecutionPlan 的依赖、Required Outcome 强类型 binder、延迟物化和串行调度通过公开接口测试。
7. `ExecutionPlanExecutor.advance()` 只接收本次新结果，并通过闭合 `PlanAdvanceResult` 先校验后持久化到 finished 节点；任一 plan_id、node_id、mapping key、running 状态、重复结果或 worker_run_id 身份错误都返回原 Plan。ExecutionPlan 是累积结果唯一事实来源，fan-in 可跨多次推进。只有 `claim_next()` 能原子完成唯一节点的 `ready → running`、worker_run_id 绑定和 PlanDispatch 生成。
8. `asset.register_outputs` 在 verified delivery 缺失时既不会物化 WorkerInvocation，也不会 ready。
9. Task 5–9 直接以唯一 Runner、delegate、analyze、ExecutionPlan Coordinator、Session 聚合和 API 替换旧接口；中间态无需维持运行。最终 `pending_workers`、current_worker_id、旧字符串 analyze、四参数 WorkerRunner、旧 Worker 通用 Schema 和旧 summary 增强入口均被删除。
10. Tool/Skill/Prompt 的能力包络只由 Invocation 快照决定；required Skill 使用结构化名称与 mode，并在第一次 Worker LLM 调用前由 Harness 全部预加载；ReAct Worker LLM 保留包络内对 Tool/optional Skill 调用时机、顺序和参数的自主判断。
11. 任一 required Skill 预加载失败都会返回 `required_skill_preload_failed`，且不会调用 WorkerRunner、LLM、业务 Tool 或产生 verified Outcome；失败分支 bundles 为空，但 attempts 完整保留失败前成功哈希与最终错误供 Trace 使用；required Skill 不作为模型 Tool 暴露。
12. 真实 ReAct Runner、确定性 Adapter、mock、stub 使用同一 `WorkerInvocation + WorkerRuntimeContext` 起始 seam 和闭合 WorkerExecutionResult；`resume_worker_invocation()` 只消费 `SuspendedWorkerRun + CommittedOperationReceipt + WorkerRuntimeContext` 并按 continuation 穷尽分派，不再次执行 operation、不重选 Adapter、不重新生成或重排 Tool Call。确定性分支只调用原 Adapter 的 `complete_from_committed_receipt()`，该接口不能访问副作用执行入口。RuntimeContext 不含完整 Session 或业务事实，Definition 通过 `execution_strategy + deterministic_adapter_id` 唯一选择执行路径，Adapter 不作为 ReAct fallback。
13. 现有基础 Prompt 和 Skill 已完成职责清理：不再重复猜测 Run Kind/required Skill mode，不再要求加载 required Skill，不包含跨 Worker 或未授权 Tool 规则，也未把允许 Tool 固化为必执行序列。
14. `config/workers.registry.json` 已删除，启动完整性校验失败会阻止应用启动。
15. 三类 Gate 的 Plan 生命周期符合 spec；四类 Workflow Gate 的 reject 分别实现重新开放 explore、停留当前阶段不启动研究、创建市场结果后续选择 Gate、停留策略阶段不执行优化，旧 gate_id 不复用。其中 `reuse_confirm` 是由 Harness 从 `ReuseRecommendationOutcome` 创建的闭合三选一 Additional Input Gate，Worker/Contract/mock 不输出 Gate 或默认选择，三个选择只在新 Turn 形成各自后续 Plan；operation authorization 则持久化当前授权暂停 Plan、SuspendedWorkerRun 和闭合 continuation，按 ReAct/确定性 discriminator 恢复原执行点。
16. 定向测试、全部非 LLM 测试和 `uv run pyright` 全部通过。
17. 所有 15 个 Run Kind 的确定性 Success Contract 都由唯一 Registry 实现，WorkerExecutionCompleted、Schema 通过或 WorkerExecutionAcceptedAsync 不能直接产生 verified Outcome；`market.start_research` 只有在持久化 confirmation 与方案/后台 Job 身份一致、Job 已持久化且 `MarketResearchRunner.start()` 已接受后台启动，并经结构化输出和 Contract 验证后才立即 success；当前同步 Plan 随后终结为 `NoCurrentExecution`，后台 Job 独立执行且不创建 `AsynchronousExecution`。
18. `AnyWorkerRunDefinition` 显式枚举全部 15 个带 Literal `worker_id + run_kind` 的具体 Definition 子类；每个子类继承时展开五个具体泛型参数，`OutcomeDefinition`、`SuccessContract`、`ContractEvaluation` 和 `OutcomeBinding` 的泛型关系由 Pyright strict 检查，解析后不使用裸 `BaseModel inputs`、`Any` 或字符串字段绑定逃生。
19. 动态性只保留在 Agent/JSON Proposal 解析 seam，以及 Worker 原始输出解析与 Invocation/输出配对 seam；两个 seam 之后都恢复为闭合具体类型。新增 Run Kind 必须先增加具体类型并通过闭合联合、启动检查和静态类型门禁。
20. 没有提前实现 Failure 分类、重试、语义 Judge、Run Store 或最终 Run 状态聚合。
21. Node Spec、WorkerInvocation、PlanNodeResult、VerifiedOutcome 与 ExecutionPlan 满足深冻结不变量：`frozen=True` 禁止字段重赋值，嵌套业务值只使用 tuple、frozenset 或 frozen 具体子模型，Session/request/Outcome 源对象变化和直接嵌套修改都不能改写既有快照。
22. `ProfilePatch` 已从任意 JSON 收敛为按 `patch_kind` 判别的五个具体 frozen 模型；各 Run Kind 只能输出匹配的补丁变体，Pyright 可缩窄其 `value`。
23. `settings.data_dir / "outputs-index.json"` 是跨 Session 的全局 schema v2 索引唯一事实来源；干净目录首次创建空索引，不读取、迁移或清理旧 `profile.outputs_index`。每个条目拥有稳定 output_id，登记/删除严格递增版本。
24. 删除授权绑定 `authorization_id + session_id + output_id + operation + expected_index_version`；首次副作用只发生一次，索引快照原子持久化包含通用 operation 结果身份的 `OutputDeletionReceipt`，相同绑定重试返回首次结果且不递增版本，不同绑定重放拒绝。`OutputIndexDeletionLedgerAdapter` 与删除 handler 共享同一 `OutputIndexStore`，只映射已提交删除事实，不能单独制造 receipt；重建后仍能读取首次结果。
25. 市场方案确认已持久化 `confirmation_id`；同版本重复确认幂等，修订使旧编号失效，启动研究拒绝跨 Session、旧版本或摘要错配的确认。
26. API 集成测试证明第一次请求先把 `AuthorizationSuspendedExecution + SuspendedWorkerRun + OperationContinuation` 持久化为唯一 `current_execution` 分支再通过 `operation_confirmation_required` SSE 暂停，前端明确控件凭结构化 `operation_confirmation={confirmation_id, decision}` 处理授权，自然语言“同意”不授予权限。聊天/删除来源 binding 由 RequestService 与快照交叉校验，API 不预读当前执行。confirm 恢复同一身份与 operation call；ReAct 分支通过 `resume_worker_invocation()` 消费 receipt 并恢复原 Tool Call，同一 confirmation 不授权 sibling calls，`remaining_tool_calls` 保持原顺序和 `tool_call_id` 并在逐项执行前重新校验 Tool/operation、资源状态、参数摘要、预算、策略与授权要求。合法无需授权者执行，下一授权点生成新 confirmation 并再次暂停，上下文变化导致失效者追加 `OperationCallRejectedResult` 且不产生副作用；全部调用有匹配 tool 消息后才增加迭代。确定性分支只用 receipt 调用原 Adapter 的 `complete_from_committed_receipt()`。底层以 `authorization_id` 幂等提交，SessionStore 原子保存 `CommittedOperationReceipt + operation_committed`。operation 已提交/receipt 未保存和 receipt 已保存/Runner 未继续两个中断点都不重放副作用；快照清除后的 completed 重试从 ledger 返回首次类型化结果。
27. `OperationAuthorizationWait` 与 `AuthorizationSuspendedExecution` 在 JSON 解析时拒绝非法状态/receipt 组合、跨模型身份错配、参数或结果摘要不一致、非法消息角色字段组合，以及重复、重排或不属于最近 assistant 未完成有序后缀的 Tool Call；`operation_call_id`、operation、参数摘要、Plan、节点、Worker Run 与 Invocation 在授权暂停执行中保持一致。
28. 独立 `DurableResultLedgerRegistry` 只定义已提交 receipt 的 `load_committed_result()/save_committed_result()` 保存与查询 seam，`OperationRegistry.resolve()` 是 operation 名称、授权要求、ledger 和唯一 handler 绑定的事实来源；当前 Harness 和后续唯一 `OperationExecutor` 都只消费同一 `ResolvedOperation`，调用方不能传入 handler。`ToolDefinition/ToolRegistry` 只保存模型可见名称、角色和参数 Schema，不保存或执行 handler。
29. `strategy.career_plan` 不存在于本期闭合目录；旧 list_type=plan 执行路径和 LegacyCareerPlanAdapter 已删除，后续独立 Spec/Plan 直接把纯规划链加入 pipeline。
30. 临时 `PlanResultPresenter` 只从 ExecutionPlan 终态、PlanNodeResult 和 VerifiedOutcome 生成确定性草稿/产物引用；旧 Worker summary 和角色说明不会成为最终回复，后续全局失败机制以统一 Turn Result Renderer 替换。
31. 用户拒绝把当前节点以原身份收敛为 `cancelled`、阻断下游且不执行 operation；新应用实例不接管旧 continuation，扫描已持久化 rejected 快照时继续收敛为 `cancelled/rejected`，只有其余旧活动快照才幂等收敛为 `interrupted`。两条路径都通过 `finalize_active_execution_plan()` 在一次 CAS 中保存 `last_terminal_execution_plan`、追加唯一 confirmation 终态回执并清除活动快照；快照清除后的重复请求仍幂等返回。授权 TTL、自动过期、Trace exactly-once 投递和完整 Failure 分类留给后续全局失败机制。
32. `SessionExecutionState` 是阶段、Gate、当前 Task 控制状态、Artifact 引用与版本、跨请求 Plan 和回执的唯一事实源；初始工厂固定 revision 0/explore/not_started/空 Artifact/无执行。同步 Plan 不进入 `CurrentExecution`，真正跨请求非授权 Plan 与授权暂停 Plan 使用不同分支；`/v1/tasks` 只投影当前 `SessionTaskState`，历史由终态 Plan/Trace 审计。单个 execution-state.json 以 revision CAS 发布，跨版本 Artifact 倒退由 Store 比较 current/next 拒绝，不读取或迁移旧 Session/Task/Artifact 数据。
33. `ExecutionPlanRequestService` 是唯一 Session 持久化事务模块；普通 Turn 一次聚合 CAS，confirmation 使用命名 CAS 序列。ExecutionPlanResumeHandler 只在 receipt 持久化后运行，Turn/Resume Handler 都不能直接写 Session。
34. 每个 DATA_DIR 只允许一个持有 DataDirectoryWriterLease 的写入进程；聚合 JSON 通过临时文件、flush/fsync、原子 replace 和父目录同步发布。

## Suggested Commit

仅在用户另行要求创建 commit 时使用：

```text
refactor(worker): 引入强类型调用与执行计划

- 使用不可变 WorkerInvocation 固定业务动作、输入和能力快照
- 使用唯一确定性 Success Contract Registry 验收并提取命名 Outcome
- 通过 Node Spec 和 Outcome 绑定延迟物化下游 WorkerInvocation
- 由 Harness 在 Worker LLM 前强制预加载 required Skill 并在失败时停止执行
- 通过 ExecutionPlan 管理依赖结果和串行 Worker 调度
- 统一真实 Runner、mock 与测试 stub 的调用接口
- 删除字符串 Worker 队列和 JSON 运行时双事实来源
```
