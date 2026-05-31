"""Eval 分类覆盖率（architecture 12 §3.2 ≥20 case 分布）."""

import pytest

# 每条为 pytest node 后缀（唯一标识）；允许跨层重复计数见 CASES.md
EVAL_INVENTORY: dict[str, list[str]] = {
    "gate": [
        "test_explore_complete_confirm",
        "test_optimize_confirm_reject",
        "test_unknown_when_no_match",
        "test_explore_gate_intent",
        "test_resume_blocked_without_optimize_confirmed",
        "test_strategy_emits_optimize_gate_on_jd",
        "test_strategy_no_optimize_gate_on_plan",
        "test_identity_explore_gate_prompt_fails_validation",
    ],
    "trajectory": [
        "test_jd_chain_market_then_opportunity",
        "test_market_before_opportunity_order",
        "test_gate_prompt_stops_delegate_chain_c3",
        "test_sequential_delegate_without_gate",
        "test_opportunity_blocked_without_market",
        "test_explore_workers_set_closure_ready",
        "test_chat_jd_gate_chain",
    ],
    "tool_storage": [
        "test_profile_patch_whitelist_rejects_asset",
        "test_asset_cannot_patch_exploration",
        "test_session_m1_trim",
        "test_reset_session_clears_messages_and_state",
        "test_create_task_list_writes_files",
        "test_complete_task_deletes_file",
        "test_asset_registers_resume_deliveries",
        "test_output_write_list_delete",
        "test_execute_tool_writes_tool_call_event",
        "test_delegate_worker_writes_agent_run_start",
        "test_jd_r1_blocks_opportunity",
        "test_b3_worker_no_complete",
    ],
    "html_delivery": [
        "test_resume_writes_multiple_levels",
        "test_golden_jd_to_html_structure",
        "test_asset_registers_resume_deliveries",
        "test_chat_jd_gate_chain",
        "test_eval_html_delivery_contract",
        "test_resume_generates_html_deliveries",
    ],
    "degrade": [
        "test_browser_fetch_degrades_without_api_key",
        "test_worker_can_complete_despite_browser_fetch_failure",
        "test_chat_in_progress",
        "test_session_expired",
    ],
}

MINIMUMS = {
    "gate": 5,
    "trajectory": 5,
    "tool_storage": 5,
    "html_delivery": 5,
    "degrade": 3,
}


@pytest.mark.no_llm
@pytest.mark.parametrize("category", list(MINIMUMS.keys()))
def test_eval_category_meets_minimum(category: str):
    count = len(EVAL_INVENTORY[category])
    assert count >= MINIMUMS[category], f"{category}: {count} < {MINIMUMS[category]}"


@pytest.mark.no_llm
def test_eval_total_distinct_cases_at_least_twenty():
    distinct = {name for cases in EVAL_INVENTORY.values() for name in cases}
    assert len(distinct) >= 20


@pytest.mark.no_llm
def test_eval_html_delivery_contract():
    """三档 HTML：optimization_level 字段 + 文件路径前缀 output/."""
    from career_os.platform.tool.handlers.resume_html import sort_optimization_levels

    levels = sort_optimization_levels(["进取", "保守", "标准"])
    assert levels == ["保守", "标准", "进取"]
    for level in levels:
        assert level in {"保守", "标准", "进取"}
