import importlib

import pytest

from career_os.platform.store.session_title import (
    fallback_title_from_messages,
    maybe_generate_title,
)


def _reload_session_store(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import career_os.config as config_mod
    import career_os.platform.store.session as session_mod

    importlib.reload(config_mod)
    importlib.reload(session_mod)
    return session_mod.SessionStore()


def test_fallback_title_from_first_user():
    messages = [{"role": "assistant", "content": "hi"}, {"role": "user", "content": "hello world"}]
    assert fallback_title_from_messages(messages) == "hello world"


def test_fallback_title_empty_user_defaults():
    assert fallback_title_from_messages([]) == "未命名会话"
    assert fallback_title_from_messages([{"role": "user", "content": ""}]) == "未命名会话"


def test_maybe_generate_title_after_first_user(tmp_path, monkeypatch):
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
