import json
import re
from typing import Any

from career_os.agents.lc.client import invoke_json, invoke_text, llm_enabled
from career_os.agents.lc.models import LLMRole
from career_os.harness.jd_prerequisites import (
    check_jd_prerequisites,
    is_jd_intent,
    jd_prerequisites_payload,
)
from career_os.harness.explore_closure import (
    explore_continuation_analyze,
    plan_explore_worker_dispatch,
)
from career_os.harness.explore_guidance import (
    sanitize_prior_results_for_synthesis,
    sanitize_structured_for_synthesis,
)
from career_os.harness.explore_intake import enforce_explore_intake, explore_intake_payload
from career_os.platform.prompt.loader import load_coordinator_prompt

EXPLORE_WORKERS = frozenset({"identity", "capability"})
JD_WORKERS = frozenset({"market", "opportunity", "strategy", "resume", "asset"})

_SMALL_TALK_PHRASES = frozenset(
    {
        "你好",
        "您好",
        "hi",
        "hello",
        "hey",
        "在吗",
        "在不在",
        "你好吗",
        "早上好",
        "晚上好",
        "哈喽",
        "嗨",
    }
)


def _coordinator_system() -> str:
    return load_coordinator_prompt().system


def chat_only_synthesis_draft() -> str:
    return load_coordinator_prompt().chat_only_draft


def jd_prerequisites_draft(reason: str | None) -> str:
    prompts = load_coordinator_prompt()
    if reason == "onboarding":
        return prompts.jd_prerequisite_draft_onboarding
    if reason == "explore":
        return prompts.jd_prerequisite_draft_explore
    return prompts.jd_prerequisite_draft_onboarding


def explore_intake_draft() -> str:
    return (
        "为了更高效地开展职业初探，请先填写「初探信息表」。"
        "请粘贴完整简历；工作年限、当前/目标薪资、目标岗位等补充项可选填——"
        "若简历中已有会尽量自动识别，缺失项我会在后续对话中向你确认。"
        "填写完成后我会基于简历继续深度问询。"
    )


def explore_repeat_draft() -> str:
    return "您已完成初探，是否需要再次进行？"


def is_small_talk(user_message: str) -> bool:
    text = user_message.strip().lower()
    if not text:
        return True
    normalized = re.sub(r"[!！。.?？~～,\，、\s]+", "", text)
    return normalized in _SMALL_TALK_PHRASES


def normalize_analyze_result(
    result: dict[str, Any] | None,
    allowed_workers: set[str],
) -> dict[str, Any]:
    if not result:
        return {"workers": []}

    raw_workers = [
        w
        for w in result.get("workers") or []
        if isinstance(w, str) and w in allowed_workers
    ]
    list_type = result.get("list_type")
    if list_type not in {"jd", "explore"}:
        list_type = None

    if list_type == "explore":
        workers = [w for w in raw_workers if w in EXPLORE_WORKERS]
    elif list_type == "jd":
        workers = [w for w in raw_workers if w in JD_WORKERS]
    else:
        explore_picks = [w for w in raw_workers if w in EXPLORE_WORKERS]
        jd_picks = [w for w in raw_workers if w in JD_WORKERS]
        if explore_picks and not jd_picks:
            workers = explore_picks
            list_type = "explore"
        elif jd_picks:
            workers = jd_picks
            list_type = "jd"
        else:
            workers = raw_workers

    if list_type == "explore":
        workers = [w for w in workers if w in EXPLORE_WORKERS]
    elif list_type == "jd":
        workers = [w for w in workers if w in JD_WORKERS]

    out: dict[str, Any] = {"workers": workers}
    if list_type and workers:
        out["list_type"] = list_type
    return out


def _is_jd_route(result: dict[str, Any]) -> bool:
    workers = result.get("workers") or []
    if result.get("list_type") == "jd":
        return True
    return any(w in JD_WORKERS for w in workers)


def enforce_jd_prerequisites(
    result: dict[str, Any],
    session_state: dict[str, Any],
    user_message: str,
) -> dict[str, Any]:
    if not _is_jd_route(result) and not is_jd_intent(user_message):
        return result
    if not _is_jd_route(result):
        return result
    ready, reason = check_jd_prerequisites(session_state)
    if ready:
        return result
    blocked: dict[str, Any] = {
        "workers": [],
        "jd_prerequisite_blocked": True,
        "jd_block_reason": reason or "explore",
    }
    return blocked


_EXPLORE_INTENT_KEYWORDS = (
    "初探",
    "explore",
    "理清",
    "职业方向",
    "职业规划",
    "职业问询",
)

_MARKET_INTENT_KEYWORDS = (
    "市场机会",
    "市场分析",
    "岗位画像",
    "岗位族",
    "趋势",
    "市场行情",
)


def _apply_explore_dispatch_plan(
    result: dict[str, Any],
    session_state: dict[str, Any],
) -> dict[str, Any]:
    workers = result.get("workers") or []
    if not workers:
        return result
    planned = plan_explore_worker_dispatch(workers, session_state)
    if planned == workers:
        return result
    return {**result, "workers": planned}


def fallback_analyze_workers(
    user_message: str,
    session_state: dict[str, Any],
) -> dict[str, Any] | None:
    if is_small_talk(user_message):
        return {"workers": []}

    continued = explore_continuation_analyze(session_state)
    if continued:
        return enforce_explore_intake(continued, session_state)

    text = user_message.lower()
    prior = session_state.get("prior_results") or {}
    flags = (session_state.get("gates") or {}).get("flags") or {}

    if "jd" in text or "岗位" in user_message or "job" in text:
        result = {"workers": ["market", "opportunity"], "list_type": "jd"}
        return enforce_jd_prerequisites(result, session_state, user_message)
    if any(keyword in user_message for keyword in _MARKET_INTENT_KEYWORDS):
        ready, _ = check_jd_prerequisites(session_state)
        if ready:
            return {"workers": ["market"], "list_type": "jd"}
    if "初探" in user_message or "explore" in text:
        result = _apply_explore_dispatch_plan(
            {"workers": ["identity", "capability"], "list_type": "explore"},
            session_state,
        )
        return enforce_explore_intake(result, session_state)
    if any(keyword in user_message for keyword in _EXPLORE_INTENT_KEYWORDS):
        result = _apply_explore_dispatch_plan(
            {"workers": ["identity", "capability"], "list_type": "explore"},
            session_state,
        )
        return enforce_explore_intake(result, session_state)

    if session_state.get("list_type") == "jd":
        if (
            "market" in prior
            and "opportunity" in prior
            and "strategy" not in prior
            and any(k in user_message for k in ("策略", "继续", "下一步", "制定"))
        ):
            return {"workers": ["strategy"]}

    if flags.get("optimize_confirmed"):
        if ("优化" in user_message or "resume" in text) and "resume" not in prior:
            return {"workers": ["resume", "asset"]}
    return None


def analyze_workers(
    user_message: str,
    session_state: dict[str, Any],
    worker_index: list[dict[str, Any]],
) -> dict[str, Any] | None:
    worker_summary: list[dict[str, Any]] = []
    allowed_workers: set[str] = set()
    for worker in worker_index:
        worker_id = worker.get("worker_id")
        if not worker_id:
            continue
        allowed_workers.add(worker_id)
        worker_summary.append(
            {
                "worker_id": worker_id,
                "summary": worker.get("summary", ""),
                "when_to_use": worker.get("when_to_use", []),
            }
        )

    if is_small_talk(user_message):
        return normalize_analyze_result({"workers": []}, allowed_workers)

    if not llm_enabled():
        return None

    user = json.dumps(
        {
            "node": "analyze",
            "message": user_message,
            "list_type": session_state.get("list_type"),
            "gates": session_state.get("gates"),
            "prior_workers": list((session_state.get("prior_results") or {}).keys()),
            "worker_index": worker_summary,
            **jd_prerequisites_payload(session_state),
            **explore_intake_payload(),
        },
        ensure_ascii=False,
    )
    try:
        data = invoke_json(_coordinator_system(), user, role=LLMRole.COORDINATOR)
        if not data:
            return None

        result: dict[str, Any] = {"workers": data.get("workers") or []}
        list_type = data.get("list_type")
        if isinstance(list_type, str) and list_type in {"jd", "explore"}:
            result["list_type"] = list_type
        normalized = normalize_analyze_result(result, allowed_workers)
        normalized = enforce_jd_prerequisites(normalized, session_state, user_message)
        normalized = enforce_explore_intake(normalized, session_state)
        return _apply_explore_dispatch_plan(normalized, session_state)
    except Exception:
        return None


def build_synthesis_messages(
    user_message: str,
    draft_text: str,
    session_state: dict[str, Any],
    last_worker_result: dict[str, Any] | None,
) -> tuple[str, str]:
    explore_guidance = session_state.get("explore_guidance")
    prior_results = sanitize_prior_results_for_synthesis(
        session_state.get("prior_results"),
        explore_guidance if isinstance(explore_guidance, dict) else None,
    )
    last_worker = sanitize_structured_for_synthesis(last_worker_result)
    user = json.dumps(
        {
            "node": "synthesize",
            "user_message": user_message,
            "draft": draft_text,
            "prior_results": prior_results,
            "last_worker_result": last_worker,
            "gates": session_state.get("gates"),
            "explore_guidance": {
                "revealed": (explore_guidance or {}).get("revealed"),
                "has_hidden_options": bool(
                    (explore_guidance or {}).get("options")
                    and not (explore_guidance or {}).get("revealed")
                ),
            },
        },
        ensure_ascii=False,
    )
    return _coordinator_system(), user


def synthesize_with_llm(
    user_message: str,
    draft_text: str,
    session_state: dict[str, Any],
    last_worker_result: dict[str, Any] | None,
) -> str | None:
    if not llm_enabled():
        return None
    system, user = build_synthesis_messages(
        user_message, draft_text, session_state, last_worker_result
    )
    try:
        return invoke_text(system, user, role=LLMRole.COORDINATOR).strip()
    except Exception:
        return None
