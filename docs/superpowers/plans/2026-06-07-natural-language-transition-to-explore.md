# 自然语言转换到可 jump 流程实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让用户在对话里明确说“转换到某个可 jump 流程”时，协调者能理解该意图并通过 `jump_to_phase(target_phase)` 真正把任务阶段切到目标流程，从而让 UI、任务阶段和对话语义同轮对齐。

**Architecture:** 协调者负责理解用户是否要切换到某个可 jump 流程，Harness 负责真正写盘与清场，`TaskStore.meta.current_phase` 仍然是任务 UI 的真相源。实现上保留现有的前向阶段转场不变，只补“自然语言转换到可 jump 流程”这一条显式 jump 路径，并确保它优先于普通的 analyze / synthesize 逻辑生效。

**Tech Stack:** Python, FastAPI, pytest, existing Career OS coordinator / harness modules, micro-classifier prompt

**Design SSOT:** `../specs/2026-06-07-natural-language-transition-to-explore-design.md`

**状态:** 已完成

---

## Task 1: 先把“转换到可 jump 流程”锁成回归测试

**Files:**
- `backend/tests/harness/test_pipeline_intent_transition.py`
- `backend/tests/agents/test_coordinator_routing.py`
- `backend/tests/api/test_chat_intent_phase.py`

- [ ] **Step 1: 写出会失败的测试**

新增四类覆盖：

1. 明确转换到 `explore` 时，真的切回 `explore`
2. 明确转换到 `market / jd_analysis / resume_strategy` 时，真的切到对应 phase
3. gate 优先
4. 模糊表达不触发流程切换

- [ ] **Step 2: 运行测试确认当前行为还不符合预期**

运行：
```bash
cd backend && pytest tests/harness/test_pipeline_intent_transition.py tests/agents/test_coordinator_routing.py tests/api/test_chat_intent_phase.py -q
```

期望：新增的“转换到可 jump 流程”用例先失败，证明当前链路还没有把该意图落成真正的 `current_phase=target_phase`。

---

## Task 2: 让协调者理解“转换到可 jump 流程”，并把它写成显式 jump

**Files:**
- `backend/career_os/platform/prompt/micro_classifier/pipeline_phase_intent/system.md`
- `backend/career_os/harness/pipeline_intent_transition.py`

- [ ] **Step 1: 扩展阶段意图 prompt，让模型可以输出可 jump 目标**

把 `pipeline_phase_intent` 的 prompt 改成支持新的显式目标：

```md
| target_phase | 含义 |
|--------------|------|
| `explore` | 明确请求转换到初探流程 |
| `market` | 明确请求转换到市场分析流程 |
| `jd_analysis` | 明确请求转换到 JD 分析流程 |
| `resume_strategy` | 明确请求转换到简历策略流程 |
| `resume_optimize` | 不允许自然语言直跳，仍需 `optimize_confirm` |
| `null` | 不转换流程 |
```

并明确说明：
- 只有在用户明确表达“转换到某个可 jump 流程”时才允许输出对应目标
- `gates_pending` 仍然优先，先吃 gate，不抢流程转换
- 不是所有“继续聊聊 / 下一步”都属于流程转换
- `resume_optimize` 仍然不在自然语言直跳集合中

- [ ] **Step 2: 在意图解析里接受可 jump 目标，不要再被 rank 过滤吞掉**

在 `resolve_intent_phase_transition()` 里保留现有前向流程规则，但增加一个明确的可 jump special case：

```python
if target in {"explore", "market", "jd_analysis", "resume_strategy"} and current != target:
    return {
        "applied": False,
        "from_phase": current,
        "to_phase": target,
        "rule_id": transition.rule_id,
        "suggested_workers": transition.suggested_workers,
        "source": source,
    }
```

核心要求是：
- 不再用“目标 phase 序更靠后”这一条把可 jump 目标挡掉
- 可 jump 目标仍然必须经过协调者理解，而不是规则硬匹配
- 该分支只针对“明确转换到可 jump 流程”的 LLM 判定结果生效

- [ ] **Step 3: 让 `apply_intent_phase_transition()` 对可 jump 目标走 `jump_to_phase`**

把当前只会 `apply_list_phase(list_id, target)` 的写盘逻辑改成：

```python
if target in {"explore", "market", "jd_analysis", "resume_strategy"}:
    jump_to_phase(session_id, list_id, target, session_state)
else:
    apply_list_phase(list_id, target)
```

同时保留：
- `intent_suggested_workers`，让同轮 analyze 能顺着新 phase 派工
- `last_phase_transition` 的记录，方便 trace 和调试

> 这一点很重要：可 jump 目标不能只改 phase，不做清场；必须走 `jump_to_phase`，这样 gate / closure 才会被正确重置。

- [ ] **Step 4: 运行单测确认可 jump 目标写盘与清场生效**

运行：
```bash
cd backend && pytest tests/harness/test_pipeline_intent_transition.py -q
```

期望：
- “转换到可 jump 流程” 会真正写成 `current_phase=target_phase`
- gate / closure 的状态会跟着 jump 清场，而不是只改一个 phase 字段

---

## Task 3: 验证同轮 coordinator / chat 链路真的吃到新的 `explore` phase

**Files:**
- `backend/tests/agents/test_coordinator_routing.py`
- `backend/tests/api/test_chat_intent_phase.py`

- [ ] **Step 1: 增加同轮集成测试**

补一条从协调者入口跑通的测试，确保用户消息“转换到某个可 jump 流程”不会只停留在回复层：

```python
def test_coordinator_turn_switches_to_explore(monkeypatch, jd_ready_profile):
    monkeypatch.setattr(coordinator_llm_mod.lc_client, "llm_enabled", lambda: False)
    harness = Harness()
    session_id = "sess_turn_explore"
    list_id = instantiate_pipeline_for_session(session_id)
    task_mod.TaskStore().set_current_phase(list_id, "market")

    state = {
        "session_id": session_id,
        "list_type": "pipeline",
        "list_id": list_id,
        "explore_gate_confirmed": True,
        "gates": {"flags": {"explore_gate_confirmed": True}},
        "explore_closure": {"completed": True},
        "prior_results": {},
    }

    run_coordinator_turn(
        harness,
        session_id=session_id,
        session_state=state,
        user_message="转换到初探流程，继续聊身份与价值观",
        pending_workers=[],
        worker_runner=lambda worker_id, goal, session_state, context: {
            "worker_id": worker_id,
            "status": "completed",
            "structured_output": {"user_visible_summary": f"{worker_id} done"},
        },
    )

    assert task_mod.TaskStore().get_list_meta(list_id)["current_phase"] == "explore"


def test_coordinator_turn_switches_to_market(monkeypatch, jd_ready_profile):
    monkeypatch.setattr(coordinator_llm_mod.lc_client, "llm_enabled", lambda: False)
    harness = Harness()
    session_id = "sess_turn_market"
    list_id = instantiate_pipeline_for_session(session_id)
    task_mod.TaskStore().set_current_phase(list_id, "explore")

    state = {
        "session_id": session_id,
        "list_type": "pipeline",
        "list_id": list_id,
        "explore_gate_confirmed": True,
        "gates": {"flags": {"explore_gate_confirmed": True}},
        "explore_closure": {"completed": True},
        "prior_results": {},
    }

    run_coordinator_turn(
        harness,
        session_id=session_id,
        session_state=state,
        user_message="转换到市场分析流程，看看外部机会",
        pending_workers=[],
        worker_runner=lambda worker_id, goal, session_state, context: {
            "worker_id": worker_id,
            "status": "completed",
            "structured_output": {"user_visible_summary": f"{worker_id} done"},
        },
    )

    assert task_mod.TaskStore().get_list_meta(list_id)["current_phase"] == "market"
```

- [ ] **Step 2: 运行集成测试确认 coordinator 已经吃到新 phase**

运行：
```bash
cd backend && pytest tests/agents/test_coordinator_routing.py tests/api/test_chat_intent_phase.py -q
```

期望：
- 协调者在 analyze 前已经把流程切到目标 phase
- 同轮派工和 synthesize 不再沿用旧 phase

---

## Task 4: 全量验收、回写 spec 状态与收口

**Files:**
- `docs/superpowers/specs/2026-06-07-natural-language-transition-to-explore-design.md`
- `docs/superpowers/plans/2026-06-07-natural-language-transition-to-explore.md`

- [ ] **Step 1: 跑相关后端测试**

运行：
```bash
cd backend && pytest tests/harness/test_pipeline_intent_transition.py tests/agents/test_coordinator_routing.py tests/api/test_chat_intent_phase.py -q
```

期望：
- 新增“转换到可 jump 流程”用例全部通过
- 既有前向意图转场测试保持绿色

- [ ] **Step 2: 跑后端全量回归**

运行：
```bash
cd backend && pytest -q
```

期望：
- 相关流程切换、闸门、初探、市场分析、JD 分析、简历策略、简历优化相关测试全部保持绿色

- [ ] **Step 3: 回写 spec 状态并收口**

把 spec 状态更新为 `已实现` 或 `部分已实现`，并在备注里写清楚：
- “自然语言转换到可 jump 流程” 已接入协调者理解链路
- `jump_to_phase(target_phase)` 已成为显式写盘结果
- 仍保留 profile 长期记忆，不清除历史档案

- [ ] **Step 4: 如需要，提交变更**

```bash
git add \
  backend/career_os/platform/prompt/micro_classifier/pipeline_phase_intent/system.md \
  backend/career_os/harness/pipeline_intent_transition.py \
  backend/tests/harness/test_pipeline_intent_transition.py \
  backend/tests/agents/test_coordinator_routing.py \
  backend/tests/api/test_chat_intent_phase.py \
  docs/superpowers/specs/2026-06-07-natural-language-transition-to-explore-design.md \
  docs/superpowers/plans/2026-06-07-natural-language-transition-to-explore.md

git commit -m "feat(pipeline): 支持自然语言转换到可 jump 流程"
```

---

## 并行建议

- Task 1 先做，锁住行为基线。
- Task 2 是核心实现，建议在测试失败后立即修。
- Task 3 用来确认同轮 coordinator / chat 真正吃到新的 `explore` phase。
- Task 4 只在所有相关测试通过后执行。

## 完成定义

- 用户明确说“转换到某个可 jump 流程”时，系统会把 `current_phase` 真正切成目标 phase。
- 这次切换通过协调者理解完成，不靠规则硬匹配。
- `jump_to_phase(target_phase)` 会正确清场并保留长期记忆。
- 相关测试全部通过，spec 状态同步收口。
