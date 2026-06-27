import importlib
import json

from typing import Any

import pytest

from career_os.platform.store.profile import ProfileStore


def explore_repeat_cleared_gates() -> dict[str, Any]:
    """为全局 intake 提交后可能进入 explore 的会话准备 gates flags。"""
    return {
        "flags": {
            "explore_repeat_accepted": True,
            "explore_repeat_baseline_at": "2026-05-30T00:00:00Z",
        }
    }


def seed_explore_intake_profile(store: ProfileStore | None = None) -> ProfileStore:
    """构造测试环境和基础状态。"""
    profile = store or ProfileStore()
    resume = (
        "张三\n5年工作经验\n当前薪资：30k\n期望岗位：后端工程师\n"
        "期望薪资：35k-45k\n熟悉 Go 与 Kubernetes。"
    )
    profile.patch(
        [
            {"path": "resume.source_text", "value": resume, "op": "set"},
            {"path": "basic.name", "value": "测试", "op": "set"},
            {"path": "basic.years_of_experience", "value": "5年", "op": "set"},
            {"path": "intent.current_salary", "value": "30K", "op": "set"},
            {"path": "intent.target_salary", "value": "35万", "op": "set"},
            {"path": "intent.target_role", "value": "后端工程师", "op": "set"},
        ]
    )
    # 兼容仍读取全局 exploration intake 的旧测试。
    raw = profile.get(
        [
            "meta",
            "basic",
            "skills",
            "intent",
            "constraints",
            "exploration",
            "career",
            "capability",
            "market",
            "strategy",
            "resume",
            "preference_tags",
            "outputs_index",
        ]
    )
    exploration = dict(raw.get("exploration") or {})
    exploration["intake"] = {
        "submitted_at": "2026-05-31T00:00:00Z",
        "resume_text": resume,
        "pending_fields": [],
        "resolved_fields": {
            "years_of_experience": "5年",
            "current_salary": "30K",
            "target_salary": "35万",
            "target_role": "后端工程师",
        },
    }
    raw["exploration"] = exploration
    profile._profile_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    return profile


def seed_jd_ready_profile(store: ProfileStore | None = None) -> ProfileStore:
    """构造测试环境和基础状态。"""
    profile = store or ProfileStore()
    profile.patch(
        [
            {"path": "basic.name", "value": "测试", "op": "set"},
        ]
    )
    raw = profile.get(
        [
            "meta",
            "basic",
            "skills",
            "intent",
            "constraints",
            "exploration",
            "career",
            "capability",
            "market",
            "strategy",
            "resume",
            "preference_tags",
            "outputs_index",
        ]
    )
    exploration = dict(raw.get("exploration") or {})
    exploration["completed_at"] = "2026-05-31T00:00:00Z"
    raw["exploration"] = exploration
    profile._profile_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    return profile


@pytest.fixture
def explore_intake_profile(tmp_path, monkeypatch):
    """构造测试环境和基础状态。"""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import career_os.config as config_mod
    import career_os.platform.store.profile as profile_mod

    importlib.reload(config_mod)
    importlib.reload(profile_mod)
    return seed_explore_intake_profile(ProfileStore())


@pytest.fixture
def jd_ready_profile(tmp_path, monkeypatch):
    """构造测试环境和基础状态。"""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import career_os.config as config_mod
    import career_os.platform.store.profile as profile_mod

    importlib.reload(config_mod)
    importlib.reload(profile_mod)
    return seed_jd_ready_profile(ProfileStore())


@pytest.fixture(autouse=True)
def _reset_llm_settings_for_l1(request, monkeypatch):
    """避免 LLM 单元测试中的旧 model_settings.llm_api_key 泄漏到其他测试。"""
    if request.node.get_closest_marker("llm"):
        yield
        return
    from career_os.agents.lc import models as models_mod

    # 空环境变量会覆盖 backend/.env，让 L1 继续使用 react_mocks，而不调用真实 API。
    monkeypatch.setenv("LLM_API_KEY", "")
    models_mod.model_settings.__init__()
    yield
    models_mod.model_settings.__init__()
