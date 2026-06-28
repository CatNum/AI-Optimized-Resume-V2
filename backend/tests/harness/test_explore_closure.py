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
    """验证默认必需 Worker 列表的处理符合预期。"""
    state = init_explore_closure()
    assert state["required_workers"] == ["identity", "capability"]
    assert state["worker_done"]["identity"] is False
    assert state["worker_done"]["capability"] is False


def test_single_worker_other_done():
    """验证单个 Worker 其他完成的处理符合预期。"""
    state = init_explore_closure(required_workers=["identity"])
    assert state["worker_done"]["capability"] is True
    state = mark_worker_done(
        state,
        "identity",
        structured_output={"phase_status": PHASE_SEGMENT_COMPLETE},
    )
    assert is_closure_ready(state)


def test_in_progress_does_not_mark_worker_done():
    """验证在进行中不会标记 Worker 完成。"""
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
    """验证两个完成会允许 gate 待处理项。"""
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
    """验证已完成 explore 不会重新打开 gate。"""
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
    """验证计划型 explore 会一次只分派一个 Worker。"""
    session_state = {"explore_closure": init_explore_closure()}
    planned = plan_explore_worker_dispatch(["identity", "capability"], session_state)
    assert planned == ["identity"]


def test_identity_explore_gate_prompt_fails_validation():
    """验证 identity Worker 探索 gate 提示失败校验的处理符合预期。"""
    err = validate_worker_structured_output(
        "identity",
        {"gate_prompt": {"name": "explore_complete", "prompt": "确认？"}},
    )
    assert err is not None
