"""SPIKE acceptance (architecture 07 §9).

1. Coordinator delegate without skill_name; Worker receives skill_index via
   capability_bundle — see ``tests/harness/test_delegate_capability_bundle.py``.
2. Worker ReAct loads two skills; audit trace has >=2 ``tool.call`` for
   ``load_skill`` (and optionally ``skill.load``).
3. Harness rejects wrong worker loading skill — see
   ``tests/harness/test_load_skill.py::test_load_skill_rejects_wrong_worker``.
"""

import importlib
from unittest.mock import MagicMock, patch

import pytest

from career_os.agents.graphs.workers.react_runner import run_worker_react
from career_os.harness.executor import Harness
from career_os.platform.store.profile import ProfileStore
from tests.conftest import seed_jd_ready_profile


@pytest.fixture
def harness(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    import career_os.config as config_mod
    import career_os.platform.store.profile as profile_mod

    importlib.reload(config_mod)
    importlib.reload(profile_mod)
    seed_jd_ready_profile(ProfileStore())
    return Harness()


def _tool_call(name: str, arguments: str, call_id: str) -> MagicMock:
    tc = MagicMock()
    tc.function.name = name
    tc.function.arguments = arguments
    tc.id = call_id
    return tc


def test_react_loads_two_skills_trace(harness, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-key")

    delegated = harness.delegate_worker(
        "coordinator",
        "strategy",
        "制定 JD 投递策略",
        {
            "session_id": "s1",
            "prior_results": {},
            "gates": {"flags": {}},
            "list_type": "pipeline",
            "explore_gate_confirmed": True,
            "explore_closure": {"completed": True},
            "intake_status": {"submitted_at": "2026-05-31T00:00:00Z"},
        },
        context={"list_type": "pipeline"},
        session_id="s1",
    )
    assert not hasattr(delegated, "code")
    capability_bundle = delegated["context"]["capability_bundle"]

    tc_load_a = _tool_call(
        "load_skill",
        '{"name": "career-jd-alignment", "mode": "jd_alignment"}',
        "call_load_1",
    )
    tc_load_b = _tool_call(
        "load_skill",
        '{"name": "career-jd-alignment", "mode": "jd_plan"}',
        "call_load_2",
    )
    final_msg = MagicMock()
    final_msg.content = (
        '{"user_visible_summary":"策略推演完成",'
        '"path_options":[{"id":"path_a","label":"稳健投递"}],'
        '"three_horizons":{"now":"对齐JD","next":"1-2年","long":"3-5年"}}'
    )
    final_msg.tool_calls = None

    with patch("career_os.agents.graphs.workers.react_runner.litellm.completion") as mocked:
        mocked.side_effect = [
            MagicMock(
                choices=[
                    MagicMock(
                        message=MagicMock(content=None, tool_calls=[tc_load_a]),
                    )
                ]
            ),
            MagicMock(
                choices=[
                    MagicMock(
                        message=MagicMock(content=None, tool_calls=[tc_load_b]),
                    )
                ]
            ),
            MagicMock(choices=[MagicMock(message=final_msg)]),
        ]
        result = run_worker_react(
            harness,
            worker_id="strategy",
            goal="制定 JD 投递策略",
            session_state={"session_id": "s1"},
            context={"capability_bundle": capability_bundle},
        )

    assert result["status"] == "completed"
    assert result["structured_output"]["path_options"]
    assert result["structured_output"]["three_horizons"]

    events = harness.trace.read_events()
    load_skill_calls = [
        e
        for e in events
        if e.get("event") == "tool.call"
        and e.get("tool_name") == "load_skill"
        and e.get("actor") == "strategy"
        and e.get("status") == "ok"
    ]
    assert len(load_skill_calls) >= 2


@pytest.mark.llm
def test_worker_loads_skill_twice_trace_llm(harness):
    """Optional real-LLM SPIKE; skipped without API key."""
    pytest.importorskip("litellm")
    import os

    if not os.environ.get("LLM_API_KEY"):
        pytest.skip("LLM_API_KEY not set")

    delegated = harness.delegate_worker(
        "coordinator",
        "strategy",
        "制定 JD 投递策略",
        {
            "session_id": "s1",
            "prior_results": {},
            "gates": {"flags": {}},
            "list_type": "pipeline",
            "explore_gate_confirmed": True,
            "explore_closure": {"completed": True},
            "intake_status": {"submitted_at": "2026-05-31T00:00:00Z"},
        },
        context={"list_type": "pipeline"},
        session_id="s1",
    )
    assert not hasattr(delegated, "code")
    pytest.skip("Real LLM SPIKE not implemented yet; use mock test_react_loads_two_skills_trace")
