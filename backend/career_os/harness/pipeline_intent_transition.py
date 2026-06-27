"""由用户意图驱动的 pipeline 阶段切换，采用规则表并满足前置条件 B。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import re

from career_os.harness.jd_prerequisites import check_jd_prerequisites, is_jd_intent
from career_os.harness.micro_classifier import classify
from career_os.harness.micro_classifier import is_chat_only_intent
from career_os.harness.micro_classifier_rules import match_pipeline_intent_rule_ids
from career_os.harness.pipeline_gates import PipelineGateError, is_explore_gate_confirmed
from career_os.harness.pipeline_gates import jump_to_phase
from career_os.harness.pipeline_jd_context import has_jd_context
from career_os.harness.pipeline_routing import get_current_phase, is_pipeline_session
from career_os.harness.pipeline_phase_transition import apply_list_phase
from career_os.platform.pipeline_constants import JUMP_TARGET_PHASES, PIPELINE_PHASES

PHASE_RANK: dict[str, int] = {phase: index for index, phase in enumerate(PIPELINE_PHASES)}

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


_JUMP_TARGET_WORKERS: dict[str, tuple[str, ...]] = {
    "explore": ("identity", "capability"),
    "market": ("market",),
    "jd_analysis": ("opportunity",),
    "resume_strategy": ("strategy",),
}


def _is_small_talk(user_message: str) -> bool:
    """判断用户消息是否只是简单寒暄。

    user_message（用户消息）会去掉标点和空白后匹配寒暄短语。返回值为 True 表示不触发阶段切换。
    """
    text = user_message.strip().lower()
    if not text:
        return True
    normalized = re.sub(r"[!！。.?？~～,\，、\s]+", "", text)
    return normalized in _SMALL_TALK_PHRASES


@dataclass(frozen=True)
class IntentTransition:
    """描述一条用户意图到 pipeline 阶段的切换规则。

    from_phases（允许起点阶段）、to_phase（目标阶段）、rule_id（规则标识）、
    preconditions（前置条件集合）和 suggested_workers（建议 Worker）共同定义一次可执行切换。
    """
    from_phases: frozenset[str]
    to_phase: str
    rule_id: str
    preconditions: frozenset[str]
    suggested_workers: tuple[str, ...]


# 规则表顺序：多个规则命中时，选择 PHASE_RANK[to_phase] 最高的目标阶段。
INTENT_TRANSITIONS: tuple[IntentTransition, ...] = (
    IntentTransition(
        frozenset({"resume_strategy"}),
        "resume_optimize",
        "intent_resume_optimize",
        frozenset({"P0", "P5", "P6"}),
        ("resume", "asset"),
    ),
    IntentTransition(
        frozenset({"jd_analysis", "market"}),
        "resume_strategy",
        "intent_resume_strategy",
        frozenset({"P0", "P1", "P3", "P6"}),
        ("strategy",),
    ),
    IntentTransition(
        frozenset({"jd_analysis", "market"}),
        "resume_strategy",
        "intent_declare_agent_project",
        frozenset({"P0", "P1", "P2", "P6"}),
        ("strategy",),
    ),
    IntentTransition(
        frozenset({"explore", "market"}),
        "jd_analysis",
        "intent_jd_eval",
        frozenset({"P0", "P1", "P2", "P4", "P6"}),
        ("opportunity",),
    ),
    IntentTransition(
        frozenset({"explore"}),
        "market",
        "intent_market",
        frozenset({"P0", "P4", "P6"}),
        ("market",),
    ),
)


def _explore_gate_precondition(session_state: dict[str, Any]) -> bool:
    """检查是否已满足离开 explore 的 gate 前置条件。"""
    if is_explore_gate_confirmed(session_state):
        return True
    closure = session_state.get("explore_closure") or {}
    return bool(closure.get("completed"))


def _check_precondition(
    precondition_id: str,
    session_state: dict[str, Any],
    user_message: str,
    *,
    chat_history: list[dict[str, str]] | None = None,
) -> bool:
    """检查单个阶段切换前置条件是否满足。

    precondition_id（前置条件标识）对应 P0-P6；session_state（会话状态）提供 list/gate；
    user_message（用户消息）和 chat_history（聊天历史）用于判断 JD 上下文与闲聊。
    """
    # P0：必须绑定 pipeline 任务列表。
    if precondition_id == "P0":
        return bool(session_state.get("list_id")) and is_pipeline_session(session_state)
    # P1：进入 JD/简历链路前必须满足 JD 前置条件。
    if precondition_id == "P1":
        ready, _ = check_jd_prerequisites(session_state)
        return ready
    # P2：必须能从本轮消息或历史中找到 JD 上下文。
    if precondition_id == "P2":
        return has_jd_context(session_state, user_message, chat_history=chat_history)
    # P3：既要有 JD 上下文，也要明确命中“做简历策略”的规则。
    if precondition_id == "P3":
        return has_jd_context(
            session_state, user_message, chat_history=chat_history
        ) and "intent_resume_strategy" in match_pipeline_intent_rule_ids(user_message)
    # P4：离开探索前必须确认探索完成 gate。
    if precondition_id == "P4":
        return _explore_gate_precondition(session_state)
    # P5：进入简历优化前必须确认优化 gate。
    if precondition_id == "P5":
        flags = (session_state.get("gates") or {}).get("flags") or {}
        return bool(flags.get("optimize_confirmed"))
    # P6：寒暄消息不触发业务阶段切换。
    if precondition_id == "P6":
        return not _is_small_talk(user_message)
    return False


def _preconditions_met(
    transition: IntentTransition,
    session_state: dict[str, Any],
    user_message: str,
    *,
    chat_history: list[dict[str, str]] | None = None,
) -> bool:
    """检查一条切换规则的所有前置条件是否满足。"""
    return all(
        _check_precondition(
            pid, session_state, user_message, chat_history=chat_history
        )
        for pid in transition.preconditions
    )


def _resolve_via_rules(
    current_phase: str,
    session_state: dict[str, Any],
    user_message: str,
    *,
    chat_history: list[dict[str, str]] | None = None,
) -> IntentTransition | None:
    """根据硬规则解析用户意图对应的 pipeline 阶段切换。"""
    # 先用硬规则从用户消息中提取可能命中的规则 id。
    rule_ids = set(match_pipeline_intent_rule_ids(user_message))
    # 没有命中任何规则时，直接交给上层回退到分类器。
    if not rule_ids:
        return None
    # best（最佳切换）用于保存当前可用候选中目标阶段最靠后的切换。
    best: IntentTransition | None = None
    best_rank = -1
    # 遍历所有预定义切换规则，逐条过滤是否适用于本轮。
    for transition in INTENT_TRANSITIONS:
        # 用户消息没有命中该规则时跳过。
        if transition.rule_id not in rule_ids:
            continue
        # 当前阶段不在该规则允许的起点阶段内时跳过。
        if current_phase not in transition.from_phases:
            continue
        # 前置条件不满足时跳过，避免越过 JD、gate、上下文等业务约束。
        if not _preconditions_met(
            transition, session_state, user_message, chat_history=chat_history
        ):
            continue
        # 多条规则同时可用时，选择目标阶段优先级最高的一条。
        rank = PHASE_RANK.get(transition.to_phase, -1)
        if rank > best_rank:
            best_rank = rank
            best = transition
    # 没有可用规则时返回 None；否则返回优先级最高的阶段切换。
    return best


def _resolve_via_classifier(
    current_phase: str,
    session_state: dict[str, Any],
    user_message: str,
) -> IntentTransition | None:
    """通过轻量分类器解析用户意图对应的 pipeline 阶段切换。

    current_phase（当前阶段）是切换起点；session_state（会话状态）提供历史结果和 gate；
    user_message（用户消息）是分类器输入。返回值是可执行的 IntentTransition 或 None。
    """
    # 先读取已完成 Worker 摘要，供分类器判断当前上下文是否足够。
    prior = session_state.get("prior_results") or {}
    # 调用 pipeline_phase_intent 分类器，尝试从用户消息中识别目标阶段。
    data = classify(
        "pipeline_phase_intent",
        user_message,
        context={
            "current_phase": current_phase,
            "prior_workers": list(prior.keys()),
            "has_jd_context": has_jd_context(session_state, user_message),
            "gates_pending": (session_state.get("gates") or {}).get("pending"),
        },
    )
    # 分类器没有给出合法目标阶段时，表示无法通过分类器解析阶段切换。
    target = data.get("target_phase")
    if not target or target not in PIPELINE_PHASES:
        return None
    # 显式跳转目标允许回退或跨阶段，但目标等于当前阶段时不需要切换。
    if target in JUMP_TARGET_PHASES:
        if target == current_phase:
            return None
        # 优先复用规则表中已有的合法跳转定义。
        for transition in INTENT_TRANSITIONS:
            if transition.to_phase != target:
                continue
            if current_phase not in transition.from_phases:
                continue
            if not _preconditions_met(transition, session_state, user_message):
                continue
            return transition
        # 规则表没有覆盖该跳转时，临时构造一个跳转 transition，后续由 jump_to_phase 做 gate 校验。
        return IntentTransition(
            frozenset({current_phase}),
            target,
            f"intent_jump_{target}",
            frozenset(),
            _JUMP_TARGET_WORKERS.get(target, tuple()),
        )
    # resume_optimize 必须通过明确规则和 gate 确认进入(人工确认)，不能只依赖分类器。
    if target == "resume_optimize":
        return None
    # 普通阶段推进必须匹配预定义规则，并满足对应前置条件。
    for transition in INTENT_TRANSITIONS:
        if transition.to_phase != target:
            continue
        if current_phase not in transition.from_phases:
            continue
        if not _preconditions_met(transition, session_state, user_message):
            continue
        return transition
    # 没有找到可执行的阶段切换时，返回 None。
    return None


def resolve_intent_phase_transition(
    user_message: str,
    session_state: dict[str, Any],
    *,
    chat_history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """返回阶段切换元数据，不写入磁盘。"""
    # 先读取当前阶段，后续所有候选切换都以它作为起点。
    current = get_current_phase(session_state) or "explore"
    # empty（空结果）表示本轮不触发阶段切换，调用方可以直接继续原流程。
    empty: dict[str, Any] = {
        "applied": False,
        "from_phase": current,
        "to_phase": None,
        "rule_id": None,
        "suggested_workers": [],
        "source": None,
    }
    # 非 pipeline 会话不处理阶段切换。
    if not is_pipeline_session(session_state):
        return empty
    # 有待确认 gate 时，优先等待用户确认，不切换阶段。
    gates = session_state.get("gates") or {}
    if gates.get("pending"):
        return empty
    # 用户明确要求只聊天时，不进入 pipeline 阶段切换。
    if is_chat_only_intent(user_message):
        return empty
    # 纯闲聊不触发阶段切换。
    if _is_small_talk(user_message):
        return empty

    # 第一优先级走硬规则，命中后可以得到确定的目标阶段和建议 Worker。
    transition = _resolve_via_rules(
        current, session_state, user_message, chat_history=chat_history
    )
    source = "rule" if transition else None
    # 硬规则没有命中时，再回退到轻量分类器。
    if not transition:
        transition = _resolve_via_classifier(current, session_state, user_message)
        source = "classifier" if transition else None
    # 两层都没有命中时，本轮不切换阶段。
    if not transition:
        return empty

    target = transition.to_phase
    # 显式跳转目标允许回退或跨阶段，由 apply_intent_phase_transition 统一执行 gate 校验。
    if target in JUMP_TARGET_PHASES:
        return {
            "applied": False,
            "from_phase": current,
            "to_phase": target,
            "rule_id": transition.rule_id,
            "suggested_workers": list(transition.suggested_workers),
            "source": source,
        }
    # 普通阶段推进只允许向后走；目标不晚于当前阶段时忽略。
    if PHASE_RANK.get(target, -1) <= PHASE_RANK.get(current, -1):
        return empty

    # 返回可执行的候选阶段切换；这里只描述意图，不写磁盘。
    return {
        "applied": False,
        "from_phase": current,
        "to_phase": target,
        "rule_id": transition.rule_id,
        "suggested_workers": list(transition.suggested_workers),
        "source": source,
    }


def apply_intent_phase_transition(
    user_message: str,
    session_state: dict[str, Any],
    *,
    chat_history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """应用用户意图触发的 pipeline 阶段切换。"""
    # 先解析本轮用户消息是否指向某个目标阶段。
    resolved = resolve_intent_phase_transition(
        user_message, session_state, chat_history=chat_history
    )
    # 没有目标阶段时，不做任何跳转。
    if not resolved.get("to_phase"):
        return resolved

    current = resolved["from_phase"]
    target = resolved["to_phase"]
    # 目标阶段等于当前阶段时，视为无需跳转。
    if target == current:
        return resolved

    list_id = session_state.get("list_id")
    # list_id（任务列表标识）存在时，同步更新 TaskStore；不存在时只更新 session_state 中的切换记录。
    if list_id:
        # 显式跳转阶段走 jump_to_phase，用统一的 pipeline gate 做拦截。
        if target in JUMP_TARGET_PHASES:
            jump_result = jump_to_phase(
                session_state.get("session_id") or "",
                list_id,
                target,
                session_state,
            )
            # 被 gate 拦住时，只把错误写回解析结果，不推进阶段。
            if isinstance(jump_result, PipelineGateError):
                resolved["applied"] = False
                resolved["error_code"] = jump_result.code
                resolved["error_message"] = jump_result.message
                return resolved
        else:
            # 非显式跳转阶段走普通阶段推进，直接更新任务列表当前阶段。
            apply_list_phase(list_id, target)

    # 阶段切换成功后，把建议 Worker 和最近一次切换记录写回 session_state。
    session_state["intent_suggested_workers"] = resolved.get("suggested_workers") or []
    session_state["last_phase_transition"] = {
        "from_phase": current,
        "to_phase": target,
        "rule_id": resolved.get("rule_id"),
        "source": resolved.get("source"),
    }
    resolved["applied"] = True
    return resolved
