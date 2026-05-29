# PRD → 架构追溯表

| 属性 | 内容 |
|------|------|
| 文档版本 | v0.2 |
| 最后更新 | 2026-05-29 |

## 机制类

| PRD | 架构模块 | 文档 |
|-----|----------|------|
| A01 职业档案 | `store/profile`, `store/resume`, Patch 白名单 | [02-平台服务.md](./02-平台服务.md) |
| A02 任务系统 | `platform/task`, Preset, ID 规则, 对话启停 | [02-平台服务.md](./02-平台服务.md) |
| A03 技能包 | `platform/skill`, `.agent/skills` | [02-平台服务.md](./02-平台服务.md) |

## 流程类

| PRD | 协调者/Worker | 文档 |
|-----|---------------|------|
| B01 入口建档 | `coordinator` + 表单 API | [05-API与流式协议.md](./05-API与流式协议.md) |
| B02 初探 | `identity`, `capability` + skill `career-inner-exploration` | [01-协调者与Worker.md](./01-协调者与Worker.md) |
| B03 市场/JD | `market`, `opportunity` | [01-协调者与Worker.md](./01-协调者与Worker.md) |
| B04 策略 | `strategy` + skill `career-jd-alignment` | [01-协调者与Worker.md](./01-协调者与Worker.md) |
| B05 复用 | `asset`（优化前） | [01-协调者与Worker.md](./01-协调者与Worker.md) |
| B06 优化 | `capability`, `resume` + skill `resume-module-optimize` | [01-协调者与Worker.md](./01-协调者与Worker.md) |
| B07 HTML | `asset`（落盘/index） | [02-平台服务.md](./02-平台服务.md) |

## 总领 PRD 特殊项

| PRD 条目 | 架构决策 |
|----------|----------|
| §4.1 Multi-Agent 互调 | **废弃** → 一主多从 [01-协调者与Worker.md](./01-协调者与Worker.md) |
| §4.1 L2 Workflow | 协调者循环 + `delegate_worker` |
| 附录 B 闸门 | 对话-only；`gate` SSE 可选 |
| 附录 C 目录 | `store` 路径一致 |
| T-05 index 删除 | `DELETE /v1/outputs` |
| T-06 任务启发式 | 协调者 + `parse_task_control_intent` |
| 执行层暂缓 | 无模块 |

## 架构讨论结论

| # | 日期 | 结论 |
|---|------|------|
| 1 | 2026-05-29 | 一主多从，Worker 互不通信 |
| 2 | 2026-05-29 | 平台服务：Prompt / Skill / Tool / Task / 存储 |
| 3 | 2026-05-29 | ~~Go + Python gRPC~~ → **纯 Python 单体** `career_os`（见 [04-应用运行时与部署.md](./04-应用运行时与部署.md)） |
| 4 | 2026-05-29 | REST + SSE 逐字流式 |
| 5 | 2026-05-29 | 任务开始/放弃仅对话，无专用 API/按钮 |
| 6 | 2026-05-29 | **Python + Web**（FastAPI + React） |
| 7 | 2026-05-29 | **LangChain + LangGraph 结合**：LC 提供 Prompt/Model/Tool，LG 编排协调者与 Worker 子图 → [07-Agent运行时.md](./07-Agent运行时.md) |
| 8 | 2026-05-29 | 前端 React + Vite → [06-前端架构.md](./06-前端架构.md) |
| 9 | 2026-05-29 | 多篇 `docs/architecture/` |
| 10 | — | 实施顺序后续讨论 |

---

*文档结束*
