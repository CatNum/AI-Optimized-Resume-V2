from __future__ import annotations

from typing import Any

from career_os.harness.explore_intake_fields import pending_field_labels
from career_os.platform.store.profile import ProfileStore
from career_os.platform.store.session import SessionStore


def _intake_from_state(session_state: dict[str, Any] | None) -> dict[str, Any]:
    """_intake_from_state（内部函数 intake from state）的函数说明。

    session_state（参数）用于向该函数传入运行所需的数据。

    该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
    state = session_state or {}
    if isinstance(state.get("intake_status"), dict):
        return state.get("intake_status") or {}
    session_id = state.get("session_id")
    if session_id:
        persisted = SessionStore().get_state(session_id)
        if isinstance(persisted.get("intake_status"), dict):
            return persisted.get("intake_status") or {}
        artifacts = SessionStore().get_artifacts(session_id)
        intake = (artifacts.get("exploration") or {}).get("intake")
        if isinstance(intake, dict):
            return intake
    profile = ProfileStore().get(["exploration"])
    legacy = (profile.get("exploration") or {}).get("intake")
    if isinstance(legacy, dict):
        return legacy
    return {}


def resolve_explore_intake(session_state: dict[str, Any] | None = None) -> dict[str, Any]:
    """resolve_explore_intake（resolve explore intake）的函数说明。

    session_state（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    return _intake_from_state(session_state)


def explore_intake_submitted(session_state: dict[str, Any] | None = None) -> bool:
    """explore_intake_submitted（explore intake submitted）的函数说明。

    session_state（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
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
    """worker_context_from_intake（worker context from intake）的函数说明。

    session_state（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    intake = resolve_explore_intake(session_state)
    pending = list(intake.get("pending_fields") or [])
    return {
        "explore_intake_pending_fields": pending,
        "explore_intake_pending_labels": pending_field_labels(pending),
        "explore_intake_resolved_fields": intake.get("resolved_fields") or {},
    }


def is_explore_route(result: dict[str, Any]) -> bool:
    """is_explore_route（is explore route）的函数说明。

    result（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    if result.get("list_type") != "pipeline":
        return False
    if result.get("pipeline_phase") not in (None, "explore"):
        return False
    workers = result.get("workers") or []
    return not workers or any(
        worker_id in {"identity", "capability"} for worker_id in workers
    )


def _gate_flags(session_state: dict[str, Any]) -> dict[str, Any]:
    """_gate_flags（内部函数 gate flags）的函数说明。

    session_state（参数）用于向该函数传入运行所需的数据。

    该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
    return (session_state.get("gates") or {}).get("flags") or {}


def _deep_explore_completed(session_state: dict[str, Any]) -> bool:
    """_deep_explore_completed（内部函数 deep explore completed）的函数说明。

    session_state（参数）用于向该函数传入运行所需的数据。

    该函数属于模块内部辅助逻辑，返回值供同模块或调用方继续处理。"""
    if session_state.get("explore_completed_at"):
        return True
    closure = session_state.get("explore_closure") or {}
    if closure.get("completed"):
        return True
    flags = _gate_flags(session_state)
    if flags.get("explore_gate_confirmed"):
        return True
    profile = ProfileStore().get(["exploration"])
    exploration = profile.get("exploration") or {}
    return bool(exploration.get("completed_at"))


def needs_repeat_intake(session_state: dict[str, Any]) -> bool:
    """判断重复初探是否需要重新填写信息表。

    session_state（会话状态）提供探索完成状态和 gates.flags。
    返回值为 True 表示用户接受重新初探后，还没有提交新的 intake 信息表。
    """
    if not _deep_explore_completed(session_state):
        return False
    flags = _gate_flags(session_state)
    if not flags.get("explore_repeat_accepted"):
        return False
    baseline = flags.get("explore_repeat_baseline_at")
    if not baseline:
        return True
    intake = _intake_from_state(session_state)
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
    if not is_explore_route(result):
        return result

    flags = _gate_flags(session_state)
    pipeline_result = {
        **result,
        "list_type": "pipeline",
        "pipeline_phase": result.get("pipeline_phase") or "explore",
    }

    if flags.get("explore_repeat_declined"):
        return {**pipeline_result, "workers": []}

    if not explore_intake_submitted(session_state):
        return {
            **pipeline_result,
            "workers": [],
            "explore_intake_blocked": True,
        }

    if not _deep_explore_completed(session_state):
        return pipeline_result

    if flags.get("explore_repeat_accepted"):
        if needs_repeat_intake(session_state):
            return {
                **pipeline_result,
                "workers": [],
                "explore_intake_blocked": True,
            }
        return pipeline_result

    return {
        **pipeline_result,
        "workers": [],
        "explore_repeat_blocked": True,
    }
