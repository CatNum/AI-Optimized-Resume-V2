from career_os.harness.explore_depth import (
    can_offer_explore_complete,
    should_run_depth_judge,
)


def test_should_run_depth_judge_rhythm():
    """验证应当运行深度判断节奏的处理符合预期。"""
    assert should_run_depth_judge("personal", 6) is True
    assert should_run_depth_judge("personal", 5) is False
    assert should_run_depth_judge("personal", 8) is True


def test_can_offer_explore_complete_requires_closure():
    """验证可以提供探索完成要求收口。"""
    profile = {
        "exploration": {
            "intake": {"submitted_at": "2026-01-01T00:00:00Z"},
            "depth": {
                "sufficient": {"personal": True, "capability": True},
            },
        },
        "resume": {"source_text": "resume"},
        "basic": {"years_of_experience": "3"},
        "intent": {
            "current_salary": "20k",
            "target_salary": "30k",
            "target_role": "后端",
        },
    }
    session_state = {
        "explore_closure": {
            "required_workers": ["identity", "capability"],
            "worker_done": {"identity": True, "capability": True},
        }
    }
    ok, diag = can_offer_explore_complete(profile, session_state)
    assert ok is True
    assert diag["hard_pass"] is True
