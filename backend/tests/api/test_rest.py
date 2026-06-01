import importlib

import pytest
from fastapi.testclient import TestClient

from career_os.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("LLM_API_KEY", "")
    import career_os.config as config_mod
    import career_os.platform.store.profile as profile_mod
    import career_os.platform.store.session as session_mod
    import career_os.platform.store.task as task_mod
    from career_os.agents.lc import models as models_mod

    importlib.reload(config_mod)
    importlib.reload(profile_mod)
    importlib.reload(session_mod)
    importlib.reload(task_mod)
    models_mod.model_settings.__init__()
    return TestClient(app)


def test_new_session(client):
    r = client.post("/v1/sessions/new")
    assert r.status_code == 200
    assert r.json()["session_id"].startswith("sess_")


def test_list_sessions_empty_rebuilds(client):
    r = client.get("/v1/sessions")
    assert r.status_code == 200
    assert r.json()["sessions"] == []


def test_new_session_does_not_delete_old(client):
    a = client.post("/v1/sessions/new").json()["session_id"]
    from career_os.platform.store.session import SessionStore

    SessionStore().append_message(a, "user", "first session message")
    b = client.post("/v1/sessions/new").json()["session_id"]
    listed = client.get("/v1/sessions").json()["sessions"]
    ids = {s["session_id"] for s in listed}
    assert {a, b} <= ids


def test_get_messages_returns_history(client):
    sid = client.post("/v1/sessions/new").json()["session_id"]
    from career_os.platform.store.session import SessionStore

    store = SessionStore()
    store.append_message(sid, "user", "hello history")
    store.append_message(sid, "assistant", "hi back")

    r = client.get(f"/v1/sessions/{sid}/messages")
    assert r.status_code == 200
    messages = r.json()["messages"]
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "hello history"


def test_generate_title_without_llm_returns_503(client):
    sid = client.post("/v1/sessions/new").json()["session_id"]
    r = client.post(f"/v1/sessions/{sid}/generate-title")
    assert r.status_code == 503
    assert r.json()["detail"] == "llm_unavailable"


def test_generate_title_locked_when_user_title(client, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    import career_os.agents.lc.models as models_mod

    models_mod.model_settings.__init__()

    sid = client.post("/v1/sessions/new").json()["session_id"]
    client.patch(f"/v1/sessions/{sid}", json={"title": "锁定标题"})
    r = client.post(f"/v1/sessions/{sid}/generate-title")
    assert r.status_code == 409
    assert r.json()["detail"] == "title_locked"


def test_generate_title_force_overrides_user(client, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    import career_os.agents.lc.models as models_mod

    models_mod.model_settings.__init__()

    sid = client.post("/v1/sessions/new").json()["session_id"]
    from career_os.platform.store.session import SessionStore

    store = SessionStore()
    store.append_message(sid, "user", "讨论 Go 后端职业规划")

    client.patch(f"/v1/sessions/{sid}", json={"title": "用户自定义"})
    monkeypatch.setattr(
        "career_os.platform.store.session_title._generate_title_llm",
        lambda _content: "LLM 新标题",
    )

    r = client.post(f"/v1/sessions/{sid}/generate-title", params={"force": "true"})
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "LLM 新标题"
    assert body["title_source"] == "auto"


def test_patch_title_and_archived(client):
    sid = client.post("/v1/sessions/new").json()["session_id"]
    r = client.patch(
        f"/v1/sessions/{sid}",
        json={"title": "我的会话", "archived": True},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "我的会话"
    assert body["title_source"] == "user"
    assert body["archived"] is True

    listed = client.get("/v1/sessions").json()["sessions"]
    assert sid not in {s["session_id"] for s in listed}

    archived_list = client.get("/v1/sessions", params={"archived": "true"}).json()[
        "sessions"
    ]
    assert sid in {s["session_id"] for s in archived_list}


def test_delete_session_404_after(client):
    sid = client.post("/v1/sessions/new").json()["session_id"]
    assert client.delete(f"/v1/sessions/{sid}").status_code == 200
    assert client.get(f"/v1/sessions/{sid}/messages").status_code == 404
    assert client.get(f"/v1/sessions/{sid}").status_code == 404


def test_delete_session_409_when_chat_in_progress(client):
    sid = client.post("/v1/sessions/new").json()["session_id"]
    import career_os.harness.orchestrator as orch_mod

    orch_mod._active_runs[sid] = True
    try:
        r = client.delete(f"/v1/sessions/{sid}")
        assert r.status_code == 409
        assert r.json()["detail"] == "chat_in_progress"
        assert client.get(f"/v1/sessions/{sid}").status_code == 200
    finally:
        orch_mod._active_runs.pop(sid, None)


def test_invalid_session_id_format_400(client):
    r = client.get("/v1/sessions/not-a-valid-id/messages")
    assert r.status_code == 400
    assert r.json()["detail"] == "invalid_session_id"


def test_profile_onboarding(client):
    r = client.post(
        "/v1/profile/onboarding",
        json={"basic": {"name": "测试"}, "intent": {"target_city": "上海"}},
    )
    assert r.status_code == 200
    profile = client.get("/v1/profile").json()
    assert profile["basic"]["name"] == "测试"


def test_explore_intake_submit(client):
    sid = client.post("/v1/sessions/new").json()["session_id"]
    payload = {
        "session_id": sid,
        "resume_text": (
            "李四\n3年工作经验\n当前薪资：25k\n期望岗位：Java开发\n期望薪资：30k\n"
            "项目：订单系统重构"
        ),
        "years_of_experience": "6年",
    }
    r = client.post("/v1/profile/explore-intake", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["submitted"] is True
    status = client.get("/v1/profile/explore-intake/status").json()
    assert status["submitted"] is True
    assert status["intake"]["resolved_fields"]["years_of_experience"] == "6年"
    assert status["intake"]["resolved_fields"]["target_role"] == "Java开发"
    assert status["intake"]["resolved_fields"]["current_salary"] == "25K"


def test_new_session_creates_pipeline_list(client):
    sid = client.post("/v1/sessions/new").json()["session_id"]
    body = client.get("/v1/tasks", params={"session_id": sid}).json()
    assert len(body["lists"]) == 1
    assert body["lists"][0]["list_type"] == "pipeline"
    assert body["lists"][0]["current_phase"] == "explore"
    assert len(body["lists"][0]["milestones"]) == 5
    assert body["all_tasks_completed"] is False


def test_explore_intake_submit_keeps_single_pipeline_list(client):
    sid = client.post("/v1/sessions/new").json()["session_id"]
    payload = {
        "session_id": sid,
        "resume_text": "张三\n3年经验\n期望岗位：后端开发\n项目：订单系统",
        "years_of_experience": "3年",
    }
    r = client.post("/v1/profile/explore-intake", json=payload)
    assert r.status_code == 200

    tasks = client.get("/v1/tasks", params={"session_id": sid}).json()
    pipeline = [lst for lst in tasks["lists"] if lst["list_type"] == "pipeline"]
    assert len(pipeline) == 1
    assert pipeline[0]["status"] == "active"
    assert tasks["active_list_id"] == pipeline[0]["list_id"]

    client.post("/v1/profile/explore-intake", json=payload)
    tasks2 = client.get("/v1/tasks", params={"session_id": sid}).json()
    assert len([l for l in tasks2["lists"] if l["list_type"] == "pipeline"]) == 1


def test_chat_explore_intake_event(client):
    session = client.post("/v1/sessions/new").json()["session_id"]

    with client.stream(
        "POST",
        "/v1/chat",
        json={"session_id": session, "message": "帮我理清职业方向"},
        headers={"Accept": "text/event-stream"},
    ) as response:
        body = "".join(response.iter_text())

    assert "event: explore_intake" in body
    assert "初探信息表" in body


def test_explore_repeat_gate_when_intake_already_submitted(client):
    sid = client.post("/v1/sessions/new").json()["session_id"]
    payload = {
        "session_id": sid,
        "resume_text": (
            "李四\n3年工作经验\n当前薪资：25k\n期望岗位：Java开发\n期望薪资：30k\n"
            "项目：订单系统重构"
        ),
        "years_of_experience": "6年",
    }
    client.post("/v1/profile/explore-intake", json=payload)

    with client.stream(
        "POST",
        "/v1/chat",
        json={"session_id": sid, "message": "帮我理清职业方向"},
        headers={"Accept": "text/event-stream"},
    ) as response:
        body = "".join(response.iter_text())

    assert "event: explore_intake" not in body
    assert "再次" in body or "explore_repeat" in body


def test_chat_jd_gate_chain(client):
    session = client.post("/v1/sessions/new").json()["session_id"]
    client.post(
        "/v1/profile/onboarding",
        json={"basic": {"name": "E2E"}, "intent": {"target_city": "上海"}},
    )
    import career_os.platform.store.profile as profile_mod

    profile_mod.ProfileStore().patch(
        [
            {
                "path": "exploration.completed_at",
                "value": "2026-05-31T00:00:00Z",
                "op": "set",
            },
            {
                "path": "exploration.intake.submitted_at",
                "value": "2026-05-31T00:00:00Z",
                "op": "set",
            },
        ]
    )
    from career_os.harness.pipeline_gates import jump_to_phase, set_explore_gate_confirmed
    from career_os.platform.store.session import SessionStore

    session_store = SessionStore()
    state = session_store.get_state(session)
    set_explore_gate_confirmed(state, True)
    list_id = state.get("list_id")
    assert list_id
    jump_to_phase(session, list_id, "resume_strategy", state)
    session_store.update_state(session, state)

    def chat(message: str) -> str:
        with client.stream(
            "POST",
            "/v1/chat",
            json={"session_id": session, "message": message},
            headers={"Accept": "text/event-stream"},
        ) as response:
            assert response.status_code == 200
            return "".join(response.iter_text())

    body1 = chat("请评估这个 JD：后端工程师，要求 Kubernetes")
    assert "event: done" in body1

    body2 = chat("继续制定策略")
    assert "是否确认" in body2 or "optimize" in body2

    body3 = chat("确认优化")
    assert "event: done" in body3
    assert "context_usage" in body3

    outputs = client.get("/v1/outputs").json().get("outputs_index") or []
    assert len(outputs) >= 1


def test_chat_sse_events(client):
    with client.stream(
        "POST",
        "/v1/chat",
        json={"message": "你好"},
        headers={"Accept": "text/event-stream"},
    ) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())
    assert "event: session" in body
    assert "event: token" in body
    assert "event: done" in body


def test_ping_expired_returns_410_disk_intact(client, monkeypatch):
    monkeypatch.setenv("SESSION_IDLE_TTL", "1")
    import career_os.config as config_mod

    importlib.reload(config_mod)

    sid = client.post("/v1/sessions/new").json()["session_id"]
    from datetime import UTC, datetime, timedelta

    from career_os.platform.store.session import SessionStore

    store = SessionStore()
    old = (datetime.now(UTC) - timedelta(seconds=5)).isoformat()
    store.update_state(sid, {"last_activity_at": old})

    r = client.post(f"/v1/sessions/{sid}/ping")
    assert r.status_code == 410
    assert r.json()["detail"] == "session_expired"
    assert store.get_state(sid)["last_activity_at"] == old

    assert client.get(f"/v1/sessions/{sid}/messages").status_code == 200


def test_chat_without_session_id_creates_and_indexes(client):
    with client.stream(
        "POST",
        "/v1/chat",
        json={"message": "hi"},
        headers={"Accept": "text/event-stream"},
    ) as response:
        assert response.status_code == 200
        "".join(response.iter_text())

    listed = client.get("/v1/sessions").json()["sessions"]
    assert len(listed) >= 1
    assert listed[0]["title"] == "hi"
    assert listed[0]["title_source"] == "fallback"


def test_get_tasks_by_session_id(client):
    sid = client.post("/v1/sessions/new").json()["session_id"]
    r = client.get("/v1/tasks", params={"session_id": sid})
    assert r.status_code == 200
    body = r.json()
    assert body["session_id"] == sid
    assert len(body["lists"]) == 1
    assert body["lists"][0]["list_type"] == "pipeline"
    assert body["lists"][0]["current_phase"] == "explore"
    assert len(body["lists"][0]["milestones"]) == 5
    assert body["all_tasks_completed"] is False


def test_get_tasks_by_session_id_all_completed(client):
    sid = client.post("/v1/sessions/new").json()["session_id"]
    from career_os.platform.store.task import TaskStore

    store = TaskStore()
    pipeline_id = store.get_active_list_id_for_session(sid)
    assert pipeline_id
    store.abandon_task_list(pipeline_id)
    list_id = store.create_task_list(sid, list_type="plan", status="active")
    assert isinstance(list_id, str)
    store.create_task(list_id, "milestone_1", "Done step")
    store.complete_task(list_id, "milestone_1")

    r = client.get("/v1/tasks", params={"session_id": sid})
    assert r.status_code == 200
    body = r.json()
    assert body["all_tasks_completed"] is True
    assert body["active_list_id"] == list_id


def test_get_tasks_without_session_id_returns_400_object(client):
    r = client.get("/v1/tasks")
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "session_id_required"


def test_get_tasks_invalid_session_id_400_object(client):
    r = client.get("/v1/tasks", params={"session_id": "bad-id"})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "invalid_session_id"


def test_chat_sse_llm_stream_multiple_tokens(client, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    import career_os.agents.lc.models as models_mod

    models_mod.model_settings.__init__()

    def fake_stream(*args, **kwargs):
        yield from ["第一段", "第二段", "第三段"]

    monkeypatch.setattr("career_os.api.chat.stream_text", fake_stream)

    with client.stream(
        "POST",
        "/v1/chat",
        json={"message": "你好"},
        headers={"Accept": "text/event-stream"},
    ) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())

    assert body.count("event: token") >= 3
