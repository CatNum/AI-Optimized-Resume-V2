from fastapi.testclient import TestClient
from career_os.main import app


def test_healthz():
    """test_healthz（测试 healthz）的函数说明。

    该函数用于验证对应业务场景的行为是否符合预期。"""
    r = TestClient(app).get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
