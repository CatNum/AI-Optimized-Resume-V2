from career_os.agents.lc.tools import get_litellm_tools_for_worker


def test_market_tools_include_browser_fetch():
    """test_market_tools_include_browser_fetch（测试 market tools include browser fetch）的函数说明。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    tools = get_litellm_tools_for_worker("market")
    names = [t["function"]["name"] for t in tools]
    assert "browser_fetch" in names
    assert "load_skill" in names
    assert "profile_patch" in names


def test_resume_cannot_see_register_outputs():
    """test_resume_cannot_see_register_outputs（测试 resume cannot see register outputs）的函数说明。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    tools = get_litellm_tools_for_worker("resume")
    names = [t["function"]["name"] for t in tools]
    assert "register_outputs_index" not in names
