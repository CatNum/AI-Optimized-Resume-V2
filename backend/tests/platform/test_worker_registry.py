from pathlib import Path

import pytest

from career_os.platform.skill.registry import SkillRegistry
from career_os.platform.worker.registry import WorkerRegistry


@pytest.fixture
def repo_root() -> Path:
    """repo_root（repo root）的函数说明。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    return Path(__file__).resolve().parents[3]


def test_worker_registry_loads_seven_workers(repo_root: Path):
    """test_worker_registry_loads_seven_workers（测试 worker registry loads seven workers）的函数说明。

    repo_root（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    registry = WorkerRegistry(registry_path=repo_root / "config" / "workers.registry.json")
    assert len(registry.list_worker_ids()) == 7


def test_get_worker_index_returns_metadata(repo_root: Path):
    """test_get_worker_index_returns_metadata（测试 get worker index returns metadata）的函数说明。

    repo_root（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    registry = WorkerRegistry(registry_path=repo_root / "config" / "workers.registry.json")
    index = registry.get_worker_index()
    assert len(index) == 7
    assert index[0]["worker_id"] == "identity"
    assert "when_to_use" in index[0]
    assert "outputs" in index[0]


def test_load_skill_exploration_first_allowed_workers(repo_root: Path):
    """test_load_skill_exploration_first_allowed_workers（测试 load skill exploration first allowed workers）的函数说明。

    repo_root（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    registry = SkillRegistry(skills_dir=repo_root / ".agent" / "skills")
    bundle = registry.load_skill(
        "career-inner-exploration",
        mode="exploration_first",
        worker_id="identity",
    )
    assert hasattr(bundle, "body")
    assert bundle.name == "career-inner-exploration"
    assert "identity" in bundle.allowed_workers


def test_load_skill_rejects_wrong_worker(repo_root: Path):
    """test_load_skill_rejects_wrong_worker（测试 load skill rejects wrong worker）的函数说明。

    repo_root（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    registry = SkillRegistry(skills_dir=repo_root / ".agent" / "skills")
    err = registry.load_skill(
        "career-inner-exploration",
        mode="exploration_first",
        worker_id="capability",
    )
    assert err.code == "skill_worker_rejected"
