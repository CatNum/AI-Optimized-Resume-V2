# Harness Tools Schema 全集（S2）

| 属性 | 内容 |
|------|------|
| 文档版本 | v0.1 |
| 父文档 | [02-平台服务 §3](./02-平台服务.md#3-tool-管理) |
| 最后更新 | 2026-05-30 |

> **S2 约定**：Tool 参数 JSON Schema 集中本文档索引；HTML 交付类完整 schema 仍详述于 [05 §7–8](./05-API与流式协议.md#7-harness-toolregister_outputs_indexasset)。实现期 Pydantic 模型与本文 `$id` 对齐。

## 1. 工具分层

| 集合 | actor | 工具 |
|------|-------|------|
| `coordinator_tools` | `coordinator` | 见 §2 |
| `worker_meta_tools` | 各 Worker | `list_skills`, `load_skill` |
| 业务 tools | 按 Worker | 见 §3–§4 |

Worker **仅可见** 其 `tool_index` 内工具；执行统一走 `Harness.execute_tool(actor, name, args)`。

## 2. 协调者工具

### 2.1 `delegate_worker`

```json
{
  "required": ["worker_id", "goal"],
  "properties": {
    "worker_id": { "enum": ["identity", "capability", "market", "opportunity", "strategy", "resume", "asset"] },
    "goal": { "type": "string" },
    "context": { "type": "object", "additionalProperties": true }
  }
}
```

**Harness 硬约束**：无 `optimize_confirmed` → `worker_id=resume` 拒绝（`gate_blocked`）。`list_type=jd` 且无 `session_state.prior_results.market` → `worker_id=opportunity` 拒绝（`delegate_blocked`，JD-R1）。

### 2.2 Task 工具

| tool | 必填参数 | 说明 |
|------|----------|------|
| `create_task_list` | `list_type`, `session_id` | `explore` \| `jd` \| `plan` |
| `create_task` | `list_id`, `kind`, `subject`, `list_type` | 可选 `blockedBy`, `metadata` |
| `start_task_list` | `list_id` | `ready` → `active` |
| `abandon_task_list` | `list_id` | 删 list |
| `list_tasks` | `list_id`? | 缺省当前 active |
| `get_task` | `task_id` | |
| `claim_task` | `task_id` | `ready` list 禁止 |
| `complete_task` | `task_id` | 删 `{task_id}.json` |

### 2.3 `profile_get`

```json
{ "properties": { "paths": { "type": "array", "items": { "type": "string" } } } }
```

空 `paths` = 返回协调者可见摘要切片。

### 2.4 `match_gate_intent`（M2）

见 [10 §2.3](./10-会话闸门与state.md#23-match_gate_intent) 与 §5 附录 B 映射。

```json
{
  "required": ["user_message"],
  "properties": {
    "user_message": { "type": "string" },
    "pending_gate": { "type": "object", "properties": { "name": { "type": "string" }, "prompt": { "type": "string" } } }
  }
}
```

**响应**：

```json
{
  "matched": true,
  "gate_name": "optimize_confirm",
  "intent": "confirm",
  "confidence": 0.95,
  "source": "rule",
  "reason": null
}
```

`source`：`rule`（硬规则命中）| `llm`（含低于阈值降级）| `none`（无 LLM）。`reason` 仅 LLM/trace，不展示给用户。

`intent`: `confirm` | `reject` | `unknown`。

### 2.5 `apply_proposed_patches`

```json
{
  "required": ["patches"],
  "properties": {
    "patches": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["path", "value"],
        "properties": {
          "path": { "type": "string" },
          "value": {}
        }
      }
    }
  }
}
```

须在 `match_gate_intent` → `confirm` 之后调用。

### 2.6 `parse_task_control_intent`

```json
{
  "required": ["user_message"],
  "properties": { "user_message": { "type": "string" } }
}
```

**响应**：`{ "intent": "start" | "abandon" | "none", "list_id"?: string }`。

## 3. Worker 元工具

### 3.1 `load_skill`

```json
{
  "required": ["name"],
  "properties": {
    "name": { "type": "string" },
    "mode": { "type": "string" }
  }
}
```

Harness 校验 `allowed_workers[mode]`（见 [A03](../prd/A03.%20机制-技能包%20PRD.md) K2）。

### 3.2 `list_skills`

可选 `filter.worker_id`。

## 4. 业务 Tool（按 Worker）

### 4.1 `profile_patch`

```json
{
  "required": ["path", "value"],
  "properties": {
    "path": { "type": "string" },
    "value": {},
    "op": { "enum": ["set", "append"], "default": "set" }
  }
}
```

白名单见 [13-Profile-写入权限.md](./13-Profile-写入权限.md)。

### 4.2 `resume_read`

```json
{ "properties": { "path": { "type": "string", "default": "data/resume/source.md" } } }
```

### 4.3 `write_resume_html`（resume）

完整 schema：[05 §8](./05-API与流式协议.md#8-harness-toolwrite_resume_htmlresume)。

### 4.4 `register_outputs_index`（asset）

完整 schema：[05 §7](./05-API与流式协议.md#7-harness-toolregister_outputs_indexasset)。

### 4.5 `delete_output`（asset）

```json
{
  "required": ["path"],
  "properties": { "path": { "type": "string", "pattern": "^output/" } }
}
```

### 4.6 `browser_fetch`（market / opportunity）

见 [11-L7-浏览器Tool.md](./11-L7-浏览器Tool.md)。

## 5. 通用 Tool 错误码

| code | 场景 |
|------|------|
| `gate_blocked` | 闸门未满足（如 resume 无 optimize_confirmed） |
| `delegate_blocked` | 派工前置未满足（如 JD-R1：缺 `prior_results.market`） |
| `profile_patch_rejected` | 白名单 / actor / 并发冲突 |
| `task_blocked` | `blockedBy` / `ready` list / milestone 未完成 |
| `skill_not_allowed` | `load_skill` actor 不在 `allowed_workers` |
| `invalid_request` | JSON schema 校验失败 |

## 6. `structured_output`（Worker 返回，非 Tool）

各 Worker Pydantic 契约见 [09-Worker结构化输出.md](./09-Worker结构化输出.md)（S2：`extra="allow"`）。

---

*文档结束*
