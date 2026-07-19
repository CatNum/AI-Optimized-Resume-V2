from datetime import UTC, datetime
from unittest.mock import Mock

from career_os.platform.market_research.models import (
    DirectionRetryRun,
    ResearchStage,
    ResearchStatus,
)
from career_os.platform.market_research.service import MarketResearchService
from career_os.platform.market_research.store import MarketResearchStore


def test_continue_or_cancel_marks_orphaned_retry_as_process_interrupted(tmp_path):
    """热重载丢失 Runner（执行线程）后，控制请求不能留下 waiting_user（等待用户）假状态。"""
    store = MarketResearchStore(tmp_path)
    session_store = Mock()
    session_store.session_exists.return_value = False
    service = MarketResearchService(store=store, session_store=session_store)
    retry_id = "research_" + "a" * 32
    session_id = "sess_" + "b" * 32
    retry = DirectionRetryRun(
        retry_id=retry_id,
        parent_research_id="research_" + "c" * 32,
        plan_id="plan_" + "d" * 32,
        origin_session_id=session_id,
        direction_name="LLM Agent 应用开发工程师",
        direction_key="llm-agent",
        status=ResearchStatus.WAITING_USER,
        stage=ResearchStage.COLLECTING_BOSS,
        available_actions=("continue", "cancel"),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    store.write_retry_status(retry)
    store.reserve_active_run(retry_id, session_id, retry.plan_id)

    interrupted = service.continue_research(retry_id, session_id)

    assert interrupted.status is ResearchStatus.FAILED
    assert interrupted.stage is ResearchStage.FINISHED
    assert interrupted.available_actions == ()
    assert interrupted.error is not None
    assert interrupted.error.error_code == "process_interrupted"
    assert store.get_active_run() is None
    assert service.cancel(retry_id, session_id).status is ResearchStatus.FAILED
