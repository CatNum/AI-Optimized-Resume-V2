from career_os.platform.prompt.loader import (
    load_coordinator_prompt,
    load_prompt,
    load_worker_llm_prompt,
    render_prompt,
)


def test_load_coordinator_prompt_is_single_document():
    prompt = load_coordinator_prompt()
    assert "入口路由编排智能体" in prompt.system
    assert "### analyze" in prompt.system
    assert "### synthesize" in prompt.system
    assert "输出契约" in prompt.system
    assert '"workers": [], "list_type": null' in prompt.system
    assert "主动引导" in prompt.chat_only_draft
    assert prompt.jd_prerequisite_draft_onboarding
    assert "建档" in prompt.jd_prerequisite_draft_onboarding
    assert "初探" in prompt.jd_prerequisite_draft_explore


def test_load_worker_react_boot_user_template():
    rendered = render_prompt(
        load_worker_llm_prompt("react_boot_user"),
        payload='{"goal": "test"}',
    )
    assert "ReAct 循环" in rendered
    assert '{"goal": "test"}' in rendered


def test_load_worker_default_prompt():
    text = load_prompt("market")
    assert "market worker" in text
