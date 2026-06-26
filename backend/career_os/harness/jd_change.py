from __future__ import annotations

import hashlib
from typing import Any

from career_os.harness.pipeline_gates import PipelineGateError, jump_to_phase
from career_os.platform.store.session import SessionStore
from career_os.platform.store.task import TaskStore


def jd_fingerprint(jd_text: str) -> str:
    """jd_fingerprint（jd fingerprint）的函数说明。

    jd_text（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    normalized = jd_text.strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def apply_jd_fingerprint_change(
    session_id: str,
    list_id: str,
    new_fingerprint: str,
    session_state: dict[str, Any],
) -> PipelineGateError | dict[str, Any]:
    """apply_jd_fingerprint_change（apply jd fingerprint change）的函数说明。

    session_id（参数）、list_id（参数）、new_fingerprint（参数）、session_state（参数）用于向该函数传入运行所需的数据。

    返回值会根据当前业务逻辑返回处理结果，或通过副作用更新相关状态。"""
    store = TaskStore()
    meta = store.get_list_meta(list_id)
    if not meta:
        return PipelineGateError("list_not_found", "Pipeline list not found")
    old = meta.get("related_jd_fingerprint")
    if old == new_fingerprint:
        return {"unchanged": True, "related_jd_fingerprint": new_fingerprint}

    patch_err = store.patch_list_meta(
        list_id, {"related_jd_fingerprint": new_fingerprint}
    )
    if patch_err:
        return PipelineGateError(patch_err.code, patch_err.message)

    result = jump_to_phase(session_id, list_id, "jd_analysis", session_state)
    if isinstance(result, PipelineGateError):
        return result
    SessionStore().update_state(session_id, session_state)
    return {
        "related_jd_fingerprint": new_fingerprint,
        "previous": old,
        "jump": result,
    }
