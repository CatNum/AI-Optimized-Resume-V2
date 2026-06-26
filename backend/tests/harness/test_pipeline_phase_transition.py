from career_os.harness.explore_closure import PHASE_SEGMENT_COMPLETE
from career_os.harness.pipeline_phase_transition import (
    infer_phase_after_repeat_decline,
    phase_after_worker_segment_complete,
    prior_worker_segment_complete,
    structured_segment_complete,
)


def test_structured_segment_complete():
    """test_structured_segment_complete（测试 structured segment complete）的函数说明。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    assert structured_segment_complete({"phase_status": PHASE_SEGMENT_COMPLETE})
    assert not structured_segment_complete({"phase_status": "in_progress"})


def test_infer_phase_after_repeat_decline_empty_prior():
    """test_infer_phase_after_repeat_decline_empty_prior（测试 infer phase after repeat decline empty prior）的函数说明。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    assert infer_phase_after_repeat_decline({}) == "market"


def test_infer_phase_after_repeat_decline_market_only():
    """test_infer_phase_after_repeat_decline_market_only（测试 infer phase after repeat decline market only）的函数说明。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    prior = {"market": {"phase_status": PHASE_SEGMENT_COMPLETE}}
    assert infer_phase_after_repeat_decline(prior) == "market"
    assert prior_worker_segment_complete(prior, "market")


def test_infer_phase_after_repeat_decline_with_opportunity():
    """test_infer_phase_after_repeat_decline_with_opportunity（测试 infer phase after repeat decline with opportunity）的函数说明。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    prior = {
        "market": {"phase_status": PHASE_SEGMENT_COMPLETE},
        "opportunity": {"phase_status": PHASE_SEGMENT_COMPLETE},
    }
    assert infer_phase_after_repeat_decline(prior) == "jd_analysis"


def test_phase_after_worker_segment_complete():
    """test_phase_after_worker_segment_complete（测试 phase after worker segment complete）的函数说明。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    assert (
        phase_after_worker_segment_complete(
            "market", {"phase_status": PHASE_SEGMENT_COMPLETE}
        )
        == "market"
    )
    assert (
        phase_after_worker_segment_complete(
            "opportunity", {"phase_status": PHASE_SEGMENT_COMPLETE}
        )
        == "jd_analysis"
    )
    assert phase_after_worker_segment_complete("identity", {"phase_status": PHASE_SEGMENT_COMPLETE}) is None
    assert phase_after_worker_segment_complete("market", {"phase_status": "in_progress"}) is None
    assert (
        phase_after_worker_segment_complete(
            "strategy", {"phase_status": PHASE_SEGMENT_COMPLETE}
        )
        == "resume_strategy"
    )
