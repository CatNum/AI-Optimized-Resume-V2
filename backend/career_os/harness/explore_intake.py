from __future__ import annotations

from typing import Any

from career_os.harness.explore_intake_fields import pending_field_labels
from career_os.platform.store.profile import ProfileStore
from career_os.platform.store.session import SessionStore


def _intake_from_state(session_state: dict[str, Any] | None) -> dict[str, Any]:
    """按优先级读取初探信息表状态。

    session_state（会话状态）优先提供本轮内存态；如果没有，则按 session 持久化状态、
    session artifacts、profile 旧数据的顺序回退。返回值是 intake（初探信息表）字典。
    """
    state = session_state or {}
    # 本轮 session_state 中已有 intake_status 时，直接使用最新内存态。
    if isinstance(state.get("intake_status"), dict):
        return state.get("intake_status") or {}
    session_id = state.get("session_id")
    if session_id:
        # 其次读取 SessionStore 中持久化的状态，覆盖可能较旧的 artifacts/profile。
        persisted = SessionStore().get_state(session_id)
        if isinstance(persisted.get("intake_status"), dict):
            return persisted.get("intake_status") or {}
        # 再从会话产物 exploration.intake 中读取接口层保存的信息表。
        artifacts = SessionStore().get_artifacts(session_id)
        intake = (artifacts.get("exploration") or {}).get("intake")
        if isinstance(intake, dict):
            return intake
    # 最后兼容旧版 profile.exploration.intake。
    profile = ProfileStore().get(["exploration"])
    legacy = (profile.get("exploration") or {}).get("intake")
    if isinstance(legacy, dict):
        return legacy
    return {}


def resolve_explore_intake(session_state: dict[str, Any] | None = None) -> dict[str, Any]:
    """解析当前会话可用的初探信息表。"""
    return _intake_from_state(session_state)


def explore_intake_submitted(session_state: dict[str, Any] | None = None) -> bool:
    """判断初探信息表是否已经提交。

    session_state（会话状态）用于定位 intake。返回值为 True 表示 intake 中存在 submitted_at。
    """
    intake = resolve_explore_intake(session_state)
    return bool(intake.get("submitted_at"))


def explore_intake_payload(session_state: dict[str, Any] | None = None) -> dict[str, Any]:
    """构造初探信息表上下文负载。

    session_state（会话状态）用于读取已提交的 intake（初探信息）。
    返回值包含是否已提交、待补字段、待补字段中文标签和完整 intake，
    供 Coordinator 分析路由时判断是否阻断初探 Worker。
    """
    intake = resolve_explore_intake(session_state)
    pending = list(intake.get("pending_fields") or [])
    return {
        "explore_intake_submitted": explore_intake_submitted(session_state),
        "explore_intake_pending_fields": pending,
        "explore_intake_pending_labels": pending_field_labels(pending),
        "explore_intake": intake,
    }


def worker_context_from_intake(
    session_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """把初探信息表整理成 Worker 上下文。

    session_state（会话状态）用于读取 intake。返回值包含待补字段、中文标签和已解析字段，
    供探索 Worker 在问题中避开已填写信息。
    """
    intake = resolve_explore_intake(session_state)
    pending = list(intake.get("pending_fields") or [])
    return {
        "explore_intake_pending_fields": pending,
        "explore_intake_pending_labels": pending_field_labels(pending),
        "explore_intake_resolved_fields": intake.get("resolved_fields") or {},
    }


def is_explore_route(result: dict[str, Any]) -> bool:
    """判断路由结果是否属于 pipeline 的探索阶段。

    result（分析结果）提供 list_type、pipeline_phase 和 workers。返回值为 True 表示需要套用
    初探 intake 规则。
    """
    # 只有 pipeline 列表才走新的初探表单约束。
    if result.get("list_type") != "pipeline":
        return False
    # 只有 explore 阶段或尚未显式给出阶段的结果，才被视为探索路由。
    if result.get("pipeline_phase") not in (None, "explore"):
        return False
    workers = result.get("workers") or []
    # workers 为空时也算探索路由，因为它可能只是等待 intake；有 Worker 时必须包含探索 Worker。
    return not workers or any(
        worker_id in {"identity", "capability"} for worker_id in workers
    )


def _gate_flags(session_state: dict[str, Any]) -> dict[str, Any]:
    """读取当前会话 gate flags。"""
    return (session_state.get("gates") or {}).get("flags") or {}


def _deep_explore_completed(session_state: dict[str, Any]) -> bool:
    """判断深度职业初探是否已经完成。

    session_state（会话状态）先检查本会话完成标记、探索闭环和 gate flags；
    都没有时再回退到 profile.exploration.completed_at。
    """
    # 当前会话已有完成时间，说明本轮或历史已经完成探索。
    if session_state.get("explore_completed_at"):
        return True
    closure = session_state.get("explore_closure") or {}
    if closure.get("completed"):
        return True
    flags = _gate_flags(session_state)
    if flags.get("explore_gate_confirmed"):
        return True
    # 最后读取 profile 中的持久化完成时间，兼容跨会话判断。
    profile = ProfileStore().get(["exploration"])
    exploration = profile.get("exploration") or {}
    return bool(exploration.get("completed_at"))


def needs_repeat_intake(session_state: dict[str, Any]) -> bool:
    """判断重复初探是否需要重新填写信息表。

    session_state（会话状态）提供探索完成状态和 gates.flags。
    返回值为 True 表示用户接受重新初探后，还没有提交新的 intake 信息表。
    """
    # 没有完成过深度探索时，不存在“重复初探”语义。
    if not _deep_explore_completed(session_state):
        return False
    flags = _gate_flags(session_state)
    # 用户没有接受重走初探时，不需要重新填写表单。
    if not flags.get("explore_repeat_accepted"):
        return False
    baseline = flags.get("explore_repeat_baseline_at")
    # 没有 baseline 时无法证明已有新表单，因此要求重新填写。
    if not baseline:
        return True
    intake = _intake_from_state(session_state)
    # 新 intake 的 submitted_at 仍等于旧 baseline 时，说明还没提交新的重复初探表单。
    return intake.get("submitted_at") == baseline


def enforce_explore_intake(
    result: dict[str, Any],
    session_state: dict[str, Any],
) -> dict[str, Any]:
    """对探索路由强制执行 intake 信息表规则。

    result（分析结果）是候选 Worker 路由；session_state（会话状态）提供 intake、
    gates 和探索完成状态。返回值可能保留原路由，也可能清空 workers 并标记
    explore_intake_blocked 或 explore_repeat_blocked。
    """
    # 非探索路由不受 intake 规则影响，原样返回。
    if not is_explore_route(result):
        return result

    flags = _gate_flags(session_state)
    # 规范化为 pipeline/explore，后续 Coordinator 可以稳定识别当前列表类型和阶段。
    pipeline_result = {
        **result,
        "list_type": "pipeline",
        "pipeline_phase": result.get("pipeline_phase") or "explore",
    }

    # 用户拒绝重复初探时，探索 Worker 不再继续派发。
    if flags.get("explore_repeat_declined"):
        return {**pipeline_result, "workers": []}

    # 第一次探索前必须先提交 intake，否则阻断 Worker 并交给 synthesize 输出填表引导。
    if not explore_intake_submitted(session_state):
        return {
            **pipeline_result,
            "workers": [],
            "explore_intake_blocked": True,
        }

    # 尚未完成过深度探索且 intake 已提交时，允许探索 Worker 正常执行。
    if not _deep_explore_completed(session_state):
        return pipeline_result

    # 已完成过探索且用户接受重走时，只有提交新 intake 后才允许继续。
    if flags.get("explore_repeat_accepted"):
        if needs_repeat_intake(session_state):
            return {
                **pipeline_result,
                "workers": [],
                "explore_intake_blocked": True,
            }
        return pipeline_result

    # 已完成过探索但用户尚未表态是否重走时，暂停并触发重复初探 gate。
    return {
        **pipeline_result,
        "workers": [],
        "explore_repeat_blocked": True,
    }
