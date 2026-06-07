# 职业初探跨会话新鲜度规则实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:**  
让“职业初探是否需要重做”真正以 `profile.exploration.completed_at` 和 `profile.exploration.intake_baseline` 为跨会话依据；当用户已有足够新的初探落档时，新 session 不再强制回到完整初探表单，用户明确要求复盘时则走短路径。

**Architecture:**  
长期初探结果写入 `profile`，当前会话过程态留在 `session_state`，会话创建、JD 前置、协调者路由和初探完成落档都通过同一套 freshness 判定函数协同工作。完整初探、过期刷新、复盘短路径三种行为必须共享同一组规则，避免 session-first 逻辑覆盖 profile-first 逻辑。

**Tech Stack:**  
Python, FastAPI, pytest, existing Career OS harness/store modules

**Design SSOT:**  
`../specs/2026-06-07-explore-freshness-cross-session-rules-design.md`

**状态:**  
待执行

---

## Task 1: 先把新鲜度规则锁成回归测试

**Files:**
- `backend/tests/harness/test_pipeline_gates.py`
- `backend/tests/harness/test_jd_prerequisites.py`
- `backend/tests/harness/test_session_activity.py`
- `backend/tests/agents/test_coordinator_explore_intake.py`
- `backend/tests/api/test_chat_intent_phase.py`

- [ ] **Step 1: 写出会失败的回归测试**

增加四类覆盖：
1. `profile.exploration.completed_at` 在 1 个自然月内且没有复盘意图时，新 session 不应再次判定为 `needs_full_explore`。
2. `completed_at` 已超过 1 个自然月时，应判定为 `needs_full_explore=True`。
3. `profile.exploration.intake_baseline` 与当前 intake 不一致时，应判定为 `needs_full_explore=True`。
4. 用户明确表达“更新/复盘/重新梳理职业方向”时，应进入复盘短路径，而不是完整初探。

建议的断言目标：
- `compute_needs_full_explore(profile, session_state)` 返回期望值。
- `check_jd_prerequisites(session_state)` 返回 `("explore" | None)` 的期望前置结论。
- `build_session_activity(session_state)` 不应把“已完成且新鲜的 profile”误展示成“仍在填表”。

- [ ] **Step 2: 运行测试确认当前行为不符合预期**

运行：
```bash
cd backend && pytest tests/harness/test_pipeline_gates.py tests/harness/test_jd_prerequisites.py tests/harness/test_session_activity.py -q
```

期望：至少有一部分用例先失败，暴露当前 session-first / explore-first 的偏差。

---

## Task 2: 把初探完成真正落到 profile 长期档案

**Files:**
- `backend/career_os/harness/pipeline_phase_transition.py`
- `backend/career_os/api/chat.py`
- `backend/career_os/platform/store/profile.py`
- `backend/career_os/harness/explore_intake.py`

- [ ] **Step 1: 补齐落档路径**

让 `explore_complete` 和 `explore_review_complete` 在确认完成时同时写入：
- `profile.exploration.completed_at`
- `profile.exploration.intake_baseline`
- `profile.exploration.summary`

保留当前 session 的：
- `explore_gate_confirmed`
- `explore_closure.completed`

这样同一次完成既能留住 session 过程态，也能留下跨 session 可复用的长期态。

- [ ] **Step 2: 运行单测确认 profile 写入路径生效**

运行：
```bash
cd backend && pytest tests/harness/test_pipeline_phase_transition.py tests/agents/test_coordinator_explore_intake.py -q
```

期望：
- 确认完成初探后，`profile.json` 中能看到 `exploration.completed_at` 和 `intake_baseline`。
- 只改 session state 不再被视为跨会话“已完成”。

---

## Task 3: 让会话创建与 JD 前置真正读 profile freshness

**Files:**
- `backend/career_os/platform/pipeline_template.py`
- `backend/career_os/harness/pipeline_gates.py`
- `backend/career_os/harness/jd_prerequisites.py`
- `backend/career_os/harness/pipeline_phase_advance.py`
- `backend/career_os/harness/pipeline_intent_transition.py`

- [ ] **Step 1: 把新会话的起点选择改成条件化**

把 `instantiate_pipeline_for_session()` 里无条件写死的 `current_phase="explore"` 改成基于 freshness 的决策：
- 没有初探落档，或初探过期，或 intake 变化，或用户要求复盘时，进入完整初探/复盘判断；
- 已有足够新的初探落档且无复盘意图时，不再把新 session 强行压进完整初探。

这一步要复用 `compute_needs_full_explore()`，避免在多个文件里重复判定规则。

- [ ] **Step 2: 让 JD 前置从 profile 侧吃到同一套规则**

`check_jd_prerequisites()` 继续同时看 session 与 profile，但必须把 profile 的 `exploration.completed_at` / `intake_baseline` 作为主判断依据之一，而不是只依赖 `session_state.explore_completed_at` 之类的短态字段。

这一步的目标是让：
- 已完成且新鲜的旧 session 进入新会话后，不会因为 session 状态为空而被误判回初探；
- 已过期或基线变化的档案，仍会被拦回初探或复盘。

- [ ] **Step 3: 运行路由测试确认新会话不会误起步**

运行：
```bash
cd backend && pytest tests/harness/test_jd_prerequisites.py tests/harness/test_pipeline_gates.py tests/harness/test_pipeline_phase_transition.py -q
```

期望：
- 新会话在 profile fresh 的情况下不会被判成必须完整初探。
- stale / changed baseline / explicit review 仍会被拦回相应路径。

---

## Task 4: 收紧表单触发与协调者草稿，避免 fresh profile 仍回到填表态

**Files:**
- `backend/career_os/harness/session_activity.py`
- `backend/career_os/agents/graphs/coordinator.py`
- `backend/career_os/api/chat.py`
- `backend/career_os/harness/explore_intake.py`

- [ ] **Step 1: 调整表单可见性条件**

让“填写初探信息表”的展示条件只在真正需要补初探时触发：
- `compute_needs_full_explore(...)` 为真；
- 或当前 session 仍处于未完成的初探流程。

对于“profile 已经有足够新初探落档”的新 session，不应再因为 `explore_intake_blocked` 的历史默认态而显示表单入口。

- [ ] **Step 2: 让协调者在 fresh profile 场景优先读长期记忆**

协调者合成回复时，先从 profile 提供的长期信息生成上下文，再决定是否需要进入初探/复盘文案。  
不要让 `explore_intake_blocked` 这种 session 暂态覆盖“已经有可复用简历和初探档案”的事实。

- [ ] **Step 3: 运行端到端回归**

运行：
```bash
cd backend && pytest tests/agents/test_coordinator_explore_intake.py tests/api/test_chat_intent_phase.py tests/harness/test_session_activity.py -q
```

期望：
- fresh profile 的新 session 默认不再回到完整表单。
- 需要复盘时，仍然会进入短路径，并保留追问变化的能力。

---

## Task 5: 验收、回写 spec 状态与收口

**Files:**
- `docs/superpowers/specs/2026-06-07-explore-freshness-cross-session-rules-design.md`
- `docs/superpowers/plans/2026-06-07-explore-freshness-cross-session-rules.md`

- [ ] **Step 1: 跑完整后端测试**

运行：
```bash
cd backend && pytest -q
```

期望：
- 新增回归测试全部通过。
- 既有相关测试不回退。

- [ ] **Step 2: 回写 spec 状态**

把 spec 状态从 `待评审` 更新为 `已实现` 或 `部分已实现`，并在备注里写清楚：
- 初探完成态已落到 `profile`
- 新会话 freshness 路由已接入
- 复盘短路径是否已经完全落地

---

## 并行建议

- Task 1 可以先单独做，锁住行为基线。
- Task 2 和 Task 3 是主干链路，建议先后执行。
- Task 4 在 Task 2 / Task 3 基本稳定后做，避免协调者草稿和路由一起改时难以定位问题。
- Task 5 只在全量验证通过后执行。

## 完成定义

- 新 session 能读取 `profile.exploration.completed_at`，并据此决定是否跳过完整初探。
- `intake_baseline` 的变化能正确触发重新初探或复盘判断。
- 用户明确要求复盘时，系统走短路径，不重问完整初探。
- 相关测试全部通过，且 spec 状态同步更新。
