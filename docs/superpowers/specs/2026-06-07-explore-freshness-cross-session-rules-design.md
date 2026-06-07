# 职业初探落档与新会话跳过规则设计规格

| 属性 | 内容 |
|------|------|
| 状态 | **已实现** |
| 版本 | **0.1.0** |
| 日期 | 2026-06-07 |
| 需求来源 | 产品讨论：已有初探档案时，新会话应根据时效性决定是否跳过完整初探 |
| 基线文档 | [B02 流程 · 职业初探 PRD](../../prd/B02.%20流程-职业初探%20PRD.md)、[A03 机制 · 技能包 PRD](../../prd/A03.%20机制-技能包%20PRD.md)、[task-system-pipeline-upgrade](./2026-06-01-task-system-pipeline-upgrade-design.md)、[profile/session boundary](./2026-06-02-profile-session-boundary-design.md) |
| 后续计划 | implementation plan 已完成并执行，等待后续维护 |

---

## 0. 摘要

当前系统已经具备“初探完成”与“初探复盘”的业务概念，但跨会话判断仍不完整，导致以下问题：

1. 一个 session 即使已经完成职业初探，`profile.json` 中未形成可跨会话复用的完成态时，新 session 仍会被当作“未完成初探”。
2. 新 session 默认从 `explore` 起步，但没有先判断该用户是否已有**足够新**的初探落档。
3. `explore_complete` 与 `explore_review_complete` 的 session 完成态、profile 完成态、baseline 写入时机没有完全统一，导致“session 内完成了，但长期记忆没有完成”。

本 spec 定义以下目标：

- 将 **`profile.exploration.completed_at`** 作为跨会话的初探完成落档时间；
- 将 **`exploration.intake_baseline`** 作为初探完成时的长期基线；
- 新 session 进入时，若用户已有**足够新**的初探落档，则**不再触发完整初探**；
- 若用户明确要求复盘，则进入**初探复盘短路径**，而不是从零重问完整初探；
- 若用户没有初探落档或初探已过期，则仍进入完整初探。

---

## 1. 问题定义

### 1.1 当前症状

在现有实现中，下面几类状态会互相脱节：

- `session_state.explore_gate_confirmed = true`
- `session_state.explore_closure.completed = true`
- `profile.exploration.completed_at = null`

这会造成：

- 当前 session 看起来已经“完成初探”；
- 但新 session 仍然被当作“尚未初探”；
- 进而继续触发初探信息表、初探引导文案或初探 phase。

### 1.2 文档期望

文档中的产品意图是明确的：

- **首次初探**：完整初探 + 简历深挖；
- **已有初探且用户不更新**：跳过完整初探；
- **已有初探且用户要更新**：走复盘短路径，不从零重问五主题；
- **已有初探但过期或内容变化**：触发重新初探/复盘判断。

---

## 2. 目标

### 2.1 跨会话目标

初探的“完成”必须成为跨会话可见的长期状态，而不是只存在于某一个 session 的短暂状态。

### 2.2 跳过目标

当用户在新 session 进入系统时：

- 若 `profile.exploration.completed_at` 存在且仍然新鲜；
- 且用户当前意图不要求复盘；

则系统应跳过完整初探，不再进入“填写初探信息表”的主路径。

### 2.3 复盘目标

当用户已有初探档案，但明确提出：

- 想调整内心意向；
- 想更新优先级；
- 想补充变化内容；

系统应进入 **初探复盘短路径**，而不是从头开始问完整初探。

---

## 3. 设计原则

1. **长期记忆优先**：跨会话的初探完成态以 `profile` 为准，不以单个 session 为准。
2. **session 只管过程，profile 只管落档**：session state 保存当轮进度，profile 保存最终已确认的长期结果。
3. **新鲜度独立判断**：是否跳过完整初探，必须同时考虑完成时间、基线一致性和用户是否要求复盘。
4. **复盘不等于重做**：用户要更新时，默认进入短路径，不重新重问完整初探。
5. **不让表单压过对话**：已有初探且足够新时，新 session 的默认体验应是进入正常咨询/后续流程，而不是再次强行进入表单态。

---

## 4. 规则定义

### 4.1 初探完成态

跨会话初探完成态由以下字段共同表达：

| 字段 | 含义 |
|------|------|
| `profile.exploration.completed_at` | 初探或复盘完成时间，作为跨会话判断的主时间戳 |
| `profile.exploration.intake_baseline` | 与完成态绑定的初探基线，用于后续判断是否变化 |
| `profile.exploration.summary` | 可被后续流程复用的初探摘要 |

### 4.2 新鲜度规则

在已有初探落档时，系统评估以下条件：

| 条件 | 含义 |
|------|------|
| F1 | `exploration.completed_at` 早于 1 个自然月 |
| F2 | 当前 intake 与 `exploration.intake_baseline` 不一致 |
| F3 | 用户明确要求复盘 |

规则：

- 以上任一成立，均视为**需要重新进入初探相关流程**；
- 其中 F1/F2 更偏向“客观需要刷新”；
- F3 更偏向“用户主动要求更新”。

### 4.3 跳过规则

若同时满足：

- 已有初探落档；
- `exploration.completed_at` 仍然新鲜；
- 用户没有明确要求复盘；

则新 session **不应触发完整初探**。

### 4.4 复盘规则

若满足“已有初探落档”且用户要求更新，则：

- 不重问完整初探五主题；
- 只对变化部分进行追问；
- 必要时补充简历素材；
- 最终刷新 `completed_at` 与 `intake_baseline`。

---

## 5. 状态模型

### 5.1 Session 与 Profile 的职责

| 层级 | 职责 |
|------|------|
| `profile` | 保存长期稳定的初探落档、简历资产、可跨会话复用的核心画像 |
| `session_state` | 保存当前会话是否正在填写、是否已确认、是否处于复盘或阻断态 |
| `artifacts` | 保存本 session 的探索/市场/策略等过程产物 |

### 5.2 状态判定顺序

新 session 进入时，建议按以下顺序判断：

1. 是否有长期初探落档；
2. 如果有，是否仍然新鲜；
3. 如果不新鲜，是否用户主动要求复盘；
4. 如果都不是，则跳过完整初探，进入后续正常对话或后续阶段。

---

## 6. 需要补齐的行为

### 6.1 初探确认时的落档行为

当用户确认完成初探或确认完成复盘时，系统应同时写入：

- `profile.exploration.completed_at`
- `profile.exploration.intake_baseline`
- `profile.exploration.summary`

并保留 session 内的 `explore_gate_confirmed`、`explore_closure.completed` 作为当前会话状态。

### 6.2 新 session 创建时的判定行为

新 session 创建后，系统不应无条件将它固定成 `current_phase=explore`。

应改为：

- 若没有初探落档，或初探已过期，则进入完整初探；
- 若已有新鲜初探且无复盘意图，则跳过完整初探；
- 若已有初探但用户要求更新，则进入复盘短路径。

### 6.3 路由行为

当用户在新 session 发出意图消息时，意图路由应结合以下信息判断是否需要初探：

- `profile.exploration.completed_at`
- `profile.exploration.intake_baseline`
- 当前 session 的 `explore_gate_confirmed`
- 当前消息是否表达复盘/更新意图

---

## 7. 建议的实现边界

> 本 spec 只定义业务边界，不强制实现方式；但为了保证落地，建议以下模块承担责任：

- `pipeline_template.py`：创建 session pipeline 时先做新鲜度判断，不直接写死 `explore`
- `pipeline_gates.py`：提供完整的 `needs_full_explore` / freshness 判断
- `jd_prerequisites.py`：把 profile 级初探完成态纳入前置判断
- `pipeline_phase_transition.py`：在 `explore_complete` / `explore_review_complete` 时统一落档
- `profile.py`：允许写入 `exploration.completed_at`、`exploration.intake_baseline` 等长期初探字段
- `session_activity.py`：展示层依据长期完成态与当前 session 态区分“表单中”与“已完成”

---

## 8. 验收标准

当本需求完成后，应满足以下验收标准：

1. 用户在 A session 完成初探并确认后，`profile.exploration.completed_at` 必须存在。
2. 新 session 打开时，如果该初探仍在一个自然月内且用户未要求复盘，不应再次弹出完整初探表单。
3. 新 session 打开时，如果用户明确要求复盘，应进入复盘短路径，而不是从零开始的完整初探。
4. 如果 `completed_at` 已超过一个自然月，系统应视为需要重新评估初探，不可默认跳过。
5. 如果当前 intake 与 `intake_baseline` 不一致，系统应视为需要重新初探或复盘。
6. `explore_complete` / `explore_review_complete` 的确认结果必须跨 session 可见。

---

## 9. 非目标

本 spec 不处理：

- UI 重设计；
- 六维画像内容重构；
- JD / 市场 / 策略阶段的详细内容升级；
- 多租户与账号系统；
- 外部招聘市场数据接入。

---

## 10. 备注

此 spec 与下列文档保持一致：

- B02 的“已有初探档案的用户”与“初探复盘”定义；
- A03 的“首次 / 复盘”模式划分；
- task-system-pipeline-upgrade 中的 freshness / `fresh_pass` 规则；
- profile/session boundary 中的“长期档案 vs 会话态”分层。
