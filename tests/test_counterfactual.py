"""Slice 13: rerun the same term with one environment condition changed, and compare (fake model)."""

import pytest

from rulestorm.counterfactual import LABEL, measures
from test_runner import approved, client, store, wait_until_finished  # noqa: F401 - pytest fixtures


def finished_run(http, model, blueprint_id: str) -> str:
    model.gate.set()
    run_id = http.post("/api/runs", json={"blueprint_id": blueprint_id}).json()["run_id"]
    wait_until_finished(http, run_id)
    return run_id


def blueprint_count(store) -> int:
    return store._conn().execute("SELECT COUNT(*) FROM blueprints").fetchone()[0]


def test_a_counterfactual_changes_one_condition_and_compares_both_runs(client, approved, store) -> None:
    http, model = client
    base = finished_run(http, model, approved.id)

    posted = http.post(f"/api/runs/{base}/counterfactual", json={"parameter": "office_capacity_per_week", "value": 5})
    assert posted.status_code == 200, posted.text
    body = posted.json()
    assert body["changed"] == {"parameter": "office_capacity_per_week", "from": 2, "to": 5}
    assert body["label"] == LABEL and body["run_id"] != base

    new = store.get_blueprint(body["blueprint_id"])
    assert new.approved and new.counterfactual_of == approved.id and new.parent_id is None
    old_values, new_values = approved.blueprint.values, new.blueprint.values
    assert [k for k in old_values if old_values[k] != new_values[k]] == ["office_capacity_per_week"]
    assert new.blueprint.label_for(__import__("rulestorm.core.model", fromlist=["x"]).load_template("attendance"),
                                   "office_capacity_per_week")[0] == "fact"
    assert store.list_variants(approved.id) == []  # never mixed in with the stress variants

    wait_until_finished(http, body["run_id"])
    compared = http.get(f"/api/runs/{base}/compare/{body['run_id']}")
    assert compared.status_code == 200
    result = compared.json()
    assert result["label"] == "within-model evidence, not real-world causality"
    assert result["matched"] is True
    assert result["differences"] == [{"parameter": "office_capacity_per_week", "kind": "environment", "from": 2, "to": 5}]
    assert [r["run_id"] for r in result["runs"]] == [base, body["run_id"]]
    for run in result["runs"]:
        assert {"queue_length", "waiting_time", "checks"} <= set(run)
        assert run["checks"] and all({"person", "passed", "value"} <= set(c) for c in run["checks"])


@pytest.mark.parametrize("change, says", [
    ({"parameter": "threshold_pct", "value": 70}, "policy value"),
    ({"parameter": "office_capacity_per_week", "value": 51}, "not allowed"),
    ({"parameter": "office_capacity_per_week", "value": 2}, "already 2"),
    ({"parameter": "office_capacity_per_week", "value": "5"}, "whole number"),
    ({"parameter": "disruptions", "value": 1}, "a list"),
    ({"parameter": "printer_count", "value": 1}, "no parameter"),
])
def test_anything_but_one_allowed_environment_value_is_refused_and_saves_nothing(
        client, approved, store, change, says) -> None:
    http, model = client
    base = finished_run(http, model, approved.id)
    before = blueprint_count(store)
    refused = http.post(f"/api/runs/{base}/counterfactual", json=change)
    assert refused.status_code == 422 and says in refused.json()["detail"], refused.text
    assert blueprint_count(store) == before


def test_an_unknown_run_is_404_and_a_busy_server_is_409_before_anything_is_saved(client, approved, store) -> None:
    http, model = client
    missing = http.post("/api/runs/L-missing/counterfactual", json={"parameter": "office_capacity_per_week", "value": 5})
    assert missing.status_code == 404
    model.gate.clear()
    running = http.post("/api/runs", json={"blueprint_id": approved.id}).json()["run_id"]
    before = blueprint_count(store)
    busy = http.post(f"/api/runs/{running}/counterfactual", json={"parameter": "office_capacity_per_week", "value": 5})
    assert busy.status_code == 409 and busy.json()["run_id"] == running
    assert blueprint_count(store) == before
    assert http.get(f"/api/runs/{running}/compare/{running}").status_code == 409  # not finished yet
    assert http.get(f"/api/runs/{running}/compare/L-missing").status_code == 404
    model.gate.set()


def test_measures_read_queue_waiting_and_checks_from_the_events() -> None:
    events = [
        {"type": "request_filed", "period": 1, "payload": {}},
        {"type": "request_filed", "period": 1, "payload": {}},
        {"type": "request_filed", "period": 2, "payload": {}},
        {"type": "queue_processed", "period": 1, "payload": {"pending": ["R2", "R3"]}},
        {"type": "queue_over_capacity", "period": 1, "payload": {}},
        {"type": "request_decided", "period": 1, "payload": {"waited_periods": 0}},
        {"type": "request_decided", "period": 3, "payload": {"waited_periods": 2}},
        {"type": "check_evaluated", "period": 6, "payload": {"check": "exam", "person": "worker", "passed": False,
                                                              "threshold": 80, "count": {"value": 72.7},
                                                              "pending_requests": ["R3"]}},
    ]
    m = measures(events)
    assert m["queue_length"] == {"longest": 2, "periods_over_capacity": 1}
    assert m["waiting_time"] == {"unit": "periods", "decided": 2, "mean": 1, "longest": 2, "never_decided": 1}
    assert m["checks"] == [{"check": "exam", "person": "worker", "period": 6, "value": 72.7, "threshold": 80,
                            "passed": False, "pending_requests": 1}]
    assert m["check_failed"] == ["worker"] and m["pending_at_check"] == 1
