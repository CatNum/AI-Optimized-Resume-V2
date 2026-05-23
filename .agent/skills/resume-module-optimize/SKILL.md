---
name: resume-module-optimize
description: >-
  Guides modular resume optimization for a specific JD after user confirms
  optimize-by-JD. Use when jd_* task list has completed alignment milestone and
  work subtasks exist (e.g. experience section, projects, generate HTML). Applies
  Conservative/standard/aggressive optimization tiers (保守/标准/进取). Agent ReAct
  completes work tasks without per-module
  user confirmation. MUST NOT run exploration or JD recommendation. Invoked by
  resume sub-agent via Harness load_skill, not IDE.
---

# 简历模块化优化

用户已 **确认按该岗位描述优化简历**，且入口编排智能体已创建 `jd_*` 列表下的 **`work` 工作子任务**（按简历模块拆分）。本技能包约束 **简历智能体** 在推理-行动循环中逐模块执行，**小步 complete**，无需用户逐步确认每个模块。

## HARD-GATE

**禁止**：

- 开展职业初探或 JD 对齐式长篇探讨（澄清一句即可，不加载 `career-inner-exploration` / `career-jd-alignment`）
- 虚构未提供的经历、项目、职级、指标
- 在用户未确认优化前开始改简历

**必须**：

- 遵守用户 **多选** 的语义档位 **`保守`/`标准`/`进取`**（至少一档）；**每档各生成一份** HTML，文件名含 `-保守`/`-标准`/`-进取` 后缀（见下表与 PRD §5.5）
- 对齐当前岗位描述的必备项表述（**标准/进取** 档）
- 每个 `work` 任务：`claim` → 修改 → `complete` → 删除对应 task JSON（§5.8.6）
- 全部 work 完成后生成/更新 HTML 并维护 `outputs_index[]`

---

## 优化三档（与 PRD §5.5 一致）

| 档位 | 允许 | 禁止 |
|------|------|------|
| **保守** | 措辞、结构、错别字 | 新增未提供事实 |
| **标准** | 保守档 + 情境-任务-行动-结果（STAR）+ 基于档案的量化 | 夸大或虚构指标 |
| **进取** | 标准档 + 招聘系统关键词、可迁移能力突出 | 任何造假 |

---

## 执行清单

1. **读取上下文** — `profile.json`（`resume.source_text`、**`resume.experience_bank`**、`exploration.summary`、`career.*`、本 JD 指纹）、用户 **多选档位** `levels[]`（如 `["保守","进取"]`）、复用决策（沿用某 HTML / 新建）。**标准/进取** 档补全经历时 **优先** 使用 `experience_bank` 中经初探确认的事实，禁止添加 bank 与对话均未出现的内容。
2. **复用分支**
   - 用户指定或已确认复用某 HTML → 以该版为基底，仅跑未覆盖的 `work`
   - 跳过优化 → 不创建新文件，直接 `complete` 剩余 work 并说明原因
3. **按 work 顺序执行**（典型拆分，入口编排智能体可动态增减）：
   - 工作经历模块
   - 项目经历模块
   - 技能/其他模块
   - 全文连贯性 pass（可选 work）
   - **大语言模型选取文件名标签**（见下）→ 对 **每个所选档位** 生成 `{YYYY-MM-DD}-{能力偏好摘要}-{保守|标准|进取}.html`
   - 更新 `index.html` 列表（每档一行，`outputs_index[].optimization_level`）
4. **单模块循环** — 每个 work：`claim_task` → 产出修改片段（内部推理）→ 合并进当前稿 → `complete_task`（删除该 task 文件）
5. **文件名标签（大语言模型）** — 生成网页前，根据 `profile.json`（含 exploration/career/简历）+ **当前岗位描述 + 当轮对话**，从候选池选 1–3 个标签：
   - 优先级：`selected[]` > `custom[]` > 默认词表中用户**未选**但贴合本岗位的项
   - **禁止** 使用候选池外自造词；写入 `outputs_index[].filename_tags[]`
6. **网页产出** — 顶栏渲染 `exploration.summary` + `career` 摘要；正文打印友好样式
7. **收尾** — 更新 `outputs_index[]`（含每档 `optimization_level`）、`resume.last_optimization_levels[]`、`profile.meta.updated_at`；告知用户各档 HTML 路径；按档可选一句差异说明

---

## 与用户确认的关系

| 类型 | 是否需要用户逐步确认 |
|------|----------------------|
| 里程碑（确认按岗位描述优化） | **是**（进入本技能包前已完成） |
| 各 `work` 模块 | **否**，简历智能体自动推理-行动循环 |
| 最终是否满意 | 对话中可邀请用户查看网页，属反馈非闸门 |

---

## 流程图

```mermaid
flowchart TD
  In[确认优化 + 多选档位 + JD] --> Reuse{复用?}
  Reuse -->|跳过| End[complete works]
  Reuse -->|是/新建| W1[work: 模块1]
  W1 --> W2[work: 模块2]
  W2 --> Wn[work: ...]
  Wn --> HTML[work: 生成 HTML]
  HTML --> Idx[index + outputs_index]
```

---

## 延伸阅读

- 产品规格：`docs/prd/career-planning-agent-prd.md` §5.5、§5.6、§5.7（网页交付）、§4.1（智能体架构）
- 前置对齐：`career-jd-alignment` skill
