import pytest
from fastapi.testclient import TestClient

from rulestorm.api import app, get_store
from rulestorm.store import Store


@pytest.fixture
def client(tmp_path):
    store = Store(str(tmp_path / "test.db"))
    app.dependency_overrides[get_store] = lambda: store
    yield TestClient(app), store
    app.dependency_overrides.clear()


def test_post_policy_saves_and_returns_id(client) -> None:
    http, store = client
    response = http.post("/api/policies", json={"text": "x", "purpose": "y", "environment": "z"})
    assert response.status_code == 200
    body = response.json()
    assert body["id"].startswith("P-")
    assert store.get_policy(body["id"]).text == "x"


def test_text_over_2000_chars_is_rejected(client) -> None:
    http, _ = client
    response = http.post(
        "/api/policies", json={"text": "a" * 2001, "purpose": "y", "environment": "z"}
    )
    assert response.status_code == 422


def test_empty_field_is_rejected(client) -> None:
    http, _ = client
    response = http.post("/api/policies", json={"text": "x", "purpose": "", "environment": "z"})
    assert response.status_code == 422
