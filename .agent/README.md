# 智能体技能包（本项目）

本目录存放 **职业规划智能体** 专用技能包。由 **自建运行框架** 通过 `load_skill(name)` 读取并注入子智能体上下文，**不** 依赖 Cursor IDE 的技能发现。

## 加载方式（运行框架）

```text
load_skill(name)
  → 读取 .agent/skills/{name}/SKILL.md
  → 可选附加 .agent/skills/{name}/phases.md 等
  → 注入身份/能力/策略/简历等子智能体系统提示
```

入口编排智能体根据阶段 **显式** 调用，参见 PRD §5.2.5。

## 技能包一览

| 标识名 | 路径 | 执行者 | 阶段 |
|------|------|--------|------|
| `career-inner-exploration` | [skills/career-inner-exploration/](skills/career-inner-exploration/) | 身份智能体 + 能力智能体 | 用户确认进入并提交表单后初探 / **初探复盘** |
| `career-jd-alignment` | [skills/career-jd-alignment/](skills/career-jd-alignment/) | 策略智能体 | 岗位评估后、确认优化简历前（`jd_*`） |
| `resume-module-optimize` | [skills/resume-module-optimize/](skills/resume-module-optimize/) | 简历智能体 | 用户确认按岗位描述优化后（`jd_*` 的 `work`） |

## 触发矩阵

| 场景 | load_skill |
|------|------------|
| 简单咨询 | 不加载 |
| 用户确认进入深度探讨 + 表单提交后 | `career-inner-exploration`（五主题 + 简历深挖） |
| 初探复盘 | `career-inner-exploration`（复盘短路径） |
| 投递策略对齐探讨 | `career-jd-alignment` |
| 模块化改简历 + 网页 | `resume-module-optimize` |
| 简单问答 | 不加载 |

## 与任务系统

- `explore_*` 里程碑「职业初探」⇄ `career-inner-exploration`
- `jd_*` 里程碑「岗位对齐」⇄ `career-jd-alignment`
- `jd_*` 的 `work` 工作子任务 ⇄ `resume-module-optimize`

产品规格：[docs/prd/career-planning-agent-prd.md](../docs/prd/career-planning-agent-prd.md)（智能体架构见 §4.1；功能规格见第 5 章）
