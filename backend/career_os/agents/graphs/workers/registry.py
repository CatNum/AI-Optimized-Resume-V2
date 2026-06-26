from typing import Any, Callable

from career_os.agents.graphs.workers.react_mocks import mock_run_worker_react
from career_os.agents.graphs.workers.react_runner import run_worker_react
from career_os.agents.lc.client import llm_enabled

WorkerFn = Callable[[Any, str, dict[str, Any], dict[str, Any]], dict[str, Any]]
"""WorkerFn（工作者函数类型）描述底层 Worker 调用签名。"""

REACT_REQUIRED_WORKERS = frozenset(
    {"market", "opportunity", "strategy", "resume", "identity", "capability", "asset"}
)
"""REACT_REQUIRED_WORKERS（需要 ReAct 的工作者集合）列出当前支持的 Worker 类型。"""


def build_harness_worker_runner(
    harness: Any,
    *,
    use_react: bool = True,
    use_react_mocks: bool | None = None,
) -> Callable[[str, str, dict[str, Any], dict[str, Any]], dict[str, Any]]:
    """构造基于 Harness 的 Worker 调度函数。

    harness（运行时工具门面）负责真实工具执行；
    use_react（是否使用 ReAct）控制是否启用 ReAct Worker；
    use_react_mocks（是否使用 mock）为 None 时根据 LLM 配置自动判断。
    返回值 runner（运行函数）按 worker_id 选择真实 ReAct 或 mock ReAct。
    """
    react_mocks = use_react_mocks if use_react_mocks is not None else not llm_enabled()

    def runner(
        worker_id: str,
        goal: str,
        session_state: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """运行一个指定 Worker。

        worker_id（工作者标识）决定具体 Worker 类型；
        goal（目标）是本轮任务；
        session_state（会话状态）提供 session_id 和历史结果；
        context（上下文）提供路由、能力包和业务补充信息。返回值是标准 Worker 结果。
        """
        if not use_react or worker_id not in REACT_REQUIRED_WORKERS:
            return {"worker_id": worker_id, "status": "failed", "error": "unknown worker"}

        if react_mocks:
            return mock_run_worker_react(
                harness,
                worker_id=worker_id,
                goal=goal,
                session_state=session_state,
                context=context,
            )

        if not llm_enabled():
            return {
                "worker_id": worker_id,
                "status": "failed",
                "error": f"LLM_API_KEY is required for {worker_id} ReAct worker",
            }

        return run_worker_react(
            harness,
            worker_id=worker_id,
            goal=goal,
            session_state=session_state,
            context=context,
        )

    return runner
