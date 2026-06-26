from typing import Any, TypedDict


class WorkerState(TypedDict, total=False):
    """WorkerState（工作者状态）描述单个 Worker 的 ReAct 执行状态。

    worker_id（工作者标识）区分 market、resume 等 Worker；
    goal（目标）是本轮 Worker 要完成的任务；
    context（上下文）保存能力包、聊天历史和业务参数；
    session_state（会话状态）保存 session_id 与历史结果；
    iteration（当前迭代次数）记录 ReAct 循环进度；
    max_iterations（最大迭代次数）防止工具调用无限循环；
    messages（消息列表）保存 system/user/assistant/tool 消息；
    structured_output（结构化输出）是 Worker 最终业务结果；
    status（状态）表示 running、completed 或 failed；
    error（错误信息）保存失败原因。
    """
    worker_id: str
    goal: str
    context: dict[str, Any]
    session_state: dict[str, Any]
    iteration: int
    max_iterations: int
    messages: list[dict[str, Any]]
    structured_output: dict[str, Any]
    status: str
    error: str | None
