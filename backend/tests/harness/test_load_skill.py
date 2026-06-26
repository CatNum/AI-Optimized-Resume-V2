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


def test_load_skill_allowed_worker(harness):
    """test_load_skill_allowed_worker（测试 load skill allowed worker）的函数说明。

    harness（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    result = harness.execute_tool(
        "identity",
        "load_skill",
        {"name": "career-inner-exploration", "mode": "exploration_first"},
    )
    assert not hasattr(result, "code")
    assert "body" in result
    assert len(result["body"]) > 100


def test_load_skill_rejects_wrong_worker(harness):
    """test_load_skill_rejects_wrong_worker（测试 load skill rejects wrong worker）的函数说明。

    harness（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    result = harness.execute_tool(
        "market",
        "load_skill",
        {"name": "career-inner-exploration", "mode": "exploration_first"},
    )
    assert result.code == "skill_not_allowed"


def test_list_skills_for_worker(harness):
    """test_list_skills_for_worker（测试 list skills for worker）的函数说明。

    harness（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    result = harness.execute_tool("strategy", "list_skills", {})
    assert "skills" in result
    names = [s["name"] for s in result["skills"]]
    assert "career-jd-alignment" in names
