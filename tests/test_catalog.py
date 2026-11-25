"""Slice U0: the read-only routes the screens need (no model call)."""

import pytest
from fastapi.testclient import TestClient

from rulestorm.api import app, get_store
from rulestorm.fixture import restore_demo
from rulestorm.store import Store


@pytest.fixture
def http(tmp_path):
    store = Store(str(tmp_path / "test.db"))
    restore_demo(store)
    app.dependency_overrides[get_store] = lambda: store
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_a_template_gives_its_own_words_people_and_parameters(http) -> None:
    curfew = http.get("/api/templates/hostel_curfew")
    assert curfew.status_code == 200
    t = curfew.json()
    assert t["ref"] == "hostel_curfew@1" and t["calendar"]["step_label"] == "night"
    assert t["terms"]["request"] == "late-entry request" and len(t["people"]) == 10
    assert {"id", "role", "label"} <= set(t["people"][0])
    assert any(r["llm"] is False and r["rules"] for r in t["roles"])  # rule-run roles are marked
    kinds = {p["name"]: p["kind"] for p in t["parameters"]}
    assert kinds["warden_capacity_per_night"] == "environment" and kinds["curfew_time"] == "policy"
    cap = next(p for p in t["parameters"] if p["name"] == "warden_capacity_per_night")
    assert (cap["min"], cap["max"]) == (0, 20)
    assert t["counterfactual_parameters"] == ["warden_capacity_per_night"]

    attendance = http.get("/api/templates/attendance").json()
    assert attendance["counterfactual_parameters"] == ["office_capacity_per_week", "checkpoint_week"]
    assert attendance["terms"]["check_failed"] == "not eligible"


@pytest.mark.parametrize("name", ["nope", "..%2Fpyproject", "attendance.json"])
def test_only_a_shipped_template_can_be_named(http, name) -> None:
    assert http.get(f"/api/templates/{name}").status_code == 404


def test_a_stored_blueprint_can_be_read_back_and_a_missing_one_is_404(http) -> None:
    run = http.get("/api/runs/demo").json()
    record = http.get(f"/api/blueprints/{run['blueprint_id']}")
    assert record.status_code == 200
    bp = record.json()
    assert bp["id"] == run["blueprint_id"] and bp["approved"] is True and bp["status"] == "valid"
    values = bp["blueprint"]["values"]
    assert "working" in values["profiles"] and values["checkpoint_week"] == 6
    assert bp["blueprint"]["facts"] and bp["blueprint"]["assumptions"]
    assert http.get("/api/blueprints/B-missing").status_code == 404
