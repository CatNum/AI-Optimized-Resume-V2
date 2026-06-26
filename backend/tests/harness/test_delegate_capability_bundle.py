import pytest

from career_os.harness.executor import Harness


@pytest.fixture
def harness(tmp_path, monkeypatch):
    """harness（harness）的函数说明。

    tmp_path（参数）、monkeypatch（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    return Harness()


def test_delegate_includes_capability_bundle(harness, jd_ready_profile):
    """test_delegate_includes_capability_bundle（测试 delegate includes capability bundle）的函数说明。

    harness（参数）、jd_ready_profile（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    _ = jd_ready_profile
    result = harness.delegate_worker(
        "coordinator",
        "strategy",
        "制定 JD 投递策略",
        {
            "session_id": "s1",
            "prior_results": {},
            "gates": {"flags": {}},
            "list_type": "pipeline",
            "explore_gate_confirmed": True,
            "explore_closure": {"completed": True},
        },
        context={"list_type": "jd"},
        session_id="s1",
    )
    assert not hasattr(result, "code")
    ctx = result["context"]
    assert "capability_bundle" in ctx
    assert "skill_index" in ctx["capability_bundle"]
    assert "tool_index" in ctx["capability_bundle"]
    skill_names = [s["name"] for s in ctx["capability_bundle"]["skill_index"]]
    assert "career-jd-alignment" in skill_names
