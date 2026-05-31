from career_os.agents.graphs.workers.base import run_worker_emit
from career_os.agents.schemas.workers import validate_structured_output


def test_opportunity_missing_recommendation_fails():
    validated, error = validate_structured_output(
        "opportunity",
        {"user_visible_summary": "评估完成"},
    )
    assert validated is None
    assert error is not None


def test_identity_explore_gate_prompt_fails():
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


def test_opportunity_valid_output_passes():
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
