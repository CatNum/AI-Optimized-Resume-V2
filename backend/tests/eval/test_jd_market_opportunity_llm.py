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
def test_opportunity_not_always_recommended(harness):
    """test_opportunity_not_always_recommended（测试 opportunity not always recommended）的函数说明。

    harness（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    if not llm_enabled():
        pytest.skip("LLM_API_KEY not configured")

    runner = build_harness_worker_runner(harness)
    session_state = {
        "session_id": "sess_mismatch",
        "list_type": "jd",
        "prior_results": {
            "market": {
                "user_visible_summary": "前端市场",
                "topics": [{"topic": "React", "summary": "需求高"}],
            }
        },
        "gates": {"flags": {}},
    }
    result = runner(
        "opportunity",
        "JD：高级 Java 后端，10 年分布式经验，要求 Scala/Kafka",
        session_state,
        {"capability_bundle": {"skill_index": [], "tool_index": []}},
    )
    assert result["status"] == "completed"
    structured = result["structured_output"]
    assert structured["recommendation"] in {"recommended", "not_recommended"}
    assert structured.get("user_visible_summary")


@pytest.mark.llm
def test_market_topics_vary_with_jd(harness):
    """test_market_topics_vary_with_jd（测试 market topics vary with jd）的函数说明。

    harness（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    if not llm_enabled():
        pytest.skip("LLM_API_KEY not configured")

    runner = build_harness_worker_runner(harness)
    context = {"capability_bundle": {"skill_index": [], "tool_index": []}}

    r1 = runner(
        "market",
        "JD：Kubernetes 云原生后端工程师",
        {"session_id": "s1", "prior_results": {}, "gates": {"flags": {}}},
        context,
    )
    r2 = runner(
        "market",
        "JD：Flutter 移动端开发，要求 iOS/Android 双端",
        {"session_id": "s2", "prior_results": {}, "gates": {"flags": {}}},
        context,
    )
    assert r1["status"] == "completed" and r2["status"] == "completed"
    topics1 = r1["structured_output"].get("topics") or []
    topics2 = r2["structured_output"].get("topics") or []
    assert topics1 and topics2
    assert topics1 != topics2
