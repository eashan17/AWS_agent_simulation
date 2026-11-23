from fastapi.testclient import TestClient

from rulestorm.api import app


def test_health_returns_ok() -> None:
    response = TestClient(app).get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True}
