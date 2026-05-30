# HTTP API 与流式协议

| 属性 | 内容 |
|------|------|
| 文档版本 | v0.3 |
| 父文档 | [00-架构总览.md](./00-架构总览.md) |
| 最后更新 | 2026-05-30（Session 生命周期、gate 说明） |

## 1. 设计原则

- **对话是唯一控制面**：任务开始/放弃、闸门确认、派工推进，均通过 `POST /v1/chat` 消息完成。
- **SSE 承载模型输出**：逐 token 推送，前端增量渲染。
- **非对话 API** 仅用于：建档表单提交、档案只读、产物管理（T-05）、健康检查。

## 2. REST 端点（v0.1）

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/v1/chat` | 用户消息；响应 `text/event-stream` |
| `POST` | `/v1/sessions/new` | 新建会话（清空旧 session 工作区与绑定任务）；返回 `{ "session_id" }` |
| `POST` | `/v1/profile/onboarding` | B01 表单提交（确认进入深度探讨后） |
| `GET` | `/v1/profile` | 读档案摘要（前端表单回显、简历预览） |
| `GET` | `/v1/resume/markdown` | 读 `source.md` 渲染用 |
| `GET` | `/v1/tasks` | 当前任务列表（**只读**，进度条） |
| `GET` | `/v1/outputs` | 产物列表（或静态 index + 本 API） |
| `DELETE` | `/v1/outputs/{encoded_path}` | 删除 HTML + 同步 `outputs_index`（T-05） |
| `GET` | `/healthz` | 存活探针 |

**刻意不提供**（由对话触发）：

- ~~`POST /v1/tasks/{id}/start`~~
- ~~`POST /v1/tasks/{id}/abandon`~~

协调者识别意图后内部调用 `start_task_list` / `abandon_task_list`。

## 3. `POST /v1/chat`

### 3.1 请求

```json
{
  "session_id": "sess_...",
  "message": "用户输入文本",
  "attachments": [
    { "type": "file_ref", "path": "output/2026-05-29/xxx.html" }
  ]
}
```

- `session_id`：首次可省略，响应 `session` 事件带回新 ID。**浏览器刷新（R2）** 视为新会话：前端调用 `POST /v1/sessions/new` 或不带 `session_id`，服务端清空旧工作区（见 [10 §1](./10-会话闸门与state.md#1-会话工作区生命周期)）。
- `attachments`：拖入历史 HTML 等（B05）。
- 请求 **仅** 单条 `message`；历史由服务端 `messages.json` 维护（`begin_chat` 读写）。

### 3.2 SSE 事件

`POST /v1/chat` 的响应为 **SSE（Server-Sent Events）**：HTTP 连接保持打开，服务端 **边处理边推送** 多条事件；前端按 `event` 字段分流处理，而非等待整段 JSON 一次返回。

**响应头**：`Content-Type: text/event-stream`

**单条推送格式（概念）**：

```text
event: token
data: {"delta":"你"}

event: done
data: {"finish_reason":"stop"}

```

每条事件由 `event:`（类型）与 `data:`（JSON 字符串）组成，以空行分隔。

#### 3.2.1 事件类型说明

| event | data 示例 | 含义 | 前端典型处理 |
|-------|-----------|------|--------------|
| `session` | `{"session_id":"sess_..."}` | 当前 **会话 ID**（新建或续接） | 写入 state；后续 `POST /v1/chat` 携带 `session_id` |
| `token` | `{"delta":"你"}` | 面向用户的 **模型增量**（一字或子词） | 追加到当前 assistant 气泡，实现 **逐字输出** |
| `task_snapshot` | `{"list_id":"...","tasks":[...]}` | **任务列表快照**变更（建 list、claim/complete 等） | 刷新只读进度条；**不**提供「开始/放弃」按钮 |
| `form_request` | `{"type":"onboarding"}` | 协调者判定应 **弹出建档表单** | 打开 onboarding UI；提交走 `POST /v1/profile/onboarding` |
| `gate` | `{"name":"optimize_confirm","prompt":"..."}` | 可选 **UI 提示**：当前处于某对话闸门 | **仅**高亮/提示；用户 **必须**在输入框确认；语义以 `match_gate_intent` + [10 §2](./10-会话闸门与state.md#2-gates-闸门) 为准 |
| `error` | `{"code":"...","message":"..."}` | 本轮出错（模型不可用、超时等） | 展示错误；保留已收到的 `token`  partial 文本 |
| `done` | `{"finish_reason":"stop"}` | 对 **本条用户消息** 的处理结束 | 结束 loading；允许发送下一条消息 |

**前端约定**：

- 将所有 `token.data.delta` **字符串拼接** 为完整 assistant 回复。
- 收到 `done` 之前，通常 **禁用** 再次发送，避免并发两条 chat。
- `session_id` 以首条 `session` 或响应上下文为准（若请求未带则必须保存）。

#### 3.2.2 一轮对话中的事件顺序（示例）

用户发送：「我想理清职业方向」

```text
event: session       →  {"session_id":"sess_abc"}
event: token         →  {"delta":"我"}
event: token         →  {"delta":"理解你的诉求…"}
event: token         →  {"delta":"是否进入深度探讨与规划？"}
event: done          →  {"finish_reason":"stop"}
```

用户回复「确认进入深度探讨」后，下一轮可能包含：

```text
event: form_request  →  {"type":"onboarding"}
event: done          →  …
```

协调者派工并更新 `data/tasks` 时，可能在 `token` 流中间插入：

```text
event: task_snapshot →  {"list_id":"list_7f3a…","tasks":[…]}
```

#### 3.2.3 与 Agent 内部的关系

**流式出口唯一**：SSE 的 `token` **仅** 来自协调者 `synthesize`；Worker 在后台 Run，结果由协调者汇总后再以 `token` 输出。Worker **不得** 流式直出到前端。

| 内部行为 | 对用户可见的 SSE |
|----------|------------------|
| 协调者 `synthesize` 流式生成 | `token`（**唯一**用户可见正文来源） |
| `create_task_list` / `complete_task` 等改任务文件 | `task_snapshot` |
| 协调者判定弹表单 | `form_request` |
| Worker Run（含 `load_skill`、业务 tool、内部 LLM 流） | **无** `token`；结论回协调者后再 synthesize |
| 协调者本轮循环结束 | `done` |

任务与表单类 side-effect 通过 `task_snapshot` / `form_request` 驱动 UI；聊天正文 **始终** 经协调者汇总后的 `token` 呈现。

### 3.3 流式路径

```text
协调者 synthesize: LLM token → async generator → FastAPI StreamingResponse → browser fetch reader
Worker 内部 LLM: 仅 Run 内 messages，不接入 SSE 管道
```

服务端需：

- SSE 每个 `token` 事件及时 `yield`（避免整段缓冲）。
- 客户端断开时取消当前 `asyncio` Run 任务。

### 3.4 Session 生命周期（R2：刷新清空）

| 事件 | 行为 |
|------|------|
| `POST /v1/sessions/new` 或首次 chat 无 `session_id` | 生成 `session_id`；若存在旧 session 则清空其 `messages.json`、`state.json` 及绑定 **全部** tasks |
| 每条 chat 结束 | append user/assistant 至 `data/sessions/{id}/messages.json` |
| 浏览器刷新 | 前端 **不**复用旧 `session_id`；UI 聊天气泡为空；**profile / output 保留** |

详见 [10-会话闸门与state.md](./10-会话闸门与state.md)。

## 4. `POST /v1/profile/onboarding`

表单 JSON → `ProfileStore` 初始化 + 写 `resume/source.md` + 协调者后续在对话中 `create_task_list(explore)`（可在提交响应后由后端触发首条系统事件，或等用户下一条消息）。

响应：`201` + `{ "profile_version": 1 }`

## 5. 任务进度只读 `GET /v1/tasks`

返回与 A02 一致的列表视图，供 UI 渲染；**无** `start`/`abandon` action 字段。

用户说「开始执行」→ 下一轮 `chat` → SSE 流中可能含 `task_snapshot`（`status: active`）。

## 6. 错误码

| HTTP | code | 场景 |
|------|------|------|
| 400 | `invalid_request` | 缺字段 |
| 503 | `agent_unavailable` | Python 未启动 |
| 504 | `run_timeout` | Run 超时 |

> v0.1 **不使用** HTTP `403 gate_blocked`：未初探完成走 JD 时由协调者 **软引导**（B1），不硬拦 API。

## 7. Harness Tool：`register_outputs_index`（asset）

> **非 REST**：由 **资产 Worker** 在 Run 内经 Harness 调用；入参通常来自协调者 `delegate_worker` 注入的 `context.html_deliveries`（即 resume `structured_output` 的同名数组）。协作流程见 [01 §4.3](./01-协调者与Worker.md#43-html-交付协作resume-写盘--asset-登记)、[02 §5](./02-平台服务.md#5-存储层)。

### 7.1 调用约束

| 约束 | 说明 |
|------|------|
| `actor` | 必须为 `asset` |
| 前置 | 对应 `path` 的 `.html` **已由 resume** `write_resume_html` 落盘 |
| 副作用 | `ProfileStore.patch(outputs_index[])`；可选 `refresh_index_html` |
| 禁止 | 创建/覆盖 HTML 正文；`path` 不在 `output/` 下 |

### 7.2 请求参数（JSON Schema 语义）

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "career_os.tools.register_outputs_index.request",
  "type": "object",
  "additionalProperties": false,
  "required": ["deliveries"],
  "properties": {
    "deliveries": {
      "type": "array",
      "minItems": 1,
      "description": "与 resume structured_output.html_deliveries 同构（见 §8.3 HtmlDelivery）",
      "items": { "$ref": "#/$defs/HtmlDelivery" }
    },
    "refresh_index": {
      "type": "boolean",
      "default": true,
      "description": "登记后是否重写 output/{session_date}/index.html"
    },
    "dedupe_by_path": {
      "type": "boolean",
      "default": true,
      "description": "path 已存在于 outputs_index 时跳过并记入 skipped"
    }
  },
  "$defs": {
    "HtmlDelivery": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "path",
        "optimization_level",
        "filename_tags",
        "session_date"
      ],
      "properties": {
        "path": {
          "type": "string",
          "description": "相对项目根的路径；须已存在且位于 output/ 下",
          "pattern": "^output/[0-9]{4}-[0-9]{2}-[0-9]{2}/[^/]+\\.html$"
        },
        "filename": {
          "type": "string",
          "description": "展示用文件名；缺省时取 path 最后一段"
        },
        "optimization_level": {
          "type": "string",
          "enum": ["保守", "标准", "进取"]
        },
        "filename_tags": {
          "type": "array",
          "minItems": 1,
          "maxItems": 3,
          "items": { "type": "string", "minLength": 1 }
        },
        "session_date": {
          "type": "string",
          "format": "date",
          "description": "YYYY-MM-DD，与 output 子目录一致"
        },
        "jd_fingerprint": {
          "type": "string",
          "description": "关联 JD 指纹（可选）"
        },
        "created_at": {
          "type": "string",
          "format": "date-time",
          "description": "缺省时由 Harness 写入当前 UTC ISO8601"
        }
      }
    }
  }
}
```

**请求示例**（协调者注入 `context` 后 asset 调用）：

```json
{
  "deliveries": [
    {
      "path": "output/2026-05-30/2026-05-30-后端-云原生-标准.html",
      "filename": "2026-05-30-后端-云原生-标准.html",
      "optimization_level": "标准",
      "filename_tags": ["后端", "云原生"],
      "session_date": "2026-05-30",
      "jd_fingerprint": "sha256:abc..."
    },
    {
      "path": "output/2026-05-30/2026-05-30-后端-云原生-进取.html",
      "optimization_level": "进取",
      "filename_tags": ["后端", "云原生"],
      "session_date": "2026-05-30"
    }
  ],
  "refresh_index": true
}
```

### 7.3 成功响应

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "career_os.tools.register_outputs_index.response.ok",
  "type": "object",
  "required": ["registered", "skipped", "index_html_path"],
  "properties": {
    "registered": {
      "type": "array",
      "items": { "$ref": "#/$defs/OutputsIndexEntry" },
      "description": "本次新写入 profile.outputs_index 的条目"
    },
    "skipped": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["path", "reason"],
        "properties": {
          "path": { "type": "string" },
          "reason": {
            "type": "string",
            "enum": ["duplicate_path", "file_not_found", "validation_failed"]
          }
        }
      }
    },
    "index_html_path": {
      "type": "string",
      "description": "已刷新或保持的 index.html 路径"
    },
    "custom_tags_appended": {
      "type": "array",
      "items": { "type": "string" },
      "description": "按 A01 §5.1.5 沉淀至 preference_tags.custom[] 的词表外标签（若有）"
    }
  },
  "$defs": {
    "OutputsIndexEntry": {
      "type": "object",
      "description": "与 A01 outputs_index[] 一致",
      "required": ["path", "created_at", "optimization_level", "filename_tags"],
      "properties": {
        "path": { "type": "string" },
        "created_at": { "type": "string", "format": "date-time" },
        "optimization_level": { "type": "string", "enum": ["保守", "标准", "进取"] },
        "filename_tags": { "type": "array", "items": { "type": "string" } },
        "jd_fingerprint": { "type": "string" },
        "session_date": { "type": "string", "format": "date" }
      }
    }
  }
}
```

**响应示例**：

```json
{
  "registered": [
    {
      "path": "output/2026-05-30/2026-05-30-后端-云原生-标准.html",
      "created_at": "2026-05-30T12:00:00Z",
      "optimization_level": "标准",
      "filename_tags": ["后端", "云原生"],
      "jd_fingerprint": "sha256:abc...",
      "session_date": "2026-05-30"
    }
  ],
  "skipped": [],
  "index_html_path": "output/2026-05-30/index.html",
  "custom_tags_appended": []
}
```

### 7.4 Tool 错误（Harness 层，非 HTTP）

| code | 场景 | 对 Worker 行为 |
|------|------|----------------|
| `invalid_deliveries` | JSON 未通过 schema | 返回 tool error，asset 可重试或上报协调者 |
| `file_not_found` | `path` 对应文件不存在 | 记入 `skipped`；若 `min_success` 未满足则整 tool 失败（实现可选） |
| `path_not_allowed` | 不在 `output/` 或路径穿越 | 拒绝整次调用 |
| `profile_patch_rejected` | 白名单/并发写冲突 | 返回 tool error |

> **与 `DELETE /v1/outputs/{encoded_path}`**：用户删除走 REST + 资产逻辑；`register_outputs_index` **仅追加/更新索引**，不删除条目。删除同步见 §2 `DELETE` 与 [B07 §5.7.6](../prd/B07.%20流程-HTML%20交付%20PRD.md#576-简历文件管理打开--删除)。

## 8. Harness Tool：`write_resume_html`（resume）

> **非 REST**：由 **简历 Worker** 在 Run 内经 Harness 调用；每档优化通常调用 **一次**，多档则多次调用，Run 结束时汇总为 `structured_output.html_deliveries[]`。登记索引由 asset 执行 [§7](#7-harness-toolregister_outputs_indexasset)。协作见 [01 §4.3](./01-协调者与Worker.md#43-html-交付协作resume-写盘--asset-登记)。

### 8.1 调用约束

| 约束 | 说明 |
|------|------|
| `actor` | 必须为 `resume` |
| 闸门 | Harness 须已记录 `optimize_confirmed=true`（[B04 §5.4.3](../prd/B04.%20流程-职业战略与投递策略%20PRD.md#543-优化确认的定义)）；否则拒绝 |
| 正文 | `body_html` **仅** 简历投递正文（[B07 §5.7.4](../prd/B07.%20流程-HTML%20交付%20PRD.md#574-页面结构)：无顶栏、无管理 UI） |
| 副作用 | 写入 `output/{session_date}/{filename}.html`；**不** 修改 `profile.outputs_index`（由 asset 登记） |
| 禁止 | `asset` / 协调者调用；禁止写入 `output/` 外路径 |

### 8.2 请求参数（JSON Schema 语义）

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "career_os.tools.write_resume_html.request",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "body_html",
    "optimization_level",
    "filename_tags",
    "session_date"
  ],
  "properties": {
    "body_html": {
      "type": "string",
      "minLength": 1,
      "description": "完整 HTML 文档或 <body> 片段；Harness 落盘前可包裹打印样式模板"
    },
    "optimization_level": {
      "type": "string",
      "enum": ["保守", "标准", "进取"]
    },
    "filename_tags": {
      "type": "array",
      "minItems": 1,
      "maxItems": 3,
      "items": { "type": "string", "minLength": 1 },
      "description": "能力偏好摘要，按 A01 §5.1.5 选取；用于生成文件名"
    },
    "session_date": {
      "type": "string",
      "format": "date",
      "description": "YYYY-MM-DD；目标目录 output/{session_date}/"
    },
    "jd_fingerprint": {
      "type": "string",
      "description": "关联 JD 指纹（可选，写入 delivery 供 asset 登记）"
    },
    "reuse_from_path": {
      "type": "string",
      "description": "增量优化：基线 HTML 路径（可选，只读参考，不修改源文件）"
    },
    "allow_overwrite": {
      "type": "boolean",
      "default": false,
      "description": "目标 path 已存在时是否覆盖；默认 false 并自动重名 (1)(2)…"
    }
  }
}
```

**请求示例**：

```json
{
  "body_html": "<!DOCTYPE html><html><head><meta charset=\"utf-8\"><title>简历</title></head><body><section>...</section></body></html>",
  "optimization_level": "标准",
  "filename_tags": ["后端", "云原生"],
  "session_date": "2026-05-30",
  "jd_fingerprint": "sha256:abc...",
  "allow_overwrite": false
}
```

**文件名生成（Harness 实现，非请求字段）**：

```text
{session_date}-{filename_tags 用「-」连接}-{optimization_level 映射后缀}.html
例：2026-05-30-后端-云原生-标准.html
```

- 后缀映射：`保守` → `-保守`；`标准` → `-标准`；`进取` → `-进取`（[B07 §5.7.3](../prd/B07.%20流程-HTML%20交付%20PRD.md#573-文件命名)）。
- 与同目录 / `outputs_index` 冲突时，在 **标签段末尾** 追加 `(1)`、`(2)` … 直至唯一。

### 8.3 成功响应

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "career_os.tools.write_resume_html.response.ok",
  "type": "object",
  "required": ["delivery", "bytes_written"],
  "properties": {
    "delivery": {
      "$ref": "career_os.types.HtmlDelivery",
      "description": "与 §7.2 HtmlDelivery / structured_output.html_deliveries[] 单条同构"
    },
    "bytes_written": { "type": "integer", "minimum": 0 },
    "filename_disambiguated": {
      "type": "boolean",
      "description": "是否因重名追加了 (n) 后缀"
    }
  }
}
```

**`HtmlDelivery`（共用类型，§7.2 / §8.3 / WorkerResult）**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `path` | string | 是 | 落盘后的相对路径 |
| `filename` | string | 否 | 缺省为 `path` 末段 |
| `optimization_level` | enum | 是 | `保守` \| `标准` \| `进取` |
| `filename_tags` | string[] | 是 | 1–3 个 |
| `session_date` | date | 是 | `YYYY-MM-DD` |
| `jd_fingerprint` | string | 否 | |
| `created_at` | date-time | 否 | 缺省由 Harness 写入 |

**响应示例**：

```json
{
  "delivery": {
    "path": "output/2026-05-30/2026-05-30-后端-云原生-标准.html",
    "filename": "2026-05-30-后端-云原生-标准.html",
    "optimization_level": "标准",
    "filename_tags": ["后端", "云原生"],
    "session_date": "2026-05-30",
    "jd_fingerprint": "sha256:abc...",
    "created_at": "2026-05-30T12:00:00Z"
  },
  "bytes_written": 18432,
  "filename_disambiguated": false
}
```

### 8.4 与 `WorkerResult` 的衔接

resume Run 在 `emit` 节点汇总多次 tool 结果：

```json
{
  "worker_id": "resume",
  "status": "completed",
  "structured_output": {
    "html_deliveries": [
      { "...": "delivery from write_resume_html call 1" },
      { "...": "delivery from write_resume_html call 2" }
    ],
    "user_visible_summary": "已生成 2 份简历 HTML（标准、进取）"
  }
}
```

协调者将 `html_deliveries` 注入 asset 的 `delegate_worker.context`（见 §7）。

### 8.5 Tool 错误（Harness 层，非 HTTP）

| code | 场景 | 对 Worker 行为 |
|------|------|----------------|
| `gate_blocked` | 未 `optimize_confirmed` | 拒绝调用 |
| `invalid_body` | `body_html` 空或含禁止的管理 UI 标记（实现可选启发式） | tool error |
| `invalid_tags` | `filename_tags` 为空或超长 | tool error |
| `path_not_allowed` | 解析路径逃逸 `output/` | tool error |
| `write_failed` | 磁盘 IO 失败 | tool error |

---

*文档结束*
