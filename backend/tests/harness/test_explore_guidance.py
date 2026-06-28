from career_os.harness.explore_guidance import (
    GUIDANCE_OFFER_LINE,
    append_guidance_offer,
    build_explore_guidance_synthesis_draft,
    format_revealed_options,
    normalize_guidance_options,
    persist_worker_guidance,
    should_reveal_explore_guidance,
    wants_guidance_options,
)


def test_wants_guidance_options_detects_clarification():
    """验证想要引导选项识别澄清的处理符合预期。"""
    assert wants_guidance_options("你能给我一些选项吗，你说的和职业有关的事指的是什么？")
    assert not wants_guidance_options("我想选技术深度方向")


def test_persist_and_reveal_guidance():
    """验证持久化和展示引导的处理符合预期。"""
    session_state: dict = {}
    persist_worker_guidance(
        session_state,
        "identity",
        {
            "user_visible_summary": "一年只允许你解决一件职业相关的事，你会选什么？",
            "guidance_options": [
                {"id": "A", "label": "技术深度", "hint": "做深 Go 基础设施"},
                {"id": "B", "label": "带团队", "hint": "向 Tech Lead 过渡"},
            ],
        },
    )
    assert session_state["explore_guidance"]["revealed"] is False
    assert should_reveal_explore_guidance("给我一些选项", session_state)

    draft = build_explore_guidance_synthesis_draft(
        {"user_visible_summary": "一年只允许你解决一件职业相关的事，你会选什么？"},
        session_state,
    )
    assert "A." not in draft
    assert GUIDANCE_OFFER_LINE in draft

    revealed = format_revealed_options(session_state["explore_guidance"])
    assert "A. 技术深度" in revealed
    assert "B. 带团队" in revealed


def test_normalize_guidance_options_caps_at_five():
    """验证规范化引导选项限制在五个的处理符合预期。"""
    raw = [{"label": f"方向{i}"} for i in range(7)]
    options = normalize_guidance_options(raw)
    assert len(options) == 5
    assert options[0]["id"] == "A"
