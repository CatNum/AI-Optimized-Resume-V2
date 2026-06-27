"""异步或按需生成的 LLM 会话标题，关联 D7。"""

from __future__ import annotations

import logging
import re
import threading

from career_os.agents.lc.client import invoke_text, llm_enabled
from career_os.agents.lc.models import LLMRole
from career_os.platform.store.session import SessionStore, _DEFAULT_TITLE

_logger = logging.getLogger(__name__)

_TITLE_SYSTEM = (
    "你是会话标题生成器。根据用户的首条消息，生成一个简短的中文会话标题。"
    "要求：不超过16个汉字；不要引号、标点装饰或解释；只输出标题本身。"
)

_MAX_LLM_INPUT = 200
_MAX_TITLE_LEN = 16


def _first_user_message(messages: list[dict[str, str]]) -> dict[str, str] | None:
    """_first_user_message（内部函数 first user message）的函数说明。

    messages（参数）用于向该函数传入运行所需的数据。

    该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
    return next((m for m in messages if m.get("role") == "user"), None)


def fallback_title_from_messages(messages: list[dict[str, str]]) -> str:
    """fallback_title_from_messages（fallback title from messages）的函数说明。

    messages（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    first_user = _first_user_message(messages)
    if first_user is None:
        return _DEFAULT_TITLE
    content = (first_user.get("content") or "").strip()
    if not content:
        return _DEFAULT_TITLE
    return content[:20]


def _index_row(store: SessionStore, session_id: str) -> dict | None:
    """_index_row（内部函数 index row）的函数说明。

    store（参数）、session_id（参数）用于向该函数传入运行所需的数据。

    该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
    index = store.load_index()
    return next(
        (r for r in index.get("sessions", []) if r.get("session_id") == session_id),
        None,
    )


def _normalize_llm_title(raw: str) -> str:
    """_normalize_llm_title（内部函数 normalize llm title）的函数说明。

    raw（参数）用于向该函数传入运行所需的数据。

    该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
    text = raw.strip()
    text = re.sub(r'^[\s"\'“”‘’「」【】]+|[\s"\'“”‘’「」【】]+$', "", text)
    text = text.replace("\n", " ").strip()
    if len(text) > _MAX_TITLE_LEN:
        text = text[:_MAX_TITLE_LEN]
    return text


def _generate_title_llm(user_content: str) -> str | None:
    """_generate_title_llm（内部函数 generate title llm）的函数说明。

    user_content（参数）用于向该函数传入运行所需的数据。

    该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
    snippet = user_content[:_MAX_LLM_INPUT]
    try:
        raw = invoke_text(_TITLE_SYSTEM, snippet, role=LLMRole.WORKER, temperature=0.2)
    except Exception:
        _logger.exception("session title LLM failed")
        return None
    title = _normalize_llm_title(raw)
    return title or None


def maybe_generate_title(
    session_id: str,
    store: SessionStore,
    *,
    force: bool = False,
) -> bool:
    """在允许时生成 LLM 标题；如果索引标题被更新为 auto，则返回 True。"""
    if not llm_enabled():
        return False

    row = _index_row(store, session_id)
    if row is None:
        return False

    title_source = row.get("title_source")
    if not force and title_source == "user":
        return False

    messages = store.load_messages_full(session_id)
    first_user = _first_user_message(messages)
    if first_user is None:
        return False

    generated = _generate_title_llm(first_user.get("content", ""))
    if not generated:
        return False

    store.patch_index(session_id, title=generated, title_source="auto")
    return True


def schedule_maybe_generate_title(session_id: str) -> None:
    """schedule_maybe_generate_title（schedule maybe generate title）的函数说明。

    session_id（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    def _run() -> None:
        """_run（内部函数 run）的函数说明。

        该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
        try:
            maybe_generate_title(session_id, SessionStore(), force=False)
        except Exception:
            _logger.exception("async session title generation failed for %s", session_id)

    threading.Thread(target=_run, daemon=True, name=f"session-title-{session_id[:12]}").start()
