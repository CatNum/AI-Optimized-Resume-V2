# 智能体技能包（本项目）

本目录存放 **职业规划智能体** 专用技能包。由 **自建运行框架** 通过 `load_skill(name)` 读取并注入子智能体上下文。

**方法论参考**：[Superpowers](https://github.com/obra/superpowers)（初探技能包范式取自 [brainstorming](https://github.com/obra/superpowers/tree/main/skills/brainstorming)）。

## 加载方式（运行框架）

```text
load_skill(name)
  → 读取 .agent/skills/{name}/SKILL.md
  → 可选附加 .agent/skills/{name}/phases.md 等
  → Worker Run 内按需注入上下文（非协调者预加载）
```

协调者派工附 **skill 索引**；Worker 在 Run 内 **自行** `load_skill`，参见 [A03](../docs/prd/A03.%20机制-技能包%20PRD.md) 与 [架构 02-平台服务](../docs/architecture/02-平台服务.md)。

## 技能包一览

| 标识名 | 路径 | 执行者 | 阶段 |
|------|------|--------|------|
| `career-inner-exploration` | [skills/career-inner-exploration/](skills/career-inner-exploration/) | 身份智能体 + 能力智能体 | 用户确认进入并提交表单后初探 / **初探复盘** |
| `career-jd-alignment` | [skills/career-jd-alignment/](skills/career-jd-alignment/) | 策略智能体 | 岗位评估后、确认优化简历前（`list_type=jd`） |
| `resume-module-optimize` | [skills/resume-module-optimize/](skills/resume-module-optimize/) | 简历智能体 | 用户确认按岗位描述优化后（`list_type=jd` 的 `work`） |

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

- `list_type=explore` 里程碑「职业初探」⇄ `career-inner-exploration`
- `list_type=jd` 里程碑「岗位对齐」⇄ `career-jd-alignment`
- `list_type=jd` 的 `work` 工作子任务 ⇄ `resume-module-optimize`

产品规格：[docs/prd/00. 职业规划 Agent PRD.md](../docs/prd/00.%20职业规划%20Agent%20PRD.md)（总领 §4.1 智能体架构）；[§5 功能规格索引](../docs/prd/00.%20职业规划%20Agent%20PRD.md#5-功能规格索引) 链至 A/B 子 PRD
