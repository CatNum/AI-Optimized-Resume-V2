import importlib

import pytest

from career_os.agents.graphs.workers.registry import build_harness_worker_runner
from career_os.agents.lc.client import llm_enabled
from career_os.harness.executor import Harness


@pytest.fixture
def harness(tmp_path, monkeypatch):
    """构造测试用 Harness。"""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    import career_os.config as config_mod
    import career_os.platform.store.profile as profile_mod

    importlib.reload(config_mod)
    importlib.reload(profile_mod)
    return Harness()


@pytest.mark.llm
def test_strategy_jd_emits_optimize_gate(harness):
    """验证 strategy Worker 会针对 JD 输出优化 gate。"""
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
    """验证 resume Worker 会生成 HTML 交付物。"""
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
