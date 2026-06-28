from pathlib import Path

import pytest

from career_os.platform.skill.registry import SkillRegistry
from career_os.platform.worker.registry import WorkerRegistry


@pytest.fixture
def repo_root() -> Path:
    """构造测试辅助数据。"""
    return Path(__file__).resolve().parents[3]


def test_worker_registry_loads_seven_workers(repo_root: Path):
    """验证 Worker 注册表会加载七个 Worker 列表。"""
    registry = WorkerRegistry(registry_path=repo_root / "config" / "workers.registry.json")
    assert len(registry.list_worker_ids()) == 7


def test_get_worker_index_returns_metadata(repo_root: Path):
    """验证获取 Worker 索引会返回元数据。"""
    registry = WorkerRegistry(registry_path=repo_root / "config" / "workers.registry.json")
    index = registry.get_worker_index()
    assert len(index) == 7
    assert index[0]["worker_id"] == "identity"
    assert "when_to_use" in index[0]
    assert "outputs" in index[0]


def test_load_skill_exploration_first_allowed_workers(repo_root: Path):
    """验证 Skill 加载 exploration 首次允许 Worker 列表的处理符合预期。"""
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
    """验证 Skill 加载会拒绝错误 Worker。"""
    registry = SkillRegistry(skills_dir=repo_root / ".agent" / "skills")
    err = registry.load_skill(
        "career-inner-exploration",
        mode="exploration_first",
        worker_id="capability",
    )
    assert err.code == "skill_worker_rejected"
