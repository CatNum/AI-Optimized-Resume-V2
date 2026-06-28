from career_os.harness.explore_closure import explore_continuation_analyze, init_explore_closure


def _base_session() -> dict:
    """构造测试环境和基础状态。"""
    return {
        "list_type": "pipeline",
        "explore_closure": init_explore_closure(),
        "gates": {"flags": {}},
    }


def test_continuation_none_when_gate_confirmed():
    """验证 gate 已确认时，续跑不触发的处理符合预期。"""
    state = {**_base_session(), "explore_gate_confirmed": True}
    assert explore_continuation_analyze(state) is None


def test_continuation_none_when_repeat_declined():
    """验证重复探索已拒绝时，续跑不触发的处理符合预期。"""
    state = _base_session()
    state["gates"] = {"flags": {"explore_repeat_declined": True}}
    assert explore_continuation_analyze(state) is None


def test_continuation_none_when_closure_completed():
    """验证收口已完成时，续跑不触发的处理符合预期。"""
    closure = init_explore_closure()
    closure["completed"] = True
    state = {**_base_session(), "explore_closure": closure}
    assert explore_continuation_analyze(state) is None


def test_continuation_dispatches_when_incomplete():
    """验证未完成时，续跑分派的处理符合预期。"""
    state = _base_session()
    result = explore_continuation_analyze(state)
    assert result is not None
    assert result["workers"] == ["identity"]
