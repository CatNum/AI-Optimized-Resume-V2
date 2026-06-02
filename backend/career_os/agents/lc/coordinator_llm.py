import json
import re
from typing import Any

from career_os.agents.lc import client as lc_client
from career_os.agents.lc.client import invoke_text
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
from career_os.harness.explore_depth import can_offer_explore_complete
from career_os.harness.pipeline_routing import (
    as_pipeline_analyze_result,
    enforce_pipeline_phase_rules,
    get_current_phase,
    infer_pipeline_phase_from_workers,
    is_pipeline_session,
    pipeline_analyze_payload,
    pipeline_fallback_workers,
)
from career_os.platform.store.profile import ProfileStore
from career_os.harness.explore_guidance import (
    sanitize_prior_results_for_synthesis,
    sanitize_structured_for_synthesis,
)
from career_os.harness.explore_intake import enforce_explore_intake, explore_intake_payload
from career_os.harness.profile_memory import (
    format_profile_memory_for_draft,
    materialize_profile_memory,
    resolve_profile_memory_sections,
)
from career_os.platform.prompt.loader import load_coordinator_prompt

EXPLORE_WORKERS = frozenset({"identity", "capability"})
JD_WORKERS = frozenset({"market", "opportunity", "strategy", "resume", "asset"})
DEEP_PIPELINE_PHASES = frozenset(
    {"market", "jd_analysis", "resume_strategy", "resume_optimize"}
)

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


def chat_only_synthesis_draft(session_state: dict[str, Any] | None = None) -> str:
    base = load_coordinator_prompt().chat_only_draft
    if not session_state or session_state.get("list_type") != "pipeline":
        return base
    from career_os.harness.session_activity import build_session_activity

    activity = build_session_activity(session_state)
    headline = activity.get("headline") or ""
    payload = pipeline_analyze_payload(session_state)
    phase = payload.get("current_phase") or "explore"
    return (
        f"{base}\n\n"
        f"【pipeline 阶段 SSOT】current_phase={phase}；{headline}。"
        "用户若询问「当前在什么阶段/进行什么」，必须按 SSOT 回答，"
        "不得声称仍在职业初探，除非 current_phase 为 explore。"
    )


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


def explore_complete_synthesis_draft() -> str:
    return (
        "内在需求和能力图谱两条线我们都梳理完了。想请你确认一下："
        "你觉得我们刚才的交流，是否已经足够完整地概括了你的职业画像？"
        "若你确认完成，我就可以开始帮你分析目标方向的市场机会和岗位画像。"
    )


def _market_continue_draft(session_state: dict[str, Any]) -> str:
    from career_os.harness.session_activity import build_session_activity

    headline = (build_session_activity(session_state).get("headline") or "")
    return (
        f"【pipeline 阶段 SSOT】current_phase=market；{headline}。\n"
        "用户可能在续聊市场趋势或准备提交 JD。请直接回应其问题；"
        "若需 JD 全文可邀请粘贴；不要套用寒暄模板。"
    )


def _jd_analysis_continue_draft(
    user_message: str,
    session_state: dict[str, Any],
) -> str:
    from career_os.harness.session_activity import build_session_activity

    headline = (build_session_activity(session_state).get("headline") or "")
    lines = [
        f"【pipeline 阶段 SSOT】current_phase=jd_analysis；{headline}。",
        "用户可能在续聊 JD 匹配评估。若其问的是简历策略或如何改简历，"
        "应基于已有评估结论作答，而非重复初探引导。",
    ]
    if "策略" in user_message or "优化" in user_message:
        lines.append("本轮语义偏策略：优先回答如何优化，勿强行挂「不推荐投递」闸门。")
    if "agent" in user_message.lower() or "智能体" in user_message or "职业规划" in user_message:
        lines.append(
            "用户可能在说明已有 Agent 实战：承认该项目即可，勿推荐另选智能客服/代码审查模板。"
        )
    return "\n".join(lines)


def _resume_strategy_continue_draft(
    user_message: str,
    session_state: dict[str, Any],
) -> str:
    pending = (session_state.get("gates") or {}).get("pending") or {}
    pending_name = pending.get("name") or ""
    prior = session_state.get("prior_results") or {}
    strategy = prior.get("strategy") or {}
    opportunity = prior.get("opportunity") or {}
    lines = [
        "【pipeline 阶段 SSOT】current_phase=resume_strategy。",
        "用户本轮关注简历优化策略或如何用现有项目/经历写简历；须直接回答问题。",
    ]
    if pending_name == "jd_continue_despite_not_recommended":
        lines.append("存在待确认 JD 闸门时可简短确认，但以回答策略与写法为主。")
    else:
        lines.append(
            "禁止复读「暂不推荐投递」二选一闸门，除非用户明确要求重新做匹配评估。"
        )
    summary = strategy.get("user_visible_summary")
    if summary:
        lines.append(f"已有 strategy 产物，可融入要点：{str(summary)[:900]}")
    elif opportunity.get("user_visible_summary"):
        lines.append(
            "可参考 prior opportunity 摘要中的策略建议段落；"
            "用户若称已有 Agent 项目，应帮助其写入简历而非要求先补项目。"
        )
    if "项目" in user_message or "agent" in user_message.lower() or "职业规划" in user_message:
        lines.append(
            "用户已说明在做的 Agent/项目（如职业规划 Agent）：不得再追问「选智能客服还是代码审查」；"
            "应基于用户所述项目类型，直接协助写进简历或给 STAR/技术栈表述建议。"
        )
    memory_sections = resolve_profile_memory_sections(user_message, session_state)
    memory = materialize_profile_memory(
        memory_sections, full_resume_text=False, session_state=session_state
    )
    facts = format_profile_memory_for_draft(memory)
    lines.append(f"【本回合档案事实 — 回答须与此一致】\n{facts}")
    return "\n".join(lines)


def _resume_optimize_continue_draft(session_state: dict[str, Any]) -> str:
    from career_os.harness.session_activity import build_session_activity

    headline = (build_session_activity(session_state).get("headline") or "")
    return (
        f"【pipeline 阶段 SSOT】current_phase=resume_optimize；{headline}。\n"
        "用户处于简历优化执行阶段；回应其关于改写、模块或交付物的具体问题。"
    )


def build_phase_synthesis_draft(
    user_message: str,
    session_state: dict[str, Any],
) -> str:
    """Phase-aware synthesis draft; deep phases avoid chat_only 寒暄模板."""
    from career_os.harness.profile_memory import build_profile_aware_chat_draft

    phase = get_current_phase(session_state) or "explore"
    if not is_pipeline_session(session_state) or phase not in DEEP_PIPELINE_PHASES:
        return build_profile_aware_chat_draft(user_message, session_state)
    if phase == "market":
        base = _market_continue_draft(session_state)
    elif phase == "jd_analysis":
        base = _jd_analysis_continue_draft(user_message, session_state)
    elif phase == "resume_strategy":
        return _resume_strategy_continue_draft(user_message, session_state)
    else:
        base = _resume_optimize_continue_draft(session_state)
    memory_sections = resolve_profile_memory_sections(user_message, session_state)
    memory = materialize_profile_memory(
        memory_sections, full_resume_text=False, session_state=session_state
    )
    facts = format_profile_memory_for_draft(memory)
    return (
        f"{base}\n\n【本回合档案事实】\n{facts}\n"
        "若 resume_on_file 为真，不得声称没有用户简历。"
    )


def is_small_talk(user_message: str) -> bool:
    text = user_message.strip().lower()
    if not text:
        return True
    normalized = re.sub(r"[!！。.?？~～,\，、\s]+", "", text)
    return normalized in _SMALL_TALK_PHRASES


def normalize_analyze_result(
    result: dict[str, Any] | None,
    allowed_workers: set[str],
    session_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not result:
        return {"workers": []}

    raw_workers = [
        w
        for w in result.get("workers") or []
        if isinstance(w, str) and w in allowed_workers
    ]
    if not raw_workers:
        return {"workers": []}

    if session_state and (
        is_pipeline_session(session_state) or session_state.get("list_id")
    ):
        coerced = as_pipeline_analyze_result(
            {
                **result,
                "workers": raw_workers,
                "pipeline_phase": result.get("pipeline_phase")
                or infer_pipeline_phase_from_workers(raw_workers, session_state),
            },
            session_state,
        )
        return {
            "workers": coerced.get("workers") or [],
            "list_type": "pipeline",
            "pipeline_phase": coerced.get("pipeline_phase"),
        }

    return {"workers": raw_workers}


def _is_jd_route(result: dict[str, Any]) -> bool:
    workers = result.get("workers") or []
    if result.get("list_type") == "pipeline":
        phase = result.get("pipeline_phase")
        if phase in {"market", "jd_analysis", "resume_strategy", "resume_optimize"}:
            return True
        return any(w in JD_WORKERS for w in workers)
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

    text = user_message.lower()
    prior = session_state.get("prior_results") or {}
    flags = (session_state.get("gates") or {}).get("flags") or {}

    if is_pipeline_session(session_state) or session_state.get("list_id"):
        if is_jd_intent(user_message) or "jd" in text:
            result = as_pipeline_analyze_result(
                {
                    "workers": ["market", "opportunity"],
                    "pipeline_phase": "jd_analysis",
                },
                session_state,
            )
            return enforce_jd_prerequisites(result, session_state, user_message)
        if any(keyword in user_message for keyword in _MARKET_INTENT_KEYWORDS):
            ready, _ = check_jd_prerequisites(session_state)
            if ready:
                result = as_pipeline_analyze_result(
                    {"workers": ["market"], "pipeline_phase": "market"},
                    session_state,
                )
                return enforce_jd_prerequisites(result, session_state, user_message)
        if "初探" in user_message or "explore" in text:
            result = _apply_explore_dispatch_plan(
                as_pipeline_analyze_result(
                    {
                        "workers": ["identity", "capability"],
                        "pipeline_phase": "explore",
                    },
                    session_state,
                ),
                session_state,
            )
            return enforce_explore_intake(result, session_state)
        if any(keyword in user_message for keyword in _EXPLORE_INTENT_KEYWORDS):
            result = _apply_explore_dispatch_plan(
                as_pipeline_analyze_result(
                    {
                        "workers": ["identity", "capability"],
                        "pipeline_phase": "explore",
                    },
                    session_state,
                ),
                session_state,
            )
            return enforce_explore_intake(result, session_state)
        from career_os.harness.micro_classifier_rules import (
            match_pipeline_intent_rule_ids,
        )

        rule_ids = set(match_pipeline_intent_rule_ids(user_message))
        if rule_ids & {"intent_resume_strategy", "intent_declare_agent_project"}:
            result = enforce_pipeline_phase_rules(
                {
                    "workers": ["strategy"],
                    "pipeline_phase": "resume_strategy",
                    "list_type": "pipeline",
                },
                session_state,
                user_message,
            )
            return enforce_explore_intake(result, session_state)
        if (
            "market" in prior
            and "opportunity" in prior
            and "strategy" not in prior
            and any(k in user_message for k in ("策略", "继续", "下一步", "制定"))
        ):
            result = enforce_pipeline_phase_rules(
                {
                    "workers": ["strategy"],
                    "pipeline_phase": "resume_strategy",
                    "list_type": "pipeline",
                },
                session_state,
                user_message,
            )
            return enforce_explore_intake(result, session_state)
        if flags.get("optimize_confirmed"):
            if ("优化" in user_message or "resume" in text) and "resume" not in prior:
                return as_pipeline_analyze_result(
                    {
                        "workers": ["resume", "asset"],
                        "pipeline_phase": "resume_optimize",
                    },
                    session_state,
                )
        pipeline_fb = pipeline_fallback_workers(user_message, session_state)
        if pipeline_fb is not None:
            return enforce_explore_intake(pipeline_fb, session_state)
        continued = explore_continuation_analyze(session_state)
        if continued:
            return enforce_explore_intake(continued, session_state)
        return None

    pipeline_fb = pipeline_fallback_workers(user_message, session_state)
    if pipeline_fb is not None:
        return enforce_explore_intake(pipeline_fb, session_state)

    continued = explore_continuation_analyze(session_state)
    if continued:
        return enforce_explore_intake(continued, session_state)

    if "jd" in text or "岗位" in user_message or "job" in text:
        result = as_pipeline_analyze_result(
            {"workers": ["market", "opportunity"], "pipeline_phase": "jd_analysis"},
            session_state,
        )
        return enforce_jd_prerequisites(result, session_state, user_message)
    return None


def analyze_workers(
    user_message: str,
    session_state: dict[str, Any],
    worker_index: list[dict[str, Any]],
    *,
    chat_history: list[dict[str, str]] | None = None,
    messages_meta: dict[str, Any] | None = None,
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
        return normalize_analyze_result({"workers": []}, allowed_workers, session_state)

    if not lc_client.llm_enabled():
        return None

    profile = ProfileStore().get(
        ["basic", "intent", "exploration", "resume", "capability"]
    )
    offer_explore, explore_diag = can_offer_explore_complete(profile, session_state)
    analyze_payload: dict[str, Any] = {
        "node": "analyze",
        "message": user_message,
        "chat_history": chat_history or [],
        "messages_meta": messages_meta or {},
        "list_type": session_state.get("list_type"),
        "gates": session_state.get("gates"),
        "prior_workers": list((session_state.get("prior_results") or {}).keys()),
        "worker_index": worker_summary,
        "can_offer_explore_complete": offer_explore,
        "explore_depth_diag": explore_diag,
        **jd_prerequisites_payload(session_state),
        **explore_intake_payload(session_state),
    }
    memory_sections = resolve_profile_memory_sections(user_message, session_state)
    if memory_sections:
        analyze_payload["profile_memory_sections"] = memory_sections
        analyze_payload["profile_memory"] = materialize_profile_memory(
            memory_sections, full_resume_text=False, session_state=session_state
        )
    if session_state.get("list_type") == "pipeline":
        analyze_payload.update(
            pipeline_analyze_payload(session_state, user_message)
        )
    user = json.dumps(analyze_payload, ensure_ascii=False)
    try:
        data = lc_client.invoke_json(_coordinator_system(), user, role=LLMRole.COORDINATOR)
        if not data:
            return None

        result: dict[str, Any] = {"workers": data.get("workers") or []}
        if data.get("pipeline_phase"):
            result["pipeline_phase"] = data["pipeline_phase"]
        if is_pipeline_session(session_state) or session_state.get("list_id"):
            result["list_type"] = "pipeline"
        normalized = normalize_analyze_result(result, allowed_workers, session_state)
        if is_pipeline_session(session_state) or session_state.get("list_id"):
            normalized = enforce_pipeline_phase_rules(
                normalized, session_state, user_message
            )
        else:
            normalized = enforce_jd_prerequisites(
                normalized, session_state, user_message
            )
        normalized = enforce_explore_intake(normalized, session_state)
        return _apply_explore_dispatch_plan(normalized, session_state)
    except Exception:
        return None


def build_synthesis_messages(
    user_message: str,
    draft_text: str,
    session_state: dict[str, Any],
    last_worker_result: dict[str, Any] | None,
    *,
    chat_history: list[dict[str, str]] | None = None,
    messages_meta: dict[str, Any] | None = None,
) -> tuple[str, str]:
    explore_guidance = session_state.get("explore_guidance")
    prior_results = sanitize_prior_results_for_synthesis(
        session_state.get("prior_results"),
        explore_guidance if isinstance(explore_guidance, dict) else None,
    )
    last_worker = sanitize_structured_for_synthesis(last_worker_result)
    meta = messages_meta or {}
    over_limit_hint = ""
    if meta.get("over_limit"):
        over_limit_hint = (
            "（对话已超过建议上下文上限，请在回复末尾简短建议用户"
            " POST /v1/sessions/new 开新会话；档案与产物保留。）"
        )
    payload: dict[str, Any] = {
        "node": "synthesize",
        "synthesis_voice": (
            "你是职业规划助手，对用户用第一人称「我」直接回复；"
            "draft 是内部提纲，融入正文后勿出现「系统提示」「系统需要」等措辞。"
            + over_limit_hint
        ),
        "user_message": user_message,
        "chat_history": chat_history or [],
        "messages_meta": meta,
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
    }
    if session_state.get("list_type") == "pipeline":
        from career_os.harness.session_activity import build_session_activity

        payload["pipeline"] = pipeline_analyze_payload(session_state, user_message)
        payload["session_activity"] = build_session_activity(session_state)
    user = json.dumps(payload, ensure_ascii=False)
    return _coordinator_system(), user


def synthesize_with_llm(
    user_message: str,
    draft_text: str,
    session_state: dict[str, Any],
    last_worker_result: dict[str, Any] | None,
) -> str | None:
    if not lc_client.llm_enabled():
        return None
    system, user = build_synthesis_messages(
        user_message,
        draft_text,
        session_state,
        last_worker_result,
    )
    try:
        return invoke_text(system, user, role=LLMRole.COORDINATOR).strip()
    except Exception:
        return None
