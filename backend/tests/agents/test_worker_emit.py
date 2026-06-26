from career_os.agents.graphs.workers.base import run_worker_emit
from career_os.agents.schemas.workers import validate_structured_output


def test_opportunity_missing_recommendation_fails():
    """test_opportunity_missing_recommendation_fails（测试 opportunity missing recommendation fails）的函数说明。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    validated, error = validate_structured_output(
        "opportunity",
        {"user_visible_summary": "评估完成"},
    )
    assert validated is None
    assert error is not None


def test_identity_explore_gate_prompt_fails():
    """test_identity_explore_gate_prompt_fails（测试 identity explore gate prompt fails）的函数说明。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    validated, error = validate_structured_output(
        "identity",
        {
            "user_visible_summary": "初探小结",
            "exploration_draft": {"summary": "草案"},
            "gate_prompt": {"name": "explore_complete", "prompt": "确认完成初探？"},
        },
    )
    assert validated is None
    assert error is not None


def test_strategy_nested_gate_prompt_normalizes():
    """test_strategy_nested_gate_prompt_normalizes（测试 strategy nested gate prompt normalizes）的函数说明。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    validated, error = validate_structured_output(
        "strategy",
        {
            "user_visible_summary": "策略完成",
            "path_options": [{"id": "a", "label": "稳健"}],
            "three_horizons": {"apply_narrative": "先投递"},
            "gate_prompt": {
                "optimize_confirm": {
                    "type": "confirm",
                    "prompt": "是否确认按该 JD 优化简历？",
                }
            },
        },
    )
    assert error is None
    assert validated["gate_prompt"]["name"] == "optimize_confirm"
    assert "优化简历" in validated["gate_prompt"]["prompt"]


def test_opportunity_gate_prompt_string_value_normalizes():
    """test_opportunity_gate_prompt_string_value_normalizes（测试 opportunity gate prompt string value normalizes）的函数说明。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    validated, error = validate_structured_output(
        "opportunity",
        {
            "recommendation": "not_recommended",
            "user_visible_summary": "不匹配",
            "gate_prompt": {
                "jd_continue_despite_not_recommended": "是否仍要继续？",
            },
        },
    )
    assert error is None
    assert validated["gate_prompt"]["name"] == "jd_continue_despite_not_recommended"


def test_opportunity_valid_output_passes():
    """test_opportunity_valid_output_passes（测试 opportunity valid output passes）的函数说明。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    validated, error = validate_structured_output(
        "opportunity",
        {
            "recommendation": "recommended",
            "user_visible_summary": "推荐投递",
            "jd_fingerprint": "abc123",
        },
    )
    assert error is None
    assert validated["recommendation"] == "recommended"


def test_worker_emit_marks_failed_on_invalid_output():
    """test_worker_emit_marks_failed_on_invalid_output（测试 worker emit marks failed on invalid output）的函数说明。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    state = run_worker_emit(
        {
            "worker_id": "identity",
            "goal": "explore",
            "context": {},
            "messages": [],
            "structured_output": {},
            "status": "pending",
        },
        raw_output={
            "user_visible_summary": "x",
            "exploration_draft": {},
            "gate_prompt": {"name": "explore_complete", "prompt": "?"},
        },
    )
    assert state["status"] == "failed"
    assert state["error"]
