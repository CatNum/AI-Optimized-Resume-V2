from career_os.harness.chat_history_scope import select_worker_chat_history
from career_os.platform.store.session import slice_chat_rounds


def _long_session(n_users: int) -> list[dict[str, str]]:
    """_long_session（内部函数 long session）的函数说明。

    n_users（参数）用于向该函数传入运行所需的数据。

    该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
    messages: list[dict[str, str]] = []
    for i in range(n_users):
        messages.append({"role": "user", "content": f"u{i}"})
        messages.append({"role": "assistant", "content": f"a{i}"})
    return messages


def test_worker_default_ten_rounds():
    """test_worker_default_ten_rounds（测试 worker default ten rounds）的函数说明。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    full = _long_session(20)
    window, scope = select_worker_chat_history(full, "继续分析", {})
    assert scope == "recent_10"
    assert len(window) < len(full)
    expected = slice_chat_rounds(full, max_rounds=10)
    assert window == expected


def test_worker_full_when_rule_matches():
    """test_worker_full_when_rule_matches（测试 worker full when rule matches）的函数说明。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    full = _long_session(5)
    window, scope = select_worker_chat_history(full, "请根据完整对话分析", {})
    assert scope == "full"
    assert len(window) == len(full)
