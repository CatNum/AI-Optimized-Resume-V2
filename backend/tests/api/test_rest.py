import importlib

import pytest
from fastapi.testclient import TestClient

from career_os.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    import career_os.config as config_mod

    importlib.reload(config_mod)
    return TestClient(app)


def test_new_session(client):
    r = client.post("/v1/sessions/new")
    assert r.status_code == 200
    assert r.json()["session_id"].startswith("sess_")


def test_profile_onboarding(client):
    r = client.post(
        "/v1/profile/onboarding",
        json={"basic": {"name": "测试"}, "intent": {"target_city": "上海"}},
    )
    assert r.status_code == 200
    profile = client.get("/v1/profile").json()
    assert profile["basic"]["name"] == "测试"


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
            }
        ]
    )

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
