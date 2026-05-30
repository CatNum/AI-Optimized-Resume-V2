# HTTP API 与流式协议

| 属性 | 内容 |
|------|------|
| 文档版本 | v0.3 |
| 父文档 | [00-架构总览.md](./00-架构总览.md) |
| 最后更新 | 2026-05-29 |

## 1. 设计原则

- **对话是唯一控制面**：任务开始/放弃、闸门确认、派工推进，均通过 `POST /v1/chat` 消息完成。
- **SSE 承载模型输出**：逐 token 推送，前端增量渲染。
- **非对话 API** 仅用于：建档表单提交、档案只读、产物管理（T-05）、健康检查。

## 2. REST 端点（v0.1）

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/v1/chat` | 用户消息；响应 `text/event-stream` |
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

- `session_id`：首次可省略，响应 `done` 事件带回新 ID。
- `attachments`：拖入历史 HTML 等（B05）。

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
| `gate` | `{"name":"optimize_confirm","prompt":"..."}` | 可选：当前处于某 **对话闸门** | 可高亮提示；用户仍通过 **输入框** 确认（PRD 无专用按钮） |
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
LLM token → coordinator/worker async generator → FastAPI StreamingResponse → browser fetch reader
```

服务端需：

- SSE 每个 `token` 事件及时 `yield`（避免整段缓冲）。
- 客户端断开时取消当前 `asyncio` Run 任务。

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
| 403 | `gate_blocked` | 未确认初探却请求 JD 流程（可选硬拦） |
| 503 | `agent_unavailable` | Python 未启动 |
| 504 | `run_timeout` | Run 超时 |

---

*文档结束*
