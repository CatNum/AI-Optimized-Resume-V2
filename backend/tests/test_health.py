from fastapi.testclient import TestClient
from career_os.main import app


def test_healthz():
    r = TestClient(app).get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
