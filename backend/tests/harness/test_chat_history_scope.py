from career_os.harness.chat_history_scope import select_worker_chat_history
from career_os.platform.store.session import slice_chat_rounds


def _long_session(n_users: int) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    for i in range(n_users):
        messages.append({"role": "user", "content": f"u{i}"})
        messages.append({"role": "assistant", "content": f"a{i}"})
    return messages


def test_worker_default_ten_rounds():
    full = _long_session(20)
    window, scope = select_worker_chat_history(full, "继续分析", {})
    assert scope == "recent_10"
    assert len(window) < len(full)
    expected = slice_chat_rounds(full, max_rounds=10)
    assert window == expected


def test_worker_full_when_rule_matches():
    full = _long_session(5)
    window, scope = select_worker_chat_history(full, "请根据完整对话分析", {})
    assert scope == "full"
    assert len(window) == len(full)
