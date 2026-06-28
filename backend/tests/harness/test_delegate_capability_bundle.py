import pytest

from career_os.harness.executor import Harness


@pytest.fixture
def harness(tmp_path, monkeypatch):
    """构造测试用 Harness。"""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    return Harness()


def test_delegate_includes_capability_bundle(harness, jd_ready_profile):
    """验证委派会包含 capability_bundle。"""
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
