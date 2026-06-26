from typing import Any, Callable

from career_os.agents.schemas.workers import validate_structured_output
from career_os.agents.state.worker import WorkerState


def run_worker_emit(
    state: WorkerState,
    *,
    raw_output: dict[str, Any] | None = None,
) -> WorkerState:
    """校验并产出 Worker 状态。

    state（工作者状态）保存 worker_id、目标、消息和结构化输出；
    raw_output（原始输出）是可选的待校验结果，优先级高于 state 中已有输出。
    返回值是更新后的 WorkerState：校验成功时 status 为 completed，失败时写入 error。
    """
    payload = raw_output or state.get("structured_output") or {}
    validated, error = validate_structured_output(state["worker_id"], payload)
    if error:
        return {
            **state,
            "status": "failed",
            "error": error,
        }
    return {
        **state,
        "status": "completed",
        "structured_output": validated or {},
        "error": None,
    }


def finalize_worker_result(worker_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """把 Worker 原始 payload 封装成统一结果。

    worker_id（工作者标识）用于选择对应的结构化 schema；
    payload（负载）是 Worker 生成的业务字段。返回值包含 worker_id、status、
    structured_output 和 error，供 Coordinator 聚合使用。
    """
    state: WorkerState = {
        "worker_id": worker_id,
        "goal": "",
        "context": {},
        "messages": [],
        "structured_output": payload,
        "status": "pending",
    }
    emitted = run_worker_emit(state, raw_output=payload)
    return {
        "worker_id": worker_id,
        "status": emitted["status"],
        "structured_output": emitted.get("structured_output"),
        "error": emitted.get("error"),
    }


def build_stub_worker_runner(
    responses: dict[str, dict[str, Any]],
) -> Callable[[str, str, dict[str, Any], dict[str, Any]], dict[str, Any]]:
    """构造测试用 Worker runner。

    responses（响应表）按 worker_id 提供固定输出。返回值 runner（运行函数）
    会忽略真实 LLM 和工具调用，直接把固定 payload 包装成标准 Worker 结果。
    """
    def runner(
        worker_id: str,
        goal: str,
        session_state: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """执行一个测试 Worker。

        worker_id（工作者标识）用于从 responses 中取固定响应；
        goal（目标）在缺省响应中作为 user_visible_summary；
        session_state（会话状态）和 context（上下文）保留签名兼容性。
        返回值是 finalize_worker_result 生成的标准结果。
        """
        payload = responses.get(worker_id, {"user_visible_summary": goal})
        return finalize_worker_result(worker_id, payload)

    return runner
