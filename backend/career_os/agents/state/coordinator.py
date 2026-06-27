from typing import Any, TypedDict


class CoordinatorState(TypedDict, total=False):
    """
    CoordinatorState（协调器状态）描述主 Agent 图在一轮对话中的共享状态。
    """

    messages: list[dict[str, str]]  # 消息列表
    messages_meta: dict[str, Any]  # 消息元数据
    session_id: str  # 会话标识
    session_state: dict[str, Any]  # 会话状态
    worker_index: list[dict[str, Any]]  # Worker 索引
    pending_workers: list[str]  # 待执行 Worker 队列
    current_worker_id: str | None  # 当前 Worker 标识
    last_worker_result: dict[str, Any] | None  # 最近 Worker 结果
    stop_delegate: bool  # 是否停止委托
    synthesis_text: str  # 合成回复文本
    synthesis_draft: str  # 合成回复草稿
    delegate_count: int  # 委托次数
    user_message: str  # 用户消息
    request_context: dict[str, Any]  # 请求上下文
