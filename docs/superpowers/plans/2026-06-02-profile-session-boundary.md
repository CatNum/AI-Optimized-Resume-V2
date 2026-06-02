# Profile 与 Session 数据边界重构 — 实施计划

> **For agentic workers:** 按 Task 执行；每完成一步更新 checkbox，并附验证证据。

**Goal:**  
将会话态数据从全局 `profile.json` 迁出到 `session state + session artifacts`，消除跨会话污染；同时保留 `outputs_index` 全局使用能力（含 `session_id` 可追溯与筛选）。

**Architecture:**  
`profile` 仅存长期用户画像；`sessions/:id/state.json` 存流程与 gate；`sessions/:id/artifacts.json` 存会话产物；`outputs_index` 作为全局特例保留在 `profile`。

**设计 SSOT:**  
`../specs/2026-06-02-profile-session-boundary-design.md` v0.1.0

**状态:**  
`Completed (PB0-PB8 代码与测试验收完成，发布观测项待上线执行)`

---

## Task PB0: 基线与防回归夹具

**Files:**
- `backend/tests/harness/test_chat_history_scope.py`（如需扩展）
- `backend/tests/harness/test_profile_memory.py`
- `backend/tests/api/test_rest.py`
- `backend/tests/e2e/test_jd_eval_chain.py`

- [x] 增加“跨 session 污染复现”基线测试（A 会话写 JD，B 会话不得自动复用 A 的 market/strategy 文本）。
- [x] 增加“outputs 全局可见 + 按 session 筛选”测试基线。
- [x] 记录基线运行结果（当前失败/通过点），作为后续验收对照。

**验证命令（建议）**
- `cd backend && pytest tests/harness/test_profile_memory.py -q`
- `cd backend && pytest tests/e2e/test_jd_eval_chain.py -q`

---

## Task PB1: Profile 写入白名单止血

**Files:**
- `backend/career_os/platform/store/profile.py`
- `backend/career_os/platform/tool/handlers/profile.py`（若有路径校验透传）

- [x] 在 `ProfileStore.patch()` 引入路径白名单/黑名单校验。
- [x] 禁止写入：`exploration.*`、`market.*`、`strategy.*`、`career.jd_override`。
- [x] 保留 `outputs_index` 特例写入（需校验记录包含 `session_id`）。
- [x] 为违规写入定义并返回统一错误码（如 `profile_path_forbidden`）。

**完成定义**
- 非法路径写入被拒绝且错误码稳定。
- 现有合法长期字段写入不受影响。

---

## Task PB2: 会话准入逻辑改为 session 真源

**Files:**
- `backend/career_os/harness/jd_prerequisites.py`
- `backend/career_os/harness/pipeline_phase_transition.py`
- `backend/career_os/harness/explore_intake.py`

- [x] `jd_prerequisites` 不再读取 `profile.exploration.completed_at`。
- [x] 改为仅读 session 侧（`state/explore_closure/gate`）判断 explore 是否完成。
- [x] 清理 `pipeline_phase_transition` 中对 `profile.exploration.completed_at` 的写入路径。

**完成定义**
- 新 session 在无本会话探索完成证据时，不得直接进入 JD 深链路。

---

## Task PB3: 引入 Session Artifacts 存储层

**Files:**
- `backend/career_os/platform/store/session.py`（扩展 artifacts API）
- `backend/career_os/platform/store/task.py`（若需联动元数据）
- `backend/career_os/agents/graphs/coordinator.py`

- [x] 新增 `sessions/:id/artifacts.json` 读写 API（get/patch/upsert）。
- [x] 约定 artifacts 结构：`exploration/market/opportunity/strategy/resume_outputs`。
- [x] coordinator 在 worker 完成后，将结构化产物写入当前 session artifacts。
- [x] `prior_results` 保留运行态最小必要字段，不再充当长期持久层。

**完成定义**
- 每个 session 可独立查看自身 artifacts，互不污染。

---

## Task PB4: profile_memory 读路径分流

**Files:**
- `backend/career_os/harness/profile_memory.py`
- `backend/career_os/agents/lc/coordinator_llm.py`

- [x] `resume/basic/intent/capability` 继续从全局 `profile` 读取。
- [x] `market/strategy/exploration` 改为从当前 session artifacts 读取。
- [x] 默认不读取历史会话 artifacts；仅在显式 `artifact_refs` 时注入。

**完成定义**
- B 会话不再自动读到 A 会话 `market/strategy` 结果。
- 用户问简历仍可命中全局 `resume`。

---

## Task PB5: explore_intake 会话化

**Files:**
- `backend/career_os/api/explore_intake.py`
- `backend/career_os/harness/explore_intake.py`

- [x] `exploration.intake*` 从 `profile` 迁移到 session state/artifacts。
- [x] intake 提交、状态查询、pending_fields 全部按当前 session 读取。
- [x] 保留与 `resume.source_text` 的长期资产同步（若产品仍要求）。

**完成定义**
- intake 状态随 session 变化，不跨会话继承。

---

## Task PB6: outputs_index 全局特例落地

**Files:**
- `backend/career_os/platform/tool/handlers/outputs.py`
- `backend/career_os/api/sessions.py`（`/outputs`）
- `backend/career_os/platform/store/profile.py`（结构校验）

- [x] `outputs_index` 使用 spec 推荐结构：`output_id/session_id/kind/path/status/...`。
- [x] upsert 规则：
  - 有 `output_id` 按主键更新；
  - 无 `output_id` 按 `(session_id, kind, path)` 去重合并。
- [x] `outputs` API 默认返回全局 `active`，支持 `session_id/kind/created_at` 过滤。
- [x] 删除改软删除（`status=deleted`），默认查询过滤。

**完成定义**
- 全局列表能力保留，且能按 session 精准追溯。

---

## Task PB7: 数据迁移与回滚

**Files:**
- `backend/scripts/migrate_profile_session_boundary.py`（新增）
- `backend/tests/scripts/test_migrate_profile_session_boundary.py`（新增）

- [x] 迁移脚本：将 profile 中会话态字段搬迁到对应 session state/artifacts。
- [x] 不可归属数据写入 `orphan_artifacts.json`。
- [x] 清理 profile 违规字段（保留 `outputs_index`）。
- [x] 提供回滚脚本或回滚步骤文档（恢复 profile 备份 + 回撤 artifacts）。

**完成定义**
- 迁移可重复执行（幂等）。
- 回滚演练通过。

---

## Task PB8: 验收与发布

**Files:**
- `docs/superpowers/specs/2026-06-02-profile-session-boundary-design.md`（状态回写）
- `docs/architecture/10-会话闸门与state.md`（必要增量）

- [x] 单测/集成/e2e 全量通过。
- [x] 验收标准逐条对照打勾（spec §8）。
- [ ] 发布观察项上线：违规 profile 写入计数、跨 session 污染告警、outputs 去重命中率。
- [x] 将 spec 状态从 `Proposed` 更新为 `Implemented`（或 `Partially Implemented`）。

**建议命令**
- `cd backend && pytest -q`

---

## 并行执行建议

- PB1（止血）与 PB0（基线）可并行。
- PB3（artifacts 存储层）与 PB6（outputs 全局特例）可并行。
- PB4/PB5 依赖 PB3 完成后再做。
- PB7 在 PB4/PB5/PB6 稳定后执行。

---

## 风险与应对

- [ ] **风险:** 老逻辑隐式依赖 `profile.exploration`  
      **应对:** 双读过渡开关 + 渐进切流（先读 session，兜底读旧字段并告警）。
- [ ] **风险:** 历史数据归属不完整  
      **应对:** `orphan_artifacts` 落盘 + 人工修复流程。
- [ ] **风险:** 全局 outputs 膨胀  
      **应对:** 分页、筛选、定期去重压缩。

---

## 完成信号（Definition of Done）

- [x] 新会话不再复用旧会话 market/strategy/opportunity 语义。
- [x] `profile` 中仅保留长期字段 + 全局 `outputs_index`。
- [x] `outputs_index` 具备 `session_id` 追溯能力与筛选能力。
- [x] 迁移脚本与回滚脚本都经测试验证可执行。
- [x] 相关文档与测试同步更新。

