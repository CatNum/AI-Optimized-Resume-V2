import pytest

from career_os.harness.explore_closure import (
    can_set_explore_gate_pending,
    init_explore_closure,
    is_closure_ready,
    mark_worker_done,
    validate_worker_structured_output,
)


def test_default_required_workers():
    state = init_explore_closure()
    assert state["required_workers"] == ["identity", "capability"]
    assert state["worker_done"]["identity"] is False
    assert state["worker_done"]["capability"] is False


def test_single_worker_other_done():
    state = init_explore_closure(required_workers=["identity"])
    assert state["worker_done"]["capability"] is True
    state = mark_worker_done(state, "identity")
    assert is_closure_ready(state)


def test_both_done_allows_gate_pending():
    state = init_explore_closure()
    state = mark_worker_done(state, "identity")
    assert not can_set_explore_gate_pending(state)
    state = mark_worker_done(state, "capability")
    assert can_set_explore_gate_pending(state)


def test_identity_explore_gate_prompt_fails_validation():
    err = validate_worker_structured_output(
        "identity",
        {"gate_prompt": {"name": "explore_complete", "prompt": "确认？"}},
    )
    assert err is not None
