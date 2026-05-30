# 会话工作区、闸门与 state.json

| 属性 | 内容 |
|------|------|
| 文档版本 | v0.1 |
| 父文档 | [02-平台服务.md](./02-平台服务.md) |
| 最后更新 | 2026-05-30 |

## 1. 会话工作区生命周期

### 1.1 存储分层

| 层级 | 路径 | 生命周期 |
|------|------|----------|
| 对话历史 | `data/sessions/{session_id}/messages.json` | 当前 session；换会话清空 |
| 派工/闸门 | `data/sessions/{session_id}/state.json` | 同上 |
| 任务 | `data/tasks/{list_id}/`（`meta.session_id`） | 绑定 session；换会话 **删除全部**（含 `ready`） |
| 长期事实 | `data/profile.json` | 跨 session |
| 产物 | `output/` | 跨 session |

### 1.2 换会话（R2：刷新清空）

触发：`POST /v1/sessions/new`、首次 chat 不带 `session_id`、前端刷新不复用旧 ID。

| 动作 | 对象 |
|------|------|
| 删除/废弃 | `messages.json`、`state.json` |
| 删除 | 该 `session_id` 下 **全部** task list（`ready` + `active`） |
| 清空 | `data/tasks/_active.json` |
| **保留** | `profile.json`、`output/` |

```mermaid
stateDiagram-v2
  [*] --> Active: 新 session_id
  Active --> Active: chat append messages
  Active --> Cleared: sessions/new 或刷新
  Cleared --> Active: 新 session
```

### 1.3 `messages.json` 格式（示意）

```json
{
  "messages": [
    { "role": "user", "content": "..." },
    { "role": "assistant", "content": "..." }
  ]
}
```

`begin_chat`：读入拼进协调者 `CoordinatorState.messages`；本轮结束后 append 并写回。

## 2. gates 闸门（G1）

闸门 **临时态** 存 `state.json`；换 session 清空。需长期保留的确认结果写 `profile.json`。

### 2.1 `state.json` 结构（示意）

```json
{
  "session_id": "sess_...",
  "list_id": "list_...",
  "prior_results": {},
  "gates": {
    "pending": {
      "name": "optimize_confirm",
      "prompt": "是否确认按该 JD 优化简历？",
      "asked_at": "2026-05-30T12:00:00Z"
    },
    "flags": {
      "deep_explore_accepted": false,
      "optimize_confirmed": false,
      "jd_continue_despite_not_recommended": false
    }
  }
}
```

### 2.2 闸门流转

| 闸门 | Worker `gate_prompt` | `flags` / profile |
|------|---------------------|-------------------|
| 进入深度探讨 | 协调者邀请 | `deep_explore_accepted` |
| 初探完成（E1） | `gate_owner` 指定 identity 或 capability | `exploration.completed_at` → profile |
| 不推荐仍继续 | opportunity（O1） | `jd_continue…` + `career.jd_override[]` |
| 优化确认 | strategy（St1） | `optimize_confirmed` → 允许派 `resume` |

### 2.3 `match_gate_intent`

| 项 | 约定 |
|----|------|
| 输入 | `user_message` + `gates.pending` + PRD 附录 B 话术 |
| 输出 | `{ matched, gate_name, intent: confirm \| reject \| unknown }` |
| `unknown` | 协调者继续澄清，不改 flag |
| confirm | 更新 `flags` / patch profile / `apply_proposed_patches`；清 `pending` |

### 2.4 B1：未初探走 JD

- 协调者 **软引导**（话术提醒先初探）。
- **不** HTTP `403`；**不** Harness 硬拦 `create_task_list(jd)` / `delegate(opportunity)`。
- **仍硬拦**：无 `optimize_confirmed` → `delegate_worker(resume)` 拒绝。

## 3. Profile 落档双路径（P3）

| 路径 | 何时 |
|------|------|
| **`proposed_profile_patches`** | 待确认草案：`exploration.*`（gate 前）、未选策略路径等 |
| **`profile_patch` tool** | 已确认或客观事实：`exploration.completed_at`、`market.trend_notes`、`opportunity_snapshots`（O-P1 即时）、gate 后字段 |
| **`apply_proposed_patches`** | `match_gate_intent` → confirm 后批量 apply proposed |

同一 path **禁止** 既 proposed 又 tool。

---

*文档结束*
