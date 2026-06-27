from career_os.harness.explore_closure import init_explore_closure
from career_os.harness.session_activity import explore_flow_active


def test_explore_flow_inactive_when_gate_confirmed():
    """验证 explore flow inactive when gate confirmed 场景。"""
    session_state = {
        "list_type": "pipeline",
        "explore_gate_confirmed": True,
        "explore_closure": init_explore_closure(),
        "gates": {"flags": {}},
    }
    assert explore_flow_active(session_state) is False


def test_explore_flow_inactive_when_repeat_declined():
    """验证 explore flow inactive when repeat declined 场景。"""
    session_state = {
        "list_type": "pipeline",
        "explore_closure": init_explore_closure(),
        "gates": {"flags": {"explore_repeat_declined": True}},
    }
    assert explore_flow_active(session_state) is False


def test_explore_flow_active_when_closure_incomplete():
    """验证 explore flow active when closure incomplete 场景。"""
    session_state = {
        "list_type": "pipeline",
        "explore_closure": init_explore_closure(),
        "gates": {"flags": {}},
    }
    assert explore_flow_active(session_state) is True
