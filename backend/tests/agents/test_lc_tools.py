from career_os.agents.lc.tools import get_litellm_tools_for_worker


def test_market_tools_include_browser_fetch():
    """验证 market Worker 工具会包含浏览器抓取。"""
    tools = get_litellm_tools_for_worker("market")
    names = [t["function"]["name"] for t in tools]
    assert "browser_fetch" in names
    assert "load_skill" in names
    assert "profile_patch" in names


def test_resume_cannot_see_register_outputs():
    """验证 resume Worker 不能看到登记产物。"""
    tools = get_litellm_tools_for_worker("resume")
    names = [t["function"]["name"] for t in tools]
    assert "register_outputs_index" not in names
