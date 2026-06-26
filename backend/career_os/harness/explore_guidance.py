from __future__ import annotations

import re
from typing import Any

EXPLORE_GUIDANCE_WORKERS = frozenset({"identity", "capability"})

GUIDANCE_OFFER_LINE = (
    "你先随想随说就好，不用急着选边站。"
    "要是脑子里还没画面，跟我说一声「给我一些选项」，我帮你列几个方向参考。"
)

GUIDANCE_REVEAL_INTRO = (
    "没问题，我先给你几个方向碰碰思路——不用硬选，"
    "挑一个改说、混着说、或者完全按你自己的说法来都行："
)

_WANTS_OPTIONS_PATTERNS = [
    r"选项",
    r"备选项",
    r"给我一些",
    r"举[几个例]",
    r"参考方向",
    r"想不明白",
    r"想不清楚",
    r"不知道.*(选|答|说)",
    r"指的是什么",
    r"是什么意思",
    r"什么意思",
    r"有哪些",
    r"能.*举例",
]


def wants_guidance_options(user_message: str) -> bool:
    """wants_guidance_options（wants guidance options）的函数说明。

    user_message（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    text = user_message.strip()
    if not text:
        return False
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in _WANTS_OPTIONS_PATTERNS)


def normalize_guidance_options(raw: Any) -> list[dict[str, str]]:
    """normalize_guidance_options（normalize guidance options）的函数说明。

    raw（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    if not isinstance(raw, list):
        return []
    options: list[dict[str, str]] = []
    labels = "ABCDEFGH"
    for index, item in enumerate(raw[:5]):
        if not isinstance(item, dict):
            continue
        option_id = str(item.get("id") or labels[index]).strip()
        label = str(item.get("label") or item.get("title") or "").strip()
        hint = str(item.get("hint") or item.get("description") or item.get("summary") or "").strip()
        if not label:
            continue
        options.append({"id": option_id, "label": label, "hint": hint})
    return options


def persist_worker_guidance(
    session_state: dict[str, Any],
    worker_id: str,
    structured_output: dict[str, Any] | None,
) -> None:
    """持久化探索 Worker 给出的引导选项。

    session_state（会话状态）会被原地写入 explore_guidance；
    worker_id（工作者标识）记录选项来自 identity 还是 capability；
    structured_output（结构化输出）中如果包含 guidance_options，就会保存为待揭示选项。
    """
    if not structured_output:
        return
    options = normalize_guidance_options(structured_output.get("guidance_options"))
    if not options:
        return
    session_state["explore_guidance"] = {
        "worker_id": worker_id,
        "question": structured_output.get("user_visible_summary") or "",
        "options": options,
        "revealed": False,
    }


def should_reveal_explore_guidance(user_message: str, session_state: dict[str, Any]) -> bool:
    """判断是否应该向用户展示探索引导选项。

    user_message（用户消息）用于识别“给我一些选项”等请求；
    session_state（会话状态）保存 explore_guidance 及 revealed（是否已展示）。
    返回值为 True 表示本轮应展示隐藏选项。
    """
    guidance = session_state.get("explore_guidance") or {}
    if not guidance.get("options") or guidance.get("revealed"):
        return False
    return wants_guidance_options(user_message)


def mark_explore_guidance_revealed(session_state: dict[str, Any]) -> None:
    """标记探索引导选项已展示。

    session_state（会话状态）会被原地更新：explore_guidance.revealed 设为 True，
    并写入 explore_guidance_reveal_pending，供 synthesize 阶段生成选项回复。
    """
    guidance = dict(session_state.get("explore_guidance") or {})
    guidance["revealed"] = True
    session_state["explore_guidance"] = guidance
    session_state["explore_guidance_reveal_pending"] = True


def format_revealed_options(guidance: dict[str, Any]) -> str:
    """格式化已揭示的探索选项。

    guidance（引导信息）包含 question（原问题）和 options（选项列表）。
    返回值是面向用户的多行文本，会把选项和原问题一起展示。
    """
    question = (guidance.get("question") or "").strip()
    options = guidance.get("options") or []
    lines = [GUIDANCE_REVEAL_INTRO, ""]
    for item in options:
        option_id = item.get("id") or "?"
        label = item.get("label") or ""
        hint = item.get("hint") or ""
        line = f"{option_id}. {label}"
        if hint:
            line += f" — {hint}"
        lines.append(line)
    if question:
        lines.extend(["", f"回到刚才的问题：{question}"])
    return "\n".join(lines)


def append_guidance_offer(summary: str) -> str:
    """append_guidance_offer（append guidance offer）的函数说明。

    summary（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    text = summary.strip()
    if not text:
        return GUIDANCE_OFFER_LINE
    if GUIDANCE_OFFER_LINE in text:
        return text
    return f"{text}\n\n{GUIDANCE_OFFER_LINE}"


def build_explore_guidance_synthesis_draft(
    structured_output: dict[str, Any],
    session_state: dict[str, Any],
) -> str:
    """构造探索引导场景的合成草稿。

    structured_output（结构化输出）提供 user_visible_summary；
    session_state（会话状态）提供 explore_guidance 是否已揭示。
    返回值会在选项未揭示时追加“可请求选项”的提示。
    """
    summary = (structured_output.get("user_visible_summary") or "").strip()
    guidance = session_state.get("explore_guidance") or {}
    if guidance.get("options") and not guidance.get("revealed"):
        return append_guidance_offer(summary)
    return summary or "请继续分享你的想法。"


def supports_explore_guidance(worker_id: str) -> bool:
    """判断 Worker 是否支持探索引导选项。

    worker_id（工作者标识）用于匹配 EXPLORE_GUIDANCE_WORKERS。
    返回值为 True 表示该 Worker 的 guidance_options 可以被延迟展示。
    """
    return worker_id in EXPLORE_GUIDANCE_WORKERS


def sanitize_structured_for_synthesis(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    """清理最近 Worker 结果中的隐藏引导选项。

    payload（负载）通常是 last_worker_result。返回值会移除 structured_output 中的
    guidance_options，避免 LLM 在用户未请求前提前泄露选项。
    """
    if not payload:
        return payload
    structured = payload.get("structured_output")
    if not isinstance(structured, dict) or "guidance_options" not in structured:
        return payload
    copy = dict(payload)
    sanitized = {**structured}
    sanitized.pop("guidance_options", None)
    copy["structured_output"] = sanitized
    return copy


def sanitize_prior_results_for_synthesis(
    prior_results: dict[str, Any] | None,
    explore_guidance: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """清理历史 Worker 结果中的隐藏引导选项。

    prior_results（历史结果）保存各 Worker 的轻量输出；
    explore_guidance（探索引导）说明选项是否已揭示。返回值在选项未揭示时会移除
    guidance_options，防止合成阶段提前暴露隐藏参考方向。
    """
    if not prior_results:
        return prior_results
    if (explore_guidance or {}).get("revealed"):
        return prior_results
    sanitized: dict[str, Any] = {}
    for worker_id, result in prior_results.items():
        if isinstance(result, dict) and "guidance_options" in result:
            copy = {**result}
            copy.pop("guidance_options", None)
            sanitized[worker_id] = copy
        else:
            sanitized[worker_id] = result
    return sanitized
