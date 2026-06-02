# 档案长期记忆（profile_memory）— 实现计划

> **For agentic workers:** 按 Task 执行；checkbox 跟踪进度。

**Goal:** 用户消息触发档案切片解析；analyze / synthesis **draft** / Worker 注入 `profile_memory`；JD/策略/优化相关 LLM **必填简历全文**；synthesize **不**承担档案发现职责。

**Architecture:** `resolve_profile_memory_sections` → `materialize_profile_memory`；硬规则 + `micro_classifier.profile_memory_scope`；`build_profile_aware_chat_draft` 前置事实。

**设计 SSOT:** [../specs/2026-06-02-profile-long-term-memory-design.md](../specs/2026-06-02-profile-long-term-memory-design.md) **v0.1.0**

**状态:** **已实现**（2026-06-02）

---

## Task PM0: 核心模块与微分类

**Files:**
- `harness/profile_memory.py`
- `harness/micro_classifier_rules.py`（`match_profile_memory_rules`）
- `harness/micro_classifier.py`（`profile_memory_scope`）
- `platform/prompt/micro_classifier/profile_memory_scope/system.md`

- [x] `SECTION_PATHS` / `WORKERS_REQUIRE_RESUME` / `PHASES_REQUIRE_RESUME`
- [x] `resolve` / `materialize` / `format_profile_memory_for_draft`
- [x] 微分类 Prompt + 规则优先

---

## Task PM1: 协调者接入

**Files:**
- `agents/lc/coordinator_llm.py` — analyze `profile_memory`
- `agents/graphs/coordinator.py` — `build_profile_aware_chat_draft`；`attach_profile_memory_to_context`

- [x] analyze payload
- [x] synthesize draft 路径（非 `build_synthesis_messages` 塞档案）
- [x] Worker delegate context

---

## Task PM2: 测试

**Files:**
- `tests/harness/test_profile_memory.py`

- [x] 规则、「有没有简历」draft、Worker 全文 resume
- [x] 全量 pytest 通过

---

## 未做（见 spec §九）

- [ ] `explore_continue_synthesis_draft` 档案感知
- [ ] `state.json` 持久化 `profile_memory_sections` trace
- [ ] 架构 `10` §1.1 增量回写
