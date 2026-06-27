import pytest

from career_os.platform.prompt.loader import (
    load_coordinator_prompt,
    load_prompt,
    load_worker_llm_prompt,
    load_worker_system_prompt,
    render_prompt,
)

WORKER_IDS = (
    "identity",
    "capability",
    "market",
    "opportunity",
    "strategy",
    "resume",
    "asset",
)

WORKER_ROLE_MARKERS = {
    "identity": "身份智能体",
    "capability": "能力智能体",
    "market": "市场智能体",
    "opportunity": "岗位/机会智能体",
    "strategy": "策略智能体",
    "resume": "简历智能体",
    "asset": "资产智能体",
}


def test_load_coordinator_prompt_is_single_document():
    """验证 load coordinator prompt is single document 场景。"""
    prompt = load_coordinator_prompt()
    assert "职业规划助手" in prompt.system
    assert "用户可见话术" in prompt.system
    assert "### analyze" in prompt.system
    assert "### synthesize" in prompt.system
    assert "输出契约" in prompt.system
    assert '"workers": [], "list_type": null' in prompt.system
    assert "主动引导" in prompt.chat_only_draft
    assert prompt.jd_prerequisite_draft_onboarding
    assert "建档" in prompt.jd_prerequisite_draft_onboarding
    assert "初探" in prompt.jd_prerequisite_draft_explore


def test_load_worker_react_boot_user_template():
    """验证 load worker react boot user template 场景。"""
    rendered = render_prompt(
        load_worker_llm_prompt("react_boot_user"),
        payload='{"goal": "test"}',
    )
    assert "ReAct 循环" in rendered
    assert '{"goal": "test"}' in rendered


@pytest.mark.parametrize("worker_id", WORKER_IDS)
def test_load_worker_system_prompt_structure(worker_id: str):
    """验证 load worker system prompt structure 场景。"""
    text = load_worker_system_prompt(worker_id)
    assert WORKER_ROLE_MARKERS[worker_id] in text
    assert "## 1. 角色" in text
    assert "## 5. ReAct 执行" in text
    assert "输出契约" in text
    assert "## 6. 安全与合规" in text
    assert "gate_prompt" in text or worker_id in {"market", "resume"}


def test_load_prompt_delegates_to_system_md():
    """验证 load prompt delegates to system md 场景。"""
    assert load_prompt("market") == load_worker_system_prompt("market")
    assert "市场智能体" in load_prompt("market")
