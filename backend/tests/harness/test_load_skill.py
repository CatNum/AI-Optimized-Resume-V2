import pytest

from career_os.harness.executor import Harness


@pytest.fixture
def harness(tmp_path, monkeypatch):
    """构造测试用 Harness。"""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    return Harness()


def test_load_skill_allowed_worker(harness):
    """验证 load skill allowed worker 场景。"""
    result = harness.execute_tool(
        "identity",
        "load_skill",
        {"name": "career-inner-exploration", "mode": "exploration_first"},
    )
    assert not hasattr(result, "code")
    assert "body" in result
    assert len(result["body"]) > 100


def test_load_skill_rejects_wrong_worker(harness):
    """验证 load skill rejects wrong worker 场景。"""
    result = harness.execute_tool(
        "market",
        "load_skill",
        {"name": "career-inner-exploration", "mode": "exploration_first"},
    )
    assert result.code == "skill_not_allowed"


def test_list_skills_for_worker(harness):
    """验证 list skills for worker 场景。"""
    result = harness.execute_tool("strategy", "list_skills", {})
    assert "skills" in result
    names = [s["name"] for s in result["skills"]]
    assert "career-jd-alignment" in names
