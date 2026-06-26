import importlib

import pytest

from career_os.agents.graphs.workers.registry import build_harness_worker_runner
from career_os.agents.lc.client import llm_enabled
from career_os.harness.executor import Harness


@pytest.fixture
def harness(tmp_path, monkeypatch):
    """harness（harness）的函数说明。

    tmp_path（参数）、monkeypatch（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    import career_os.config as config_mod
    import career_os.platform.store.profile as profile_mod

    importlib.reload(config_mod)
    importlib.reload(profile_mod)
    return Harness()


@pytest.mark.llm
def test_strategy_jd_emits_optimize_gate(harness):
    """test_strategy_jd_emits_optimize_gate（测试 strategy jd emits optimize gate）的函数说明。

    harness（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    if not llm_enabled():
        pytest.skip("LLM_API_KEY not configured")

    runner = build_harness_worker_runner(harness, use_react_mocks=False)
    result = runner(
        "strategy",
        "制定 JD 投递策略",
        {
            "session_id": "s1",
            "list_type": "jd",
            "prior_results": {"opportunity": {"recommendation": "recommended"}},
            "gates": {"flags": {}},
        },
        {"capability_bundle": {"skill_index": [], "tool_index": []}, "requires_optimize_gate": True},
    )
    assert result["status"] == "completed"
    gate = (result["structured_output"] or {}).get("gate_prompt") or {}
    assert gate.get("name") == "optimize_confirm"


@pytest.mark.llm
def test_resume_generates_html_deliveries(harness, tmp_path):
    """test_resume_generates_html_deliveries（测试 resume generates html deliveries）的函数说明。

    harness（参数）、tmp_path（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    if not llm_enabled():
        pytest.skip("LLM_API_KEY not configured")

    runner = build_harness_worker_runner(harness, use_react_mocks=False)
    result = runner(
        "resume",
        "按标准档优化简历",
        {
            "session_id": "s1",
            "gates": {"flags": {"optimize_confirmed": True}},
            "prior_results": {},
        },
        {
            "selected_optimization_levels": ["标准"],
            "capability_bundle": {"skill_index": [], "tool_index": []},
        },
    )
    assert result["status"] == "completed"
    deliveries = result["structured_output"].get("html_deliveries") or []
    assert len(deliveries) >= 1
