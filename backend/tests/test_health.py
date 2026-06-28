from fastapi.testclient import TestClient
from career_os.main import app


def test_healthz():
    """验证健康检查接口返回正常响应。"""
    r = TestClient(app).get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
