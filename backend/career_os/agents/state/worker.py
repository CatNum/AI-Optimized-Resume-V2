from typing import Any, TypedDict


class WorkerState(TypedDict, total=False):
    """
    WorkerState（工作者状态）描述单个 Worker 的 ReAct 执行状态。
    """

    worker_id: str  # 工作者标识
    goal: str  # 执行目标
    context: dict[str, Any]  # 执行上下文
    session_state: dict[str, Any]  # 会话状态
    iteration: int  # 当前迭代次数
    max_iterations: int  # 最大迭代次数
    messages: list[dict[str, Any]]  # 消息列表
    structured_output: dict[str, Any]  # 结构化输出
    status: str  # 状态
    error: str | None  # 错误信息
