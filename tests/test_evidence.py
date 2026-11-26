"""Slice 9: the evidence behind a finding, in chain order, labelled, in the template's own terms."""

import copy
import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rulestorm import evidence as evidence_module
from rulestorm.api import app, get_store
from rulestorm.core.model import load_template
from rulestorm.core.term import simulate
from rulestorm.detect import detect
from rulestorm.evidence import calculation, evidence
from rulestorm.policy import PolicyInput
from rulestorm.store import Store
from test_core_term import VALUES, decider
from test_detect import STRIKE, curfew_decider, strike_decider

LABELS = {"recorded fact", "calculated", "AI interpretation"}


@pytest.fixture(scope="module")
def attendance():
    return load_template("attendance")


def run(template, values, decide):
    events = [e.model_dump() for e in simulate(template, values, decide).events]
    return events, [f.model_dump() for f in detect("L-test", events, template)]


def test_the_bottleneck_evidence_follows_the_chain_with_labels_and_the_check_recomputed(attendance) -> None:
    events, findings = run(attendance, VALUES, decider)
    finding = findings[1]  # the working student: skipped because of the strike, then asked
    ev = evidence(finding, events, attendance)
    assert [s.event_id for s in ev.steps] == finding["chain"] and ev.title == finding["title"]
    by_type = {s.type: s for s in ev.steps}
    assert {s.label for s in ev.steps} == LABELS
    assert by_type["obstacle"].label == "recorded fact" and by_type["duty_recorded"].label == "recorded fact"
    assert by_type["decision"].label == "AI interpretation" and by_type["decision"].interpretation == "scripted"
    assert by_type["queue_over_capacity"].label == "calculated" and by_type["check_evaluated"].label == "calculated"
    assert all(s.interpretation is None for s in ev.steps if s.label != "AI interpretation")
    assert by_type["duty_recorded"].state_change  # each step carries its state change
    # in the template's own words
    assert "working: absent, session 5 (week 3)" in by_type["duty_recorded"].text
    assert by_type["request_filed"].text.startswith("working filed exception request R2 for session 5")
    check = by_type["check_evaluated"]
    assert check.text.startswith("exam eligibility for working, week 6: attendance 11 / 12 = 91.7% (needs >= 80) → eligible")
    calc = check.calculation
    assert calc.recorded.text == "attendance 11 / 12 = 91.7%" and calc.if_pending_approved.text == "attendance 11 / 11 = 100%"
    assert calc.pending_requests == ["R2"] and calc.matches_recorded
    assert [s.calculation for s in ev.steps if s.type != "check_evaluated"] == [None] * (len(ev.steps) - 1)


def test_the_check_failed_evidence_recomputes_the_failing_figure(attendance) -> None:
    events, findings = run(attendance, STRIKE, strike_decider)
    ev = evidence(findings[0], events, attendance)
    calc = ev.steps[-1].calculation
    assert calc.recorded.text == "attendance 3 / 6 = 50%" and calc.outcome == "not eligible" and calc.matches_recorded
    assert calc.if_pending_approved.value == 50.0 and calc.pending_requests == []  # nothing was waiting
    assert sum(s.type == "obstacle" for s in ev.steps) == 3


def test_a_figure_that_differs_from_the_recorded_one_is_flagged(attendance) -> None:
    events, findings = run(attendance, VALUES, decider)
    check = copy.deepcopy(next(e for e in events if e["event_id"] == findings[0]["check_event_id"]))
    check["payload"]["count"]["met"] += 1  # what the check says no longer follows from the records
    assert calculation(check, events, attendance).matches_recorded is False


def test_curfew_evidence_uses_the_curfew_words() -> None:
    curfew = load_template("hostel_curfew")
    values = json.loads((Path(__file__).parent / "cases" / "curfew_r2.json").read_text(encoding="utf-8"))["values"]
    values = {**values, "disruptions": [{"kind": "lab_overrun", "period": 1, "steps": [2], "people": ["researcher"],
                                         "delay": 60, "description": "experiment overruns"}]}
    events, findings = run(curfew, values, curfew_decider)
    ev = evidence(findings[0], events, curfew)
    text = " ".join(s.text for s in ev.steps)
    assert "late-entry request R1 for night 2" in text and "experiment overruns" in text
    for word in ("session", "absent", "exception", "attendance", "eligib"):
        assert word not in text.lower(), word
    calc = ev.steps[-1].calculation
    assert calc.recorded.text == "late returns: 1" and calc.outcome == "in good standing" and calc.matches_recorded
    assert calc.if_pending_approved.text == "late returns: 0"


def test_evidence_holds_no_template_words() -> None:
    source = Path(evidence_module.__file__).read_text(encoding="utf-8").lower()
    for word in ("attendance", "student", "session", "absen", "exception", "curfew", "night", "resident", "warden"):
        assert word not in source.split('"""', 2)[2], word  # the module docstring may give examples


def test_the_evidence_route_answers_in_under_a_second(tmp_path, attendance) -> None:
    events, findings = run(attendance, VALUES, decider)
    store = Store(str(tmp_path / "test.db"))
    policy = store.save_policy(PolicyInput(text="x", purpose="y", environment="z"))
    store._conn().execute("INSERT INTO blueprints (id, policy_id, model_id, status, record, created_at) "
                          "VALUES ('B-x', ?, 'fake', 'valid', '{}', 'now')", (policy.id,))
    store.create_run("L-test", "B-x", "attendance@1", 10, "fake")
    store.add_events("L-test", events)
    store.add_findings("L-test", findings)
    app.dependency_overrides[get_store] = lambda: store
    try:
        http = TestClient(app)
        http.get("/api/findings/L-test-F1/evidence")  # the first call checks the template once
        started = time.monotonic()
        response = http.get("/api/findings/L-test-F1/evidence")
        assert response.status_code == 200 and time.monotonic() - started < 1.0
        body = response.json()
        assert [s["event_id"] for s in body["steps"]] == findings[0]["chain"]
        assert all(s["label"] in LABELS and "state_change" in s for s in body["steps"])
        assert body["steps"][-1]["calculation"]["matches_recorded"] is True
        assert http.get("/api/findings/L-test-F9/evidence").status_code == 404
    finally:
        app.dependency_overrides.clear()


# --- slice M7b: obligations in the evidence ------------------------------------------------------


def test_the_evidence_names_the_cost_and_recounts_the_loss_at_the_end_of_the_chain() -> None:
    from rulestorm.core.cases import play_case

    case = json.loads((Path(__file__).parent / "cases" / "shift_clash.json").read_text(encoding="utf-8"))
    template = load_template("attendance")
    events = [e.model_dump() for e in play_case(case, template)[1].events]
    [lost] = [f for f in detect("L-test", events, template) if f.kind == "obligation_lost"]
    ev = evidence(lost.model_dump(), events, template)
    last = ev.steps[-1]
    assert last.type == "obligation_lost" and last.label == "calculated"
    assert last.text == ("working met 'attend class' during the clash once more than their limit of 2 missed "
                         "work shift: job lost, session 10 (week 5)")
    calc = last.obligation_calculation
    assert (calc.obligation, calc.missed, calc.limit, calc.lost, calc.matches_recorded) == ("work shift", 3, 2, "job lost", True)
    assert last.calculation is None
    words = evidence_module._Words(template)
    missed = next(e for e in events if e["type"] == "obligation_missed")
    assert words.sentence(missed) == ("working met 'attend class' during the clash, so missed their work shift: "
                                      "1 of 2 allowed, session 4 (week 2)")
    went = next(e for e in events if e["type"] == "duty_recorded" and e["payload"]["plan"] == "default_obligation")
    assert "(no plan during the clash, so they went to the other obligation)" in words.sentence(went)
    assert "not a valid reason" in words.sentence(went)
