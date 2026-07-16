from datetime import UTC, datetime

from career_os.harness.market_plan_intent import revise_plan_from_selection_message
from career_os.platform.market_research.models import (
    DirectionProposal,
    ResearchSnapshot,
    ResearchStage,
    ResearchStatus,
)
from career_os.platform.market_research.plans import MarketResearchPlanStore
from career_os.api.market_research import _active_plan_supersedes_snapshot


def _proposal(name: str) -> DirectionProposal:
    """构造指定名称的最小市场方向提案。"""
    return DirectionProposal(
        direction_name=name,
        boss_keywords=(name,),
        trends_keywords=(name,),
        cities=("北京",),
        experience_basis="total",
        experience_min=3,
        experience_max=5,
    )


def test_selection_message_revises_existing_plan_to_one_direction(tmp_path) -> None:
    """“只调研某方向”原地修订当前方案，而不是另建方案或只回复文字。"""
    store = MarketResearchPlanStore(tmp_path)
    session_id = "sess_" + "1" * 32
    plan = store.create_draft(
        session_id,
        [
            _proposal("LLM Agent 应用开发工程师"),
            _proposal("Multi-Agent 系统工程师"),
            _proposal("Agent 后端架构师"),
        ],
    )

    revised = revise_plan_from_selection_message(
        store,
        plan.plan_id,
        session_id,
        "只调研 LLM Agent 应用开发工程师",
    )

    assert revised is not None
    assert revised.plan_id == plan.plan_id
    assert revised.plan_version == 2
    assert [item.direction_name for item in revised.directions] == [
        "LLM Agent 应用开发工程师"
    ]


def test_new_draft_plan_supersedes_cancelled_snapshot_from_old_plan(tmp_path) -> None:
    """新草稿方案优先于不同方案留下的旧取消快照。"""
    store = MarketResearchPlanStore(tmp_path)
    session_id = "sess_" + "2" * 32
    plan = store.create_draft(session_id, [_proposal("LLM Agent 应用开发工程师")])
    snapshot = ResearchSnapshot(
        research_id="research_" + "3" * 32,
        plan_id="plan_" + "4" * 32,
        origin_session_id=session_id,
        status=ResearchStatus.CANCELLED,
        stage=ResearchStage.FINISHED,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    assert _active_plan_supersedes_snapshot(plan, snapshot) is True


def test_consumed_plan_does_not_hide_its_research_snapshot(tmp_path) -> None:
    """已经消费的方案不遮住由它启动的调研快照。"""
    store = MarketResearchPlanStore(tmp_path)
    session_id = "sess_" + "5" * 32
    draft = store.create_draft(session_id, [_proposal("LLM Agent 应用开发工程师")])
    confirmed = store.confirm(draft.plan_id, session_id)
    consumed = store.consume(confirmed.plan_id, session_id)
    snapshot = ResearchSnapshot(
        research_id="research_" + "6" * 32,
        plan_id=consumed.plan_id,
        origin_session_id=session_id,
        status=ResearchStatus.CANCELLED,
        stage=ResearchStage.FINISHED,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    assert _active_plan_supersedes_snapshot(consumed, snapshot) is False
