# Pipeline 全阶段意图流转 — 实现计划

> **For agentic workers:** 按 Task 执行；checkbox 跟踪进度。

**Goal:** 用户消息在 analyze 前可 **显式推进** `current_phase`（B 松门槛）；派工与 synthesize draft 与 **目标阶段** 一致，避免 `jd_analysis` 下问策略却 `workers=[]` 复读 opportunity。

**Architecture:** `resolve_intent_phase_transition` 表驱动 → `chat.py` 写 phase → 现有 `filter_workers_for_pipeline` + 扩展 fallback + 阶段 draft。

**设计 SSOT:** [../specs/2026-06-02-pipeline-intent-phase-transitions-design.md](../specs/2026-06-02-pipeline-intent-phase-transitions-design.md) **v0.1.0**

**状态:** **已实现**

---

## Task IT0: 核心模块与硬规则

**Files:**
- Create: `harness/pipeline_intent_transition.py`
- Modify: `harness/micro_classifier_rules.py`
- Create: `platform/prompt/micro_classifier/pipeline_phase_intent/system.md`
- Modify: `harness/micro_classifier.py`

- [x] `has_jd_context(session_state, user_message)`（B）
- [x] `PIPELINE_INTENT_TRANSITIONS` + `resolve_intent_phase_transition`
- [x] `match_pipeline_intent_rules` + 可选 `pipeline_phase_intent`
- [x] 单测：§4.4 每行 rule 命中

---

## Task IT1: chat 入口与 phase 写盘

**Files:**
- Modify: `api/chat.py`
- Modify: `harness/pipeline_phase_transition.py`（`strategy` → `resume_strategy` on complete）

- [x] analyze 前调用 resolve；写 `TaskStore.set_current_phase`
- [x] 闸门优先顺序单测
- [x] worker_complete 补充 strategy 行

---

## Task IT2: 派工 fallback

**Files:**
- Modify: `harness/pipeline_routing.py`
- Modify: `agents/lc/coordinator_llm.py`（`pipeline_fallback_workers`）

- [x] `intent_suggested_workers` fallback 派工
- [x] analyze payload 可选 `intent_suggested_workers`

---

## Task IT3: Synthesize 阶段 draft

**Files:**
- Modify: `agents/lc/coordinator_llm.py`
- Modify: `agents/graphs/coordinator.py`
- Modify: `platform/prompt/coordinator/system.md`

- [x] `market` / `jd_analysis` / `resume_strategy` continue draft
- [x] 深阶段禁用 `chat_only_draft` + `resume_strategy` 禁止复读 not_recommended 闸门（除非 pending）

---

## Task IT4: 集成与 Demo 验收

**Files:**
- Create: `tests/harness/test_pipeline_intent_transition.py`
- Create: `tests/api/test_chat_intent_phase.py`

- [x] harness/api 用例：jd_analysis → 问策略 → resume_strategy
- [x] 全量 pytest 绿
- [x] 更新 [pipeline-phase-explore-state spec](../specs/2026-06-02-pipeline-phase-explore-state-design.md) 关联链接（一行）

---

## 依赖顺序

`IT0 → IT1 → IT2 ∥ IT3 → IT4`
