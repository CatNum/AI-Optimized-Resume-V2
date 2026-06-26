import importlib

from career_os.harness.pipeline_routing import enforce_pipeline_phase_rules


def test_enforce_uses_disk_phase_for_jd_workers_when_gate_confirmed():
    """test_enforce_uses_disk_phase_for_jd_workers_when_gate_confirmed（测试 enforce uses disk phase for jd workers when gate confirmed）的函数说明。

    该函数用于验证对应业务场景的行为是否符合预期。"""
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


def test_enforce_blocks_inferred_leave_explore_without_gate(tmp_path, monkeypatch):
    """test_enforce_blocks_inferred_leave_explore_without_gate（测试 enforce blocks inferred leave explore without gate）的函数说明。

    tmp_path（参数）、monkeypatch（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import career_os.config as config_mod
    import career_os.platform.store.profile as profile_mod

    importlib.reload(config_mod)
    importlib.reload(profile_mod)
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
