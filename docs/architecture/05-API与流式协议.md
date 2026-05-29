# HTTP API 与流式协议

| 属性 | 内容 |
|------|------|
| 文档版本 | v0.1 |
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

`Content-Type: text/event-stream`

| event | data 示例 | 说明 |
|-------|-----------|------|
| `session` | `{"session_id":"sess_..."}` | 首包或新建会话 |
| `token` | `{"delta":"你"}` | 模型增量字符/子词 |
| `task_snapshot` | `{"list_id":"...","tasks":[...]}` | 任务变更后推送（进度条刷新） |
| `form_request` | `{"type":"onboarding"}` | 协调者判定可弹建档表单 |
| `gate` | `{"name":"optimize_confirm","prompt":"..."}` | 闸门提示（可选，辅助 UI 高亮） |
| `error` | `{"code":"...","message":"..."}` | 可恢复/不可恢复错误 |
| `done` | `{"finish_reason":"stop"}` | 本轮结束 |

前端对 `token` 事件做字符串拼接；`done` 后允许下一条用户消息。

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
