from career_os.harness.pipeline_routing import enforce_pipeline_phase_rules


def test_enforce_uses_disk_phase_for_jd_workers_when_gate_confirmed():
    session_state = {
        "list_type": "pipeline",
        "explore_gate_confirmed": True,
        "gates": {"flags": {"explore_gate_confirmed": True}},
    }
    result = enforce_pipeline_phase_rules(
        {"workers": ["market"], "pipeline_phase": "market"},
        session_state,
        "分析市场",
    )
    assert "market" in result.get("workers", [])


def test_enforce_blocks_inferred_leave_explore_without_gate():
    session_state = {
        "list_type": "pipeline",
        "gates": {"flags": {}},
    }
    result = enforce_pipeline_phase_rules(
        {"workers": ["market"], "pipeline_phase": "market"},
        session_state,
        "分析市场",
    )
    assert result.get("workers") == []
    assert result.get("explore_gate_required") is True
