# Career OS Agent Runtime

Career OS Agent Runtime 描述一次用户对话如何形成受约束的 Agent 执行，以及执行结果如何沉淀为可验证的职业规划成果。

## 调用与计划

**Worker Definition**:
某类 Worker 在一种明确业务动作下的能力定义，规定它需要什么输入、可以使用什么能力以及必须产出什么结果。
_Avoid_: Worker 配置、Agent 配置

**Run Kind**:
Worker Definition 中区分具体业务动作的稳定名称，例如生成优化简历或登记简历产物。
_Avoid_: mode、场景、分支

**Invocation Proposal**:
模型根据用户意图提出的 Worker 与 Run Kind 候选，不包含执行权限或依赖关系。
_Avoid_: Worker 选择结果、路由结果

**Worker Invocation**:
Harness 校验并补全后的不可变 Worker 调用，包含明确动作、已验证输入、允许能力和成功契约。
_Avoid_: Worker ID、派工参数

**Execution Plan**:
一个 Turn 内的 Worker Invocation 集合及其依赖关系；只有依赖与必需结果满足的 Invocation 才能执行。
_Avoid_: Worker 队列、pending workers

**Active Execution Plan Snapshot**:
因 operation 授权而暂停时序列化进 Session 的完整 Execution Plan 快照，保存原 Plan、节点、Worker Run、Invocation、操作参数摘要和确认身份，仅允许同一运行实例的下一次请求恢复。
_Avoid_: 历史计划、待办队列

**Required Outcome**:
下游 Invocation 从上游成功结果中必须取得的、经过验证的命名成果。
_Avoid_: prior result、上游摘要

## 运行

**Turn Run**:
处理一条用户消息并形成一次用户可见结果的执行生命周期。
_Avoid_: 请求、聊天调用

**Worker Run**:
执行一个 Worker Invocation 并判断其业务目标是否完成的生命周期。
_Avoid_: Agent 调用、Worker 返回

**Job Run**:
脱离当前 Turn、在后台持续执行并独立产出正式 Artifact 的长任务生命周期。
_Avoid_: 后台 Worker、异步 Turn

**Operation**:
Worker Run 或 Job Run 中一次可独立观察、判断结果并应用失败策略的动作。
_Avoid_: step、函数调用

## 结果与交互

**Success Contract**:
判断某种 Run Kind 是否真正完成业务目标的稳定规则，包括运行完整性、必需结果和可选语义判断。
_Avoid_: 输出 Schema、completed

**Business Outcome**:
operation 按契约完成后形成的正常非成功推进结果，例如暂无结果或等待授权；它不进入失败策略。
_Avoid_: 特殊错误、可忽略失败

**Profile Patch**:
Worker 对职业画像提出的闭合、强类型更新；由 patch kind 唯一确定补丁值的业务模型，再由 Harness 转换到持久化操作。
_Avoid_: 任意 JSON、通用 op/value

**Output ID**:
产物登记时生成且不随路径变化的稳定身份，用于复用、授权和删除。
_Avoid_: 文件路径、文件名、delivery id

**Output Index Version**:
产物索引快照的单调递增版本；登记和删除以预期版本做 compare-and-set，成功修改后严格递增一次。
_Avoid_: 文件时间、缓存版本

**Output Delete Authorization**:
绑定 Session、Output ID、删除操作和 Output Index Version 的一次性授权；存储层消费授权后才解析内部路径并删除。
_Avoid_: 路径确认、通用删除权限

**Confirmation ID**:
某一次待确认事实的稳定编号；请求必须携带该编号才能确认市场方案或恢复暂停操作，不能只使用自然语言“确认”。它标识用户确认请求，不替代下发给 Tool 的授权编号。
_Avoid_: boolean confirmed、聊天文本

**Failure**:
operation 未按契约完成后形成的结构化事实，供 Harness 选择重试、降级、等待或终止策略。
_Avoid_: 异常字符串、错误消息

**Operation Authorization Gate**:
为当前已冻结 operation 请求用户授权的 Gate；第一次请求把 Active Execution Plan Snapshot 写入 Session，第二次请求以一次性 Confirmation ID 恢复同一个 Plan、节点、Worker Run 和 Invocation。
_Avoid_: 流程确认、补充信息

**Workflow Transition Gate**:
询问用户是否进入下一业务阶段的 Gate；当前 Turn 结束，确认后创建新的 Turn Run 与 Execution Plan。
_Avoid_: operation 授权

**Additional Input Gate**:
要求用户提供会改变后续执行输入的信息的 Gate；当前 Worker Run 结束，用户补充后创建新的 Worker Run。
_Avoid_: 简单确认、operation 授权
