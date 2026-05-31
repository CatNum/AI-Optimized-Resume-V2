# Worker 结构化输出契约

| 属性 | 内容 |
|------|------|
| 文档版本 | v0.6 |
| 父文档 | [01-协调者与Worker.md](./01-协调者与Worker.md) |
| 最后更新 | 2026-05-31（Opt-1 三档纯对话解析） |

## 1. 通则（S2）

| 规则 | 说明 |
|------|------|
| 载体 | `WorkerResult.structured_output`，按 `worker_id` 注册 Pydantic 模型 |
| 校验 | Worker 子图 `emit` 节点；**核心字段严格**，`model_config = extra="allow"` |
| 失败 | 校验失败 → Run `status: failed` → 协调者 synthesize 说明未完成 |
| 用户可见 | **仅**协调者 synthesize；Worker **不**映射 SSE `token` |
| **explore 收束（E2）** | `explore_complete` / `explore_review_complete`：**禁止** Worker `gate_prompt`；由协调者在 `explore_closure` 齐套后发问（[10 §2.5](./10-会话闸门与state.md#25-explore_closuree2-双-worker-收束)） |
| 外层 | `internal_notes`、`proposed_profile_patches`、`proposed_task_completions` 在 `WorkerResult` 上，非 `structured_output` 内 |
| **B3** | Worker **禁止** `complete_task`；`proposed_task_completions` 供协调者 gate/Run 成功后代为 complete（[02 §5.5](./02-平台服务.md#55-任务完成b3)） |

## 2. 各 Worker 契约

### 2.1 `identity`

| 字段 | 必填 | 说明 |
|------|:----:|------|
| `user_visible_summary` | ✓ | 协调者 synthesize |
| `exploration_draft` | ✓ | 本轮提议的 exploration 片段（gate 前为草案，经 `proposed_profile_patches`） |
| `gate_prompt` | **禁止** | explore / explore_review 收束（E2）；其他 gate 不适用 |
| `is_review_mode` | 可选 | 初探复盘短路径 |

### 2.2 `capability`

| 字段 | 必填 | 说明 |
|------|:----:|------|
| `user_visible_summary` | ✓ | |
| `bank_delta_summary` | ✓ | 无变更时写「沿用既有 bank」 |
| `gate_prompt` | **禁止** | explore / explore_review 收束（E2） |
| `gate_prompt` | 条件 | `jd_bank_deep_dive`（B06 §5.5.0）时 **必填** |

### 2.3 `market`

| 字段 | 必填 | 说明 |
|------|:----:|------|
| `user_visible_summary` | ✓ | |
| `topics` | ✓ | ≥1 条 `{ topic, summary }` |
| `external_sources` | 条件 | 本轮调用 `browser_fetch` 时 **必填** |
| `role_families` | 条件 | 用户咨询岗位族/方向时必填 |
| `gate_prompt` | **禁止** | |

### 2.4 `opportunity`（O1）

| 字段 | 必填 | 说明 |
|------|:----:|------|
| `recommendation` | ✓ | `recommended` \| `not_recommended` |
| `user_visible_summary` | ✓ | |
| `jd_fingerprint` | ✓ | 有 JD 输入时 |
| `match_highlights` / `blockers` / `risks` | 推荐 | 列表，可为空数组 |
| `gate_prompt` | 条件 | `not_recommended` 时 **必填**（O1） |

**落档（O-P1）**：Run 完成后 **立即** `profile_patch` 追加 `market.opportunity_snapshots[]`；`career.jd_override[]` 在用户确认仍继续后写入。

### 2.5 `strategy`（St1）

| 字段 | 必填 | 说明 |
|------|:----:|------|
| `user_visible_summary` | ✓ | |
| `path_options` | ✓ | `{ id, label, summary, risks }[]` |
| `three_horizons` | ✓ | `{ apply_narrative, horizon_1_2y, horizon_3_5y }` |
| `gate_prompt` | 条件 | `context.requires_optimize_gate=true`（JD 路径）时 **必填** |
| `gate_prompt` | **禁止** | `list_type=plan` 时不得出现 |
| `selected_path_id` | 可选 | 用户已选路径时 |

### 2.6 `resume`

| 字段 | 必填 | 说明 |
|------|:----:|------|
| `user_visible_summary` | ✓ | |
| `html_deliveries` | ✓ | 与 [05 §8](./05-API与流式协议.md#8-harness-toolwrite_resume_htmlresume) 同构；`status=completed` 时 **≥1** |

**约束**：仅 `optimize_confirmed` 后可派工；Run 内须调用 `write_resume_html`，次数与 `context.selected_optimization_levels.length` 一致（**顺序** 保守→标准→进取，N≥1）。Run 成功后 **`profile_patch`** 更新 `resume.last_optimization_levels[]` 为本次所选（跨 session 默认档）。

### 2.7 `asset`

由 `context.run_kind` 区分：

**`run_kind: "reuse"`（B05）**

| 字段 | 必填 |
|------|:----:|
| `user_visible_summary` | ✓ |
| `reuse_recommendation` | ✓ `{ action: skip\|base\|new, recommended_path?, reason }` |
| `gate_prompt` | ✓ |

**`run_kind: "register"`（B07）**

| 字段 | 必填 |
|------|:----:|
| `user_visible_summary` | ✓ |
| `registered_deliveries` | ✓ ≥1 |
| `gate_prompt` | **禁止** |

## 3. 与 `prior_results` 的关系

协调者将已完成 Worker 的 `structured_output` **摘要或全文** 写入 `state.json` → `prior_results.{worker_id}`，供同 session 内下游 `DelegateRequest.context` 注入；**不**跨 session（换会话清空）。

---

*文档结束*
