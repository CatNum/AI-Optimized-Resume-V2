import importlib

import pytest

from career_os.platform.store.session_title import (
    fallback_title_from_messages,
    maybe_generate_title,
)


def _reload_session_store(tmp_path, monkeypatch):
    """_reload_session_store（内部函数 reload session store）的函数说明。

    tmp_path（参数）、monkeypatch（参数）用于向该函数传入运行所需的数据。

    该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import career_os.config as config_mod
    import career_os.platform.store.session as session_mod

    importlib.reload(config_mod)
    importlib.reload(session_mod)
    return session_mod.SessionStore()


def test_fallback_title_from_first_user():
    """test_fallback_title_from_first_user（测试 fallback title from first user）的函数说明。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    messages = [{"role": "assistant", "content": "hi"}, {"role": "user", "content": "hello world"}]
    assert fallback_title_from_messages(messages) == "hello world"


def test_fallback_title_empty_user_defaults():
    """test_fallback_title_empty_user_defaults（测试 fallback title empty user defaults）的函数说明。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    assert fallback_title_from_messages([]) == "未命名会话"
    assert fallback_title_from_messages([{"role": "user", "content": ""}]) == "未命名会话"


def test_maybe_generate_title_after_first_user(tmp_path, monkeypatch):
    """test_maybe_generate_title_after_first_user（测试 maybe generate title after first user）的函数说明。

    tmp_path（参数）、monkeypatch（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    from career_os.agents.lc import models as models_mod

    models_mod.model_settings.__init__()

    store = _reload_session_store(tmp_path, monkeypatch)
    sid = store.create_session()
    store.append_message(sid, "user", "我想转行做后端开发")

    monkeypatch.setattr(
        "career_os.platform.store.session_title._generate_title_llm",
        lambda _content: "职业方向探讨",
    )

    assert maybe_generate_title(sid, store) is True
    row = next(r for r in store.load_index()["sessions"] if r["session_id"] == sid)
    assert row["title"] == "职业方向探讨"
    assert row["title_source"] == "auto"


def test_maybe_generate_title_skips_user_locked(tmp_path, monkeypatch):
    """test_maybe_generate_title_skips_user_locked（测试 maybe generate title skips user locked）的函数说明。

    tmp_path（参数）、monkeypatch（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    from career_os.agents.lc import models as models_mod

    models_mod.model_settings.__init__()

    store = _reload_session_store(tmp_path, monkeypatch)
    sid = store.create_session()
    store.patch_index(sid, title="用户标题", title_source="user")
    store.append_message(sid, "user", "hello")

    monkeypatch.setattr(
        "career_os.platform.store.session_title._generate_title_llm",
        lambda _content: "不应写入",
    )

    assert maybe_generate_title(sid, store) is False
    row = next(r for r in store.load_index()["sessions"] if r["session_id"] == sid)
    assert row["title"] == "用户标题"
    assert row["title_source"] == "user"


def test_append_first_user_sets_fallback_then_auto(tmp_path, monkeypatch):
    """test_append_first_user_sets_fallback_then_auto（测试 append first user sets fallback then auto）的函数说明。

    tmp_path（参数）、monkeypatch（参数）用于向该函数传入运行所需的数据。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    from career_os.agents.lc import models as models_mod

    models_mod.model_settings.__init__()

    store = _reload_session_store(tmp_path, monkeypatch)
    sid = store.create_session()

    monkeypatch.setattr(
        "career_os.platform.store.session_title.schedule_maybe_generate_title",
        lambda _session_id: None,
    )
    monkeypatch.setattr(
        "career_os.platform.store.session_title._generate_title_llm",
        lambda _content: "异步标题",
    )

    store.append_message(sid, "user", "首条用户消息内容")
    row = next(r for r in store.load_index()["sessions"] if r["session_id"] == sid)
    assert row["title"] == "首条用户消息内容"
    assert row["title_source"] == "fallback"

    maybe_generate_title(sid, store)
    row = next(r for r in store.load_index()["sessions"] if r["session_id"] == sid)
    assert row["title"] == "异步标题"
    assert row["title_source"] == "auto"
