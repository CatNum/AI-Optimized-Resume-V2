from typing import Any, TypedDict


class CoordinatorState(TypedDict, total=False):
    """CoordinatorState（协调器状态）描述主 Agent 图在一轮对话中的共享状态。

    messages（消息列表）保存对话消息；messages_meta（消息元数据）保存消息统计信息；
    session_id（会话标识）用于关联持久化会话；session_state（会话状态）保存用户画像、
    prior_results 等业务状态；worker_index（工作者索引）描述可调度 Worker；
    pending_workers（待执行工作者）是后续要分发的 Worker 队列；
    current_worker_id（当前工作者标识）记录正在执行的 Worker；
    last_worker_result（最近工作者结果）保存最新 Worker 返回；
    stop_delegate（停止分发标记）控制是否结束 Worker 分发；
    synthesis_text（合成文本）是最终给用户的回复；
    synthesis_draft（合成草稿）是 LLM 合成前的确定性草稿；
    delegate_count（分发次数）统计本轮已调用 Worker 数；
    user_message（用户消息）是本轮用户输入；
    request_context（请求上下文）保存外部传入的运行约束和参数。
    """
    messages: list[dict[str, str]]
    messages_meta: dict[str, Any]
    session_id: str
    session_state: dict[str, Any]
    worker_index: list[dict[str, Any]]
    pending_workers: list[str]
    current_worker_id: str | None
    last_worker_result: dict[str, Any] | None
    stop_delegate: bool
    synthesis_text: str
    synthesis_draft: str
    delegate_count: int
    user_message: str
    request_context: dict[str, Any]
