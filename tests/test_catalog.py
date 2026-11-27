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
    assert t["ref"] == "hostel_curfew@2" and t["calendar"]["step_label"] == "night"
    assert t["terms"]["request"] == "late-entry request" and len(t["people"]) == 10
    assert {"id", "role", "label"} <= set(t["people"][0])
    assert any(r["llm"] is False and r["rules"] for r in t["roles"])  # rule-run roles are marked
    kinds = {p["name"]: p["kind"] for p in t["parameters"]}
    assert kinds["warden_capacity_per_night"] == "environment" and kinds["curfew_time"] == "policy"
    cap = next(p for p in t["parameters"] if p["name"] == "warden_capacity_per_night")
    assert (cap["min"], cap["max"]) == (0, 20)
    # Slice M8b: one environment value or one single-value policy value (no text, no lists).
    assert t["counterfactual_parameters"][0] == "warden_capacity_per_night"
    assert {"curfew_time", "warning_at", "exceptional_causes", "excused_counting"} <= set(t["counterfactual_parameters"])

    attendance = http.get("/api/templates/attendance").json()
    assert attendance["counterfactual_parameters"][:2] == ["office_capacity_per_week", "checkpoint_week"]
    assert "excused_counting" in attendance["counterfactual_parameters"]
    assert "exception_rule" not in attendance["counterfactual_parameters"]  # text
    assert "slack_min" not in attendance["counterfactual_parameters"]  # a per-person profile value
    assert attendance["terms"]["check_failed"] == "not eligible"


def test_a_template_shows_how_rulestorm_reads_the_rule(http) -> None:
    """Slice M8b: the readings, each with the parameter that sets it, if any."""
    r = http.get("/api/templates/attendance").json()["readings"]
    count = r["counts"][0]
    assert count["count"] == "attendance_pct" and count["excused"]["parameter"] == "excused_counting"
    assert count["excused"]["default"] == "remove" and set(count["excused"]["sentences"]) == {"remove", "count_as_met"}
    kinds = {k["id"]: k for k in r["disruption_kinds"]}
    assert kinds["transport"]["routine"] is False and kinds["transport"]["leaves_proof"] is False
    assert kinds["work_shift_clash"]["routine"] is True and kinds["work_shift_clash"]["obligation"]["label"]
    request = r["request_types"][0]
    assert request["decided_by"] == "rule" and request["decision_rule"]["parameter"] == "decision_rule"
    assert request["decision_rule"]["sentences"]["approve_if_covered_missed"].startswith("The attendance office")
    assert request["exceptional"]["choices"] == ["unforeseen_only", "any_documented"]  # no decider_judges by rule
    assert request["proof"]["default"] is False and request["deadline"]["default"] == 0
    assert r["parameters"] == ["decision_rule", "exceptional_causes", "excused_counting", "filing_deadline",
                               "proof_required"]
    assert r["template_readings"] == ["routine", "leaves_proof", "obligation"]

    curfew = http.get("/api/templates/hostel_curfew").json()["readings"]["request_types"][0]
    assert curfew["decided_by"] == "llm" and curfew["decision_rule"] is None
    assert curfew["exceptional"]["default"] == "decider_judges" and "decider_judges" in curfew["exceptional"]["choices"]


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
