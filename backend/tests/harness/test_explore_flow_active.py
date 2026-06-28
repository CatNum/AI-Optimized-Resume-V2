from career_os.harness.explore_closure import init_explore_closure
from career_os.harness.session_activity import explore_flow_active


def test_explore_flow_inactive_when_gate_confirmed():
    """验证 gate 已确认时，explore pipeline 未激活的处理符合预期。"""
    session_state = {
        "list_type": "pipeline",
        "explore_gate_confirmed": True,
        "explore_closure": init_explore_closure(),
        "gates": {"flags": {}},
    }
    assert explore_flow_active(session_state) is False


def test_explore_flow_inactive_when_repeat_declined():
    """验证重复探索已拒绝时，explore pipeline 未激活的处理符合预期。"""
    session_state = {
        "list_type": "pipeline",
        "explore_closure": init_explore_closure(),
        "gates": {"flags": {"explore_repeat_declined": True}},
    }
    assert explore_flow_active(session_state) is False


def test_explore_flow_active_when_closure_incomplete():
    """验证收口未完成时，explore pipeline 活跃的处理符合预期。"""
    session_state = {
        "list_type": "pipeline",
        "explore_closure": init_explore_closure(),
        "gates": {"flags": {}},
    }
    assert explore_flow_active(session_state) is True
