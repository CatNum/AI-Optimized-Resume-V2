import importlib

import pytest

from career_os.harness.micro_classifier_rules import match_profile_memory_rules
from career_os.harness.profile_memory import (
    WORKERS_REQUIRE_RESUME,
    build_profile_aware_chat_draft,
    materialize_profile_memory,
    resolve_profile_memory_sections,
)
from tests.conftest import seed_explore_intake_profile


def test_rules_resume_question():
    """验证规则 resume Worker 问题的处理符合预期。"""
    sections = match_profile_memory_rules("你有我的简历吗")
    assert "resume" in sections


def test_resolve_mandatory_resume_for_opportunity():
    """验证解析必需 resume Worker 针对 opportunity Worker 的处理符合预期。"""
    sections = resolve_profile_memory_sections(
        "继续",
        {"list_type": "pipeline", "list_id": "list_x"},
        worker_id="opportunity",
    )
    assert "resume" in sections


def test_all_jd_and_resume_workers_require_resume():
    """验证全部 JD 和 resume Worker 都要求简历上下文 的处理符合预期。"""
    assert WORKERS_REQUIRE_RESUME >= {
        "market",
        "opportunity",
        "strategy",
        "resume",
        "asset",
    }


def test_profile_aware_draft_states_resume_on_file(tmp_path, monkeypatch):
    """验证 profile 感知草稿声明 resume Worker 在文件的处理符合预期。"""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import career_os.config as config_mod
    import career_os.platform.store.profile as profile_mod

    importlib.reload(config_mod)
    monkeypatch.setattr(config_mod.settings, "data_dir", str(tmp_path))
    importlib.reload(profile_mod)
    seed_explore_intake_profile(profile_mod.ProfileStore())

    session_state = {
        "list_type": "pipeline",
        "list_id": "list_x",
        "explore_gate_confirmed": True,
        "gates": {"flags": {}},
    }
    draft = build_profile_aware_chat_draft("你有我的简历吗", session_state)
    assert "档案中已有用户简历" in draft
    assert "不得声称没有用户简历" in draft


def test_materialize_full_resume_for_worker(tmp_path, monkeypatch):
    """验证落盘生成完整 resume Worker 针对 Worker 的处理符合预期。"""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import career_os.config as config_mod
    import career_os.platform.store.profile as profile_mod

    importlib.reload(config_mod)
    importlib.reload(profile_mod)
    seed_explore_intake_profile(profile_mod.ProfileStore())

    memory = materialize_profile_memory(["resume"], full_resume_text=True)
    assert memory["resume"]["resume_on_file"] is True
    assert memory["resume"].get("source_text")
    assert len(memory["resume"]["source_text"]) > 50


def test_materialize_market_and_strategy_from_session_state(tmp_path, monkeypatch):
    """验证落盘生成 market Worker 和 strategy Worker 从 session_state 的处理符合预期。"""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import career_os.config as config_mod
    import career_os.platform.store.profile as profile_mod

    importlib.reload(config_mod)
    importlib.reload(profile_mod)
    seed_explore_intake_profile(profile_mod.ProfileStore())
    session_state = {
        "prior_results": {
            "market": {"role_families": ["session-role"]},
            "strategy": {"path_options": [{"id": "session"}]},
        }
    }
    memory = materialize_profile_memory(
        ["market", "strategy"], full_resume_text=False, session_state=session_state
    )
    assert memory["market"]["role_families"] == ["session-role"]
    assert memory["strategy"]["path_options"] == [{"id": "session"}]
