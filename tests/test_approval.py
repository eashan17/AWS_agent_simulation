import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from rulestorm.api import app, get_store
from rulestorm.llm import FakeModel
from rulestorm.policy import (
    Blueprint,
    BlueprintFrozen,
    BlueprintInvalid,
    BlueprintNotApproved,
    PolicyInput,
    approve_blueprint,
    create_blueprint,
    require_approved,
)
from rulestorm.store import Store
from test_blueprint import VALID


@pytest.fixture
def store(tmp_path) -> Store:
    return Store(str(tmp_path / "test.db"))


@pytest.fixture
def blueprint(store):
    policy = store.save_policy(PolicyInput(text="80% attendance", purpose="y", environment="z"))
    return create_blueprint(store, policy.id, FakeModel([json.dumps(VALID)]))


@pytest.fixture
def http(store):
    app.dependency_overrides[get_store] = lambda: store
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_approve_sets_approved(store, blueprint) -> None:
    assert approve_blueprint(store, blueprint.id).approved is True
    assert store.get_blueprint(blueprint.id).approved is True
    assert approve_blueprint(store, blueprint.id).approved is True  # twice is fine


def test_approved_blueprint_cannot_be_edited(store, blueprint) -> None:
    edited = Blueprint.model_validate(VALID).model_copy(deep=True)
    edited.scenario.admin_capacity_per_week = 9
    assert store.update_blueprint(blueprint.id, edited).blueprint.scenario.admin_capacity_per_week == 9

    approve_blueprint(store, blueprint.id)
    with pytest.raises(BlueprintFrozen):
        store.update_blueprint(blueprint.id, Blueprint.model_validate(VALID))
    # The database refuses it too, even for code that skips the store method.
    conn = sqlite3.connect(store.db_path)
    with pytest.raises(sqlite3.IntegrityError, match="frozen"):
        conn.execute("UPDATE blueprints SET record = '{}' WHERE id = ?", (blueprint.id,))
    with pytest.raises(sqlite3.IntegrityError, match="frozen"):
        conn.execute("DELETE FROM blueprints WHERE id = ?", (blueprint.id,))
    assert store.get_blueprint(blueprint.id).blueprint.scenario.admin_capacity_per_week == 9


def test_invalid_blueprint_cannot_be_approved(store) -> None:
    policy = store.save_policy(PolicyInput(text="x", purpose="y", environment="z"))
    invalid = create_blueprint(store, policy.id, FakeModel(["not json", "{}"]))
    with pytest.raises(BlueprintInvalid):
        approve_blueprint(store, invalid.id)


def test_run_on_unapproved_blueprint_refused(store, blueprint, http) -> None:
    with pytest.raises(BlueprintNotApproved):
        require_approved(store, blueprint.id)
    response = http.post("/api/runs", json={"blueprint_id": blueprint.id})
    assert response.status_code == 409
    assert response.json() == {"detail": "blueprint not approved"}


def test_approve_route_then_run_passes_the_check(blueprint, http) -> None:
    response = http.post(f"/api/blueprints/{blueprint.id}/approve")
    assert response.status_code == 200 and response.json()["approved"] is True
    # Approved: the approval check passes; the runner itself arrives in slice 7a.
    assert http.post("/api/runs", json={"blueprint_id": blueprint.id}).status_code == 501
    assert http.post("/api/runs", json={"blueprint_id": "B-missing"}).status_code == 404
