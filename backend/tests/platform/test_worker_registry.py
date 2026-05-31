from pathlib import Path

import pytest

from career_os.platform.skill.registry import SkillRegistry
from career_os.platform.worker.registry import WorkerRegistry


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_worker_registry_loads_seven_workers(repo_root: Path):
    registry = WorkerRegistry(registry_path=repo_root / "config" / "workers.registry.json")
    assert len(registry.list_worker_ids()) == 7


def test_get_worker_index_returns_metadata(repo_root: Path):
    registry = WorkerRegistry(registry_path=repo_root / "config" / "workers.registry.json")
    index = registry.get_worker_index()
    assert len(index) == 7
    assert index[0]["worker_id"] == "identity"
    assert "when_to_use" in index[0]
    assert "outputs" in index[0]


def test_load_skill_exploration_first_allowed_workers(repo_root: Path):
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
    registry = SkillRegistry(skills_dir=repo_root / ".agent" / "skills")
    err = registry.load_skill(
        "career-inner-exploration",
        mode="exploration_first",
        worker_id="capability",
    )
    assert err.code == "skill_worker_rejected"
