# Eval Case 清单（对齐 architecture 12 §3.2）

> 审计日期：2026-05-31 · 命令：`cd backend && uv run pytest tests/ -q`

## 汇总

| 指标 | 数值 |
|------|------|
| pytest 总 case | **94** |
| `-m not llm` 通过 | **88**（6 条 `@pytest.mark.llm` deselect） |
| `-m llm` 真推理 | **6**（market/opportunity/strategy/resume + golden） |
| 分类覆盖（去重后） | **≥23**（见下表，允许跨层） |

## 分类分布

| 类别 | 要求 | 实际 | 代表 case |
|------|:----:|:----:|-----------|
| 闸门 | ≥5 | **8** | `test_match_gate_intent`×3、`test_delegate_rules` resume gate、`test_strategy_asset`×2、`test_explore_closure` E2 |
| 派工链 | ≥5 | **7** | `test_jd_eval_chain`×2、`test_coordinator_c3`×2、`test_explore_closure_e2e`、`test_chat_jd_gate_chain` |
| Tool / 存储 | ≥5 | **12** | 白名单×4、Session M1/R2×2、Task×4、Output×1、Trace×2 |
| 三档 HTML | ≥5 | **5** | `test_resume_levels`、`test_golden_path`、`test_asset_register`、`test_chat_jd_gate_chain`、`test_eval_html_delivery_contract` |
| 降级 | ≥3 | **4** | `test_browser_fetch_degrade`×2、`test_orchestrator` 409/410 |

## 分层

| 层 | 目录 | case 数 | LLM |
|----|------|:-------:|-----|
| L1 Component | `tests/harness/`、`tests/store/`、`tests/agents/` 等 | ~60 | 否（react_mocks） |
| L2 Trajectory | `tests/e2e/`、`tests/agents/test_coordinator_c3.py` | ~10 | react_mocks |
| L3 E2E | `tests/api/test_rest.py`、`tests/eval/` | ~8 | golden + `-m llm` |

## Worker ReAct 状态

| Worker | ReAct | L1 mock | `-m llm` eval |
|--------|:-----:|:-------:|:-------------:|
| market | ✅ | react_mocks | ✅ |
| opportunity | ✅ | react_mocks | ✅ |
| strategy | ✅ | react_mocks | ✅ |
| resume | ✅ | react_mocks | ✅ |
| identity | ✅ | react_mocks | — |
| capability | ✅ | react_mocks | — |
| asset | ✅ | react_mocks | — |

## 已知限制

- **L1 无 Key**：全 Worker 走 `react_mocks` 确定性替身，非真推理。
- **真 LLM eval**：配置 `LLM_API_KEY` 后 `pytest tests/eval/ -m llm -v`。

自动化校验：`tests/eval/test_eval_coverage.py`
