"""Slice 19: how the AI people adapted, found by rules over a run's records (no model call)."""

import pytest
from fastapi.testclient import TestClient

from rulestorm.adaptation import adaptations
from rulestorm.api import app, get_store
from rulestorm.core.model import load_template
from rulestorm.fixture import restore_demo
from rulestorm.store import Store

ATTENDANCE = load_template("attendance")


def ev(seq, type_, actor, period, step, payload=None, change=None):
    return {"event_id": f"E-{seq:04d}", "seq": seq, "type": type_, "actor": actor, "period": period, "step": step,
            "payload": payload or {}, "state_change": change or {}, "caused_by": []}


def obstacle(seq, step, delay, people):
    return ev(seq, "obstacle", "environment", 1, step, {"duty": "attend_class", "delay": delay, "people": people,
                                                        "description": "bus strike"})


def record(seq, step, person, outcome):
    return ev(seq, "duty_recorded", "faculty", 1, step, {"duty": "attend_class", "person": person, "outcome": outcome},
              {f"record.attend_class.{person}.{step}": {"from": None, "to": outcome}})


def buffer(seq, step, person, old, new):
    return ev(seq, "attribute_set", person, 1, step, {"attribute": "travel_buffer_min"},
              {f"travel_buffer_min.{person}": {"from": old, "to": new}})


def decision(seq, step, person, strategy):
    return ev(seq, "decision", person, 1, step, {"strategy": strategy, "reason": "r"})


def test_a_raised_buffer_is_shown_with_the_session_it_saved() -> None:
    events = [obstacle(1, 1, 45, ["working"]), buffer(2, 1, "working", 15, 45), record(3, 1, "working", "met"),
              obstacle(4, 2, 90, ["working"]), record(5, 2, "working", "missed")]  # 90 > 45: not this change's doing
    [a] = [x for x in adaptations(ATTENDANCE, events) if x["kind"] == "value_changed"]
    assert (a["person"], a["from"], a["to"], a["event_id"], a["label"]) == ("working", 15, 45, "E-0002", "recorded fact")
    [effect] = a["effects"]
    assert effect["event_ids"] == ["E-0001", "E-0003"]
    assert "recorded present despite a delay of 45" in effect["text"] and "with the old 15 they would have been absent" in effect["text"]


def test_a_lowered_buffer_is_shown_with_the_session_it_cost_and_a_same_value_is_not_a_change() -> None:
    events = [buffer(1, 1, "commuter", 60, 60), buffer(2, 1, "family", 40, 20),
              obstacle(3, 2, 30, ["family"]), record(4, 2, "family", "missed")]
    found = [x for x in adaptations(ATTENDANCE, events) if x["kind"] == "value_changed"]
    assert [a["person"] for a in found] == ["family"]  # commuter's 60 -> 60 isn't one
    assert "recorded absent after a delay of 30; the old 40 would have covered it" in found[0]["effects"][0]["text"]


def test_a_record_made_before_the_change_is_not_its_effect() -> None:
    events = [obstacle(1, 1, 45, ["working"]), record(2, 1, "working", "missed"), buffer(3, 2, "working", 15, 45)]
    [a] = [x for x in adaptations(ATTENDANCE, events) if x["kind"] == "value_changed"]
    assert a["effects"] == []


def test_firsts_are_counted_once_per_person_and_kind() -> None:
    events = [ev(1, "request_filed", "family", 1, 1, {"person": "family"}),
              ev(2, "request_filed", "family", 1, 2, {"person": "family"}),
              ev(3, "response_given", "advisor", 1, 2, {"to": "working"})]
    firsts = [x for x in adaptations(ATTENDANCE, events) if x["kind"] == "first_action"]
    assert [(f["person"], f["event_id"]) for f in firsts] == [("family", "E-0001"), ("advisor", "E-0003")]
    assert firsts[0]["text"].startswith("family filed an exception request for the first time")


def test_a_new_strategy_counts_but_a_rewording_does_not() -> None:
    events = [decision(1, 1, "resident", "Maintain perfect attendance by overcoming minor transport issues."),
              decision(2, 2, "resident", "Maintain attendance by attempting to overcome transport issues where possible."),
              decision(3, 3, "resident", "Formally request exceptions for every recorded absence.")]
    [shift] = [x for x in adaptations(ATTENDANCE, events) if x["kind"] == "strategy_shift"]
    assert shift["event_id"] == "E-0003" and shift["previous_event_id"] == "E-0002"
    assert shift["label"] == "AI interpretation" and shift["to"].startswith("Formally request")


@pytest.fixture
def http(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    restore_demo(store)
    app.dependency_overrides[get_store] = lambda: store
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_the_route_reads_the_demo_run_and_a_missing_run_is_404(http) -> None:
    body = http.get("/api/runs/demo/adaptations").json()
    kinds = {a["kind"] for a in body["adaptations"]}
    assert "value_changed" not in kinds  # its only buffer change is 60 -> 60
    assert {"first_action", "strategy_shift"} <= kinds
    assert sum(body["by_person"].values()) == len(body["adaptations"])
    assert http.get("/api/runs/nope/adaptations").status_code == 404
