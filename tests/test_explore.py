"""Stress variants wait for their port to the template format (slice L8); until then every
entry point says so plainly. Slice L8 replaces this file with the ported 6c tests."""

import json

import pytest
from fastapi.testclient import TestClient

from rulestorm import explore
from rulestorm.agents import NotPortedYet
from rulestorm.api import app, get_blueprint_model, get_store
from rulestorm.llm import FakeModel
from rulestorm.policy import PolicyInput, approve_blueprint, create_blueprint
from rulestorm.store import Store
from test_blueprint import FILL, PICK


@pytest.fixture
def store(tmp_path) -> Store:
    return Store(str(tmp_path / "test.db"))


@pytest.fixture
def parent(store):
    policy = store.save_policy(PolicyInput(text="80% attendance", purpose="y", environment="strikes happen"))
    record = create_blueprint(store, policy.id, FakeModel([PICK, json.dumps(FILL)]))
    return approve_blueprint(store, record.id)


def test_variants_say_not_yet_until_slice_l8(store, parent) -> None:
    with pytest.raises(NotPortedYet, match="slice L8"):
        explore.propose_variants(store, parent.id)
    with pytest.raises(NotPortedYet, match="slice L8"):
        explore.run_variants(store, parent.id)


def test_variants_route_answers_409_not_yet_and_404_for_unknown(store, parent) -> None:
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_blueprint_model] = lambda: FakeModel([])
    try:
        http = TestClient(app)
        response = http.post(f"/api/blueprints/{parent.id}/variants")
        assert response.status_code == 409 and "slice L8" in response.json()["detail"]
        assert http.post("/api/blueprints/B-missing/variants").status_code == 404
    finally:
        app.dependency_overrides.clear()
