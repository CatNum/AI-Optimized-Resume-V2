# 老模式任务清除 — 实现计划

| 属性 | 内容 |
|------|------|
| 状态 | **已实施** |
| 日期 | 2026-06-01 |
| 设计 SSOT | [../specs/2026-06-01-legacy-task-mode-removal-design.md](../specs/2026-06-01-legacy-task-mode-removal-design.md) |
| 说明 | **不修改** 已归档的 pipeline / session 等 plan·spec；任务仅在本计划与设计 spec 维护 |

---

## Task R0: Store 与工具层拒绝老 list_type

**Files:**
- Modify: `backend/career_os/platform/store/task.py`
- Modify: `backend/career_os/platform/tool/handlers/task.py`
- Create: `backend/tests/store/test_task_list_type_deprecated.py`（或并入 `test_task_pipeline.py`）

**Spec refs:** 设计 spec §2.4 T1–T2、§五 5.5

- [x] **Step 1:** `create_task_list(list_type="explore")` → `TaskStoreError(code=list_type_deprecated)`
- [x] **Step 2:** 同上 `list_type="jd"`
- [x] **Step 3:** `list_type="pipeline"` / `plan` 仍成功
- [x] **Step 4:** Harness `create_task_list` 工具透传错误码
- [x] **Step 5:** `pytest` 上述用例

---

## Task R1: 协调者路由仅 pipeline + phase

**Files:**
- Modify: `backend/career_os/agents/lc/coordinator_llm.py`
- Modify: `backend/career_os/agents/graphs/coordinator.py`
- Modify: `backend/tests/agents/test_coordinator_routing.py`
- Modify: `backend/tests/agents/test_coordinator_explore_phase.py`（改为 pipeline fixture）

**Spec refs:** 设计 spec §2.2 A1–A6、§五 5.1–5.2

- [x] **Step 1:** `normalize_analyze_result` 删除 `explore`/`jd` 分支；输出 `pipeline` + `pipeline_phase`
- [x] **Step 2:** `fallback_analyze_workers` 初探/市场/JD 均返回 `list_type: pipeline`
- [x] **Step 3:** `analyze_workers` 丢弃 LLM 返回的 `explore`/`jd`
- [x] **Step 4:** `_apply_analysis` 禁止把 `session_state.list_type` 写成 explore/jd
- [x] **Step 5:** 测试：pipeline session + fallback「初探」→ `pipeline_phase=explore`，`list_type` 仍为 pipeline

---

## Task R2: Harness 单路径 + chat 副作用

**Files:**
- Modify: `backend/career_os/harness/explore_closure.py`
- Modify: `backend/career_os/harness/explore_intake.py`
- Modify: `backend/career_os/harness/session_activity.py`
- Modify: `backend/career_os/harness/explore_depth.py`
- Modify: `backend/career_os/harness/delegate.py`
- Modify: `backend/career_os/api/chat.py`
- Modify: `backend/tests/harness/test_explore_intake.py`
- Modify: `backend/tests/e2e/test_explore_closure_e2e.py`

**Spec refs:** 设计 spec §2.3 G1–G2、§五 5.4

- [x] **Step 1:** 删除 `list_type=="explore"` 并列分支；统一 `get_current_phase` / `is_pipeline_explore_phase`
- [x] **Step 2:** `explore_repeat` confirm **删除** `session_state["list_type"] = "explore"`
- [x] **Step 3:** `explore_repeat` reject + intake 已提交 → `set_explore_gate_confirmed(true)`（产品已确认）
- [x] **Step 4:** 相关 harness 测试改为 pipeline session

---

## Task R3: Prompt、架构注记与全量回归

**Files:**
- Modify: `backend/career_os/platform/prompt/coordinator/system.md`
- Modify: `backend/career_os/platform/prompt/identity/system.md`、`capability/system.md`、`market/system.md`、`opportunity/system.md`（按需）
- Modify: `docs/architecture/02-平台服务.md`（仅 deprecated 注记，若允许改架构；否则改本 spec §十 附录）
- Modify: `backend/tests/store/test_task.py`（explore 建表用例改为 deprecated 断言）

**Spec refs:** 设计 spec §五 5.6、§七

- [x] **Step 1:** coordinator prompt 示例 JSON 仅 `pipeline`
- [x] **Step 2:** Worker prompt `list_type=explore|jd` → `current_phase` 表述
- [x] **Step 3:** `cd backend && uv run pytest -q`
- [x] **Step 4:** 对照设计 spec §七 验收表逐条勾选

---

## 验收清单（设计 spec §七）

| # | 场景 | 验证 |
|---|------|------|
| 1 | 新 session | 仅 pipeline list；`current_phase=explore` |
| 2 | 「帮我初探」 | 无 `list_type=explore`；`pipeline_phase=explore` |
| 3 | 「看市场/JD」且 gate 已过 | `pipeline_phase` 正确；无 `list_type=jd` |
| 4 | `explore_repeat` confirm | `state.list_type` 仍为 pipeline |
| 5 | `create_task_list(explore)` | `list_type_deprecated` |
| 6 | 全量 pytest | 通过（214 passed, 5 skipped） |

---

*计划版本：2026-06-01 · 仅维护本文件与 legacy-task-mode-removal-design.md*
