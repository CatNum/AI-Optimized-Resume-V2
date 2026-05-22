# Agent Skills（本项目）

本目录存放 **职业规划 Agent** 专用 Skills。由 **自建 Harness** 通过 `load_skill(name)` 读取并注入子 Agent 上下文，**不** 依赖 Cursor IDE 的 skill 发现。

## 加载方式（Harness）

```text
load_skill(name)
  → 读取 .agent/skills/{name}/SKILL.md
  → 可选附加 .agent/skills/{name}/phases.md 等
  → 注入规划师 / 简历专家 system prompt
```

主 Agent 根据阶段 **显式** 调用，参见 PRD §5.2.5。

## Skill 一览

| name | 路径 | 执行者 | 阶段 |
|------|------|--------|------|
| `career-inner-exploration` | [skills/career-inner-exploration/](skills/career-inner-exploration/) | 规划师 | 用户确认进入并提交表单后初探 / **初探复盘** |
| `career-jd-alignment` | [skills/career-jd-alignment/](skills/career-jd-alignment/) | 规划师 | JD 评估后、确认优化简历前（`jd_*`） |
| `resume-module-optimize` | [skills/resume-module-optimize/](skills/resume-module-optimize/) | 简历专家 | 用户确认按 JD 优化后（`jd_*` 的 `work`） |

## 触发矩阵

| 场景 | load_skill |
|------|------------|
| 简单咨询 | 不加载 |
| 用户确认进入深度探讨 + 表单提交后 | `career-inner-exploration`（五主题 + 简历深挖） |
| 初探复盘 | `career-inner-exploration`（复盘短路径） |
| JD 对齐探讨 | `career-jd-alignment` |
| 模块化改简历 + HTML | `resume-module-optimize` |
| 简单问答 | 不加载 |

## 与 Task 系统

- `explore_*` milestone「职业初探」⇄ `career-inner-exploration`
- `jd_*` milestone「JD 对齐」⇄ `career-jd-alignment`
- `jd_*` 的 `work` 子任务 ⇄ `resume-module-optimize`

产品规格：[docs/prd/career-planning-agent-prd.md](../docs/prd/career-planning-agent-prd.md)（Agent 架构见 §4.1；功能规格见第 5 章）
