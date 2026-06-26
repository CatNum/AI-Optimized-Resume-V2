import pytest

from career_os.harness.explore_closure import (
    PHASE_IN_PROGRESS,
    PHASE_SEGMENT_COMPLETE,
    can_set_explore_gate_pending,
    init_explore_closure,
    is_closure_ready,
    mark_worker_done,
    plan_explore_worker_dispatch,
    validate_worker_structured_output,
)


def test_default_required_workers():
    """test_default_required_workers（测试 default required workers）的函数说明。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    state = init_explore_closure()
    assert state["required_workers"] == ["identity", "capability"]
    assert state["worker_done"]["identity"] is False
    assert state["worker_done"]["capability"] is False


def test_single_worker_other_done():
    """test_single_worker_other_done（测试 single worker other done）的函数说明。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    state = init_explore_closure(required_workers=["identity"])
    assert state["worker_done"]["capability"] is True
    state = mark_worker_done(
        state,
        "identity",
        structured_output={"phase_status": PHASE_SEGMENT_COMPLETE},
    )
    assert is_closure_ready(state)


def test_in_progress_does_not_mark_worker_done():
    """test_in_progress_does_not_mark_worker_done（测试 in progress does not mark worker done）的函数说明。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    state = init_explore_closure()
    state = mark_worker_done(
        state,
        "identity",
        structured_output={
            "user_visible_summary": "继续问",
            "exploration_draft": {},
            "phase_status": PHASE_IN_PROGRESS,
        },
    )
    assert state["worker_done"]["identity"] is False
    assert not can_set_explore_gate_pending(state)


def test_both_done_allows_gate_pending():
    """test_both_done_allows_gate_pending（测试 both done allows gate pending）的函数说明。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    state = init_explore_closure()
    state = mark_worker_done(
        state,
        "identity",
        structured_output={"phase_status": PHASE_SEGMENT_COMPLETE},
    )
    assert not can_set_explore_gate_pending(state)
    state = mark_worker_done(
        state,
        "capability",
        structured_output={"phase_status": PHASE_SEGMENT_COMPLETE},
    )
    assert can_set_explore_gate_pending(state)


def test_completed_explore_does_not_reopen_gate():
    """test_completed_explore_does_not_reopen_gate（测试 completed explore does not reopen gate）的函数说明。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    state = init_explore_closure()
    state = mark_worker_done(
        state,
        "identity",
        structured_output={"phase_status": PHASE_SEGMENT_COMPLETE},
    )
    state = mark_worker_done(
        state,
        "capability",
        structured_output={"phase_status": PHASE_SEGMENT_COMPLETE},
    )
    state["completed"] = True
    assert not can_set_explore_gate_pending(state)


def test_plan_explore_dispatch_one_worker_at_a_time():
    """test_plan_explore_dispatch_one_worker_at_a_time（测试 plan explore dispatch one worker at a time）的函数说明。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    session_state = {"explore_closure": init_explore_closure()}
    planned = plan_explore_worker_dispatch(["identity", "capability"], session_state)
    assert planned == ["identity"]


def test_identity_explore_gate_prompt_fails_validation():
    """test_identity_explore_gate_prompt_fails_validation（测试 identity explore gate prompt fails validation）的函数说明。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    err = validate_worker_structured_output(
        "identity",
        {"gate_prompt": {"name": "explore_complete", "prompt": "确认？"}},
    )
    assert err is not None
