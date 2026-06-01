# 老模式任务清除 — 设计规格

## 重点

- **目标**：清除 `list_type=explore` / `list_type=jd` 作为**独立任务列表**及 **session 路由标签** 的运行时语义；**唯一主路径**为 `list_type=pipeline` + `current_phase`。
- **已做**：`POST /v1/sessions/new`、`explore-intake` 补建仅走 `instantiate_pipeline_for_session`；磁盘无新 `explore` list。
- **待做**：见 [实现计划](../plans/2026-06-01-legacy-task-mode-removal.md) Task R0–R3。
- **文档策略**：pipeline / session 等 **已归档 plan·spec 不修改**；本文件 + 上列 plan 为清除工作的唯一 SSOT。

| 属性 | 内容 |
|------|------|
| 状态 | **已确认**（产品 2026-06-01） |
| 版本 | **0.1.1** |
| 日期 | 2026-06-01 |
| 适用范围 | `backend/career_os/**`、`web` 任务展示、coordinator/worker prompts |
| 非目标 | 本期不删 `list_type=plan` 的 Store 能力（仅禁止新会话主路径使用）；不回写已归档 superpowers 文档 |

---

## 一、术语与清除范围

### 1.1 什么叫「老模式」

| 模式 | 历史语义 | 清除后 |
|------|----------|--------|
| **`list_type=explore` 任务列表** | intake 或协调者 `create_task_list(explore)` | **禁止新建**；初探 = `current_phase=explore` |
| **`list_type=jd` 任务列表** | 每个 JD 一条 list | **禁止新建**；JD 链 = pipeline 各 `current_phase` |
| **session / analyze 标签 `explore` \| `jd`** | `session_state.list_type` 与 analyze 返回值 | **禁止写入**；恒 `pipeline` + `pipeline_phase` |
| **`ensure_explore_task_list`** | intake 后建 explore list | **已删除**（代码已无） |

### 1.2 保留什么

| 保留项 | 说明 |
|--------|------|
| **`list_type=pipeline`** | 每 session 一条 active list；五步 milestone |
| **`current_phase` / `pipeline_phase`** | 阶段 SSOT |
| **`list_type=plan`（Store）** | 二期旁路；新会话主路径不得创建 |
| **磁盘遗留 list** | 只读列出；**不得**作为派工依据 |

### 1.3 归档文档（只读引用）

以下文档 **已归档，实施期不修改**；行为冲突时 **以本 spec 为准**：

- `docs/superpowers/specs/2026-06-01-task-system-pipeline-upgrade-design.md`
- `docs/superpowers/plans/2026-06-01-task-system-pipeline-upgrade.md`
- `docs/superpowers/specs/2026-06-01-session-task-isolation-design.md` 等

架构 / PRD 若需 deprecated 注记，可在本 spec **§十 附录** 记录拟议文案，由单独 PR 处理，**非本任务阻塞项**。

---

## 二、目标态规则（SSOT）

### 2.1 Session 与任务实例化

| 规则 ID | 约定 |
|---------|------|
| L1 | 新 session **必须** 有且仅有 **一条** `list_type=pipeline` active list |
| L2 | **禁止** `create_task_list(list_type=explore\|jd)` |
| L3 | `state.json.list_type` **恒为** `"pipeline"`；analyze/chat **不得** 改为 explore/jd |
| L4 | `explore-intake` 仅补 pipeline list |

### 2.2 协调者 analyze 契约

| 规则 ID | 约定 |
|---------|------|
| A1 | 输出 `list_type` **仅** `"pipeline"` 或省略（视为 pipeline） |
| A2 | 必须带 **`pipeline_phase`** ∈ `PIPELINE_PHASES` |
| A3 | Worker 由 `filter_workers_for_pipeline(phase)` 决定 |
| A4 | 初探意图 → `pipeline_phase=explore` |
| A5 | 市场/JD 意图 → `market` / `jd_analysis` 等 phase，**非** `list_type=jd` |
| A6 | LLM 返回 explore/jd → **强制改写** 为 pipeline + phase（须单测） |

### 2.3 闸门与副作用（产品已确认）

| 规则 ID | 约定 |
|---------|------|
| G1 | `explore_repeat` confirm **不得** 设 `list_type=explore` |
| G2 | `explore_repeat` reject + `explore_intake_submitted()` → `explore_gate_confirmed=true` |
| G3 | 与「闸门 LLM 回退」实现可同 PR 联调；**不依赖** 修改已归档闸门 spec 文件 |

### 2.4 Store / 前端

| 规则 ID | 约定 |
|---------|------|
| T1 | `create_task_list(explore\|jd)` → `list_type_deprecated` |
| F1 | `TaskProgress` 仅 pipeline（已实现） |

---

## 三、代码现状审计（2026-06-01）

### 3.1 已清除或已达标

| 项 | 状态 |
|----|------|
| `ensure_explore_task_list` | 已移除 |
| `POST /v1/sessions/new` | 仅 pipeline |
| `submit_explore_intake` | 仅补 pipeline |
| `web/TaskProgress.tsx` | 仅 pipeline |

### 3.2 仍含老模式语义（Task R0–R3）

| 区域 | 文件 |
|------|------|
| Fallback / 归一化 | `agents/lc/coordinator_llm.py` |
| Session 污染 | `agents/graphs/coordinator.py` |
| Chat | `api/chat.py`（`explore_repeat` → `list_type=explore`） |
| Harness 双路径 | `explore_closure.py`, `explore_intake.py`, `session_activity.py`, `explore_depth.py`, `delegate.py` |
| Store / Tool | `store/task.py`, `tool/handlers/task.py` |
| Prompt | `platform/prompt/coordinator/system.md` 等 |
| 测试 | `test_coordinator_explore_phase.py`, `test_explore_closure_e2e.py`, `test_task.py` 等 |

---

## 四、阶段映射（老 → 新）

| 老语义 | 新语义 |
|--------|--------|
| `list_type=explore` + identity/capability | `pipeline`, `current_phase=explore` |
| `list_type=jd` + market | `pipeline`, `current_phase=market` |
| `list_type=jd` + opportunity | `pipeline`, `current_phase=jd_analysis` |
| `list_type=jd` + strategy | `pipeline`, `current_phase=resume_strategy` |
| resume+asset | `pipeline`, `current_phase=resume_optimize` + `optimize_confirmed` |

---

## 五、实现任务索引

详细步骤与 checkbox 见 **[实现计划](../plans/2026-06-01-legacy-task-mode-removal.md)**：

| Task | 摘要 |
|------|------|
| **R0** | Store/工具拒绝 `explore`/`jd` 建表 |
| **R1** | `coordinator_llm` + `coordinator` 仅 pipeline+phase |
| **R2** | Harness 单路径 + `chat` 副作用 + `explore_gate_confirmed` on repeat reject |
| **R3** | Prompt + 测试全绿 + §七验收 |

---

## 六、遗留数据策略

| 场景 | 行为 |
|------|------|
| 磁盘 legacy list | 不删；`GET /v1/tasks` 可列出 |
| 派工 | 仅 `state.list_id` 指向的 pipeline |
| 迁移 | 本期不做自动迁移 |

---

## 七、验收标准

| # | 场景 | 通过条件 |
|---|------|----------|
| 1 | 新 session | 仅 pipeline；`current_phase=explore` |
| 2 | 「帮我初探」 | 无 `list_type=explore`；`pipeline_phase=explore` |
| 3 | 「看市场/JD」且 gate 已过 | 正确 phase；无 `list_type=jd` |
| 4 | `explore_repeat` confirm | `state.list_type` 仍为 pipeline |
| 5 | `create_task_list(explore)` | `list_type_deprecated` |
| 6 | 全量 pytest | 通过 |

---

## 八、实现分期

与计划 Task 一一对应：**R0 → R1 → R2 → R3**。R2 宜与闸门 LLM / `explore_repeat` 联调同 PR 或紧邻合并。

---

## 九、产品决策（本 spec 内闭环）

| ID | 决策 |
|----|------|
| P1 | 清除 explore/jd 老模式；仅 pipeline + `current_phase` |
| P2 | `explore_repeat` reject → `explore_gate_confirmed`（intake 已提交） |
| P3 | 不修改已归档 superpowers 文档；任务只维护本 spec + `plans/2026-06-01-legacy-task-mode-removal.md` |

---

## 十、附录：架构 deprecated 文案（拟议，非阻塞）

实施 R3 时可选写入 `docs/architecture/02-平台服务.md`：

> **Preset: `explore` / `jd`**：已废弃。新会话使用 **Preset: `pipeline`**（见同文档 pipeline 小节）。遗留 list 只读。

---

*Spec 版本：0.1.1 · 2026-06-01 · 任务见 plans/2026-06-01-legacy-task-mode-removal.md*
