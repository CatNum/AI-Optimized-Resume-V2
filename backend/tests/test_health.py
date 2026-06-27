from fastapi.testclient import TestClient
from career_os.main import app


def test_healthz():
    """验证 healthz 场景。"""
    r = TestClient(app).get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
