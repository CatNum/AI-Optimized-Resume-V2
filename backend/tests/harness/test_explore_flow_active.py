from career_os.harness.explore_closure import init_explore_closure
from career_os.harness.session_activity import explore_flow_active


def test_explore_flow_inactive_when_gate_confirmed():
    """test_explore_flow_inactive_when_gate_confirmed（测试 explore flow inactive when gate confirmed）的函数说明。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    session_state = {
        "list_type": "pipeline",
        "explore_gate_confirmed": True,
        "explore_closure": init_explore_closure(),
        "gates": {"flags": {}},
    }
    assert explore_flow_active(session_state) is False


def test_explore_flow_inactive_when_repeat_declined():
    """test_explore_flow_inactive_when_repeat_declined（测试 explore flow inactive when repeat declined）的函数说明。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    session_state = {
        "list_type": "pipeline",
        "explore_closure": init_explore_closure(),
        "gates": {"flags": {"explore_repeat_declined": True}},
    }
    assert explore_flow_active(session_state) is False


def test_explore_flow_active_when_closure_incomplete():
    """test_explore_flow_active_when_closure_incomplete（测试 explore flow active when closure incomplete）的函数说明。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    session_state = {
        "list_type": "pipeline",
        "explore_closure": init_explore_closure(),
        "gates": {"flags": {}},
    }
    assert explore_flow_active(session_state) is True
