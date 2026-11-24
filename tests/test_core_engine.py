"""Slices L2-L3: the general engine, driven only by the template and the blueprint's values."""

import json
from pathlib import Path

import pytest

from rulestorm.core.engine import Engine, Obstacle, run_case
from rulestorm.core.model import TEMPLATES_DIR, Template, load_template

CASE = Path(__file__).parent / "cases" / "student_c.json"
VALUES = {  # test-only values
    "threshold_pct": 80, "request_timing": "after_missed", "partial_at_submit": False,
    "partial_at_decide": False, "decision_rule": "approve_if_covered_missed",
    "office_capacity_per_week": 2, "checkpoint_week": 10,
    "slack_min": {"commuter": 10, "resident": 30, "working": 15, "family": 20},
}


@pytest.fixture
def template() -> Template:
    return load_template("attendance")


@pytest.fixture
def engine(template: Template) -> Engine:
    return Engine(template, VALUES)


def record_through(engine: Engine, last_step: int) -> None:
    for step in range(1, last_step + 1):
        engine.record_step(step)


def test_student_c_case_prints_expected_lines(template: Template) -> None:
    lines = run_case(json.loads(CASE.read_text(encoding="utf-8")), template)
    assert [line.split("  [")[0] for line in lines] == [
        "15/20 = 75.0% (2 exceptions pending)",
        "15/18 = 83.3% (if 2 approved)",
        "student edit_attendance: rejected (permission)",
    ]
    assert all(line.split("  [")[1].startswith("E-") for line in lines)


def test_permission_comes_from_the_template(engine: Engine, template: Template) -> None:
    record_through(engine, 1)
    refused = engine.propose("working", "edit_attendance", 1, student="working", session=1, present=False)
    assert (refused.type, refused.payload["reason"]) == ("action_rejected", "permission")
    assert engine.records[("attend_class", "working", 1)] == "met"
    assert [a.effects[0].kind for a in template.actions if a.id == "edit_attendance"] == ["correct_record"]

    # the same engine code, with a template that lets students edit: now allowed
    raw = json.loads((TEMPLATES_DIR / "attendance.json").read_text(encoding="utf-8"))
    raw["roles"][0]["actions"].append("edit_attendance")
    loose = Engine(Template.model_validate(raw), VALUES)
    record_through(loose, 1)
    allowed = loose.propose("working", "edit_attendance", 1, student="working", session=1, present=False)
    assert allowed.type == "record_corrected"
    assert loose.records[("attend_class", "working", 1)] == "missed"


def test_attend_and_skip_only_plan_and_the_recorder_records(engine: Engine) -> None:
    engine.current_step = 1
    skip = engine.propose("working", "skip", 1, session=1)
    attend = engine.propose("commuter", "attend", 1, session=1)
    assert skip.type == attend.type == "duty_planned"
    assert ("attend_class", "working", 1) not in engine.records  # a plan is not a record

    delay = engine.emit("obstacle", "environment", 1, 1, payload={"delay": 25})
    recorded = {e.payload["person"]: e for e in engine.record_step(
        1, [Obstacle(event_id=delay.event_id, duty="attend_class", people=["commuter", "resident"], delay=25)])}

    assert {p: e.payload["outcome"] for p, e in recorded.items()} == {
        "commuter": "missed",  # planned to attend, 25 min delay > 10 min slack
        "resident": "met",     # 25 min delay but 30 min slack; no plan means planning to attend
        "working": "missed",   # planned to skip
        "family": "met",       # no plan, no obstacle
    }
    assert recorded["commuter"].caused_by == [delay.event_id, attend.event_id]
    assert recorded["working"].caused_by == [skip.event_id]
    assert all(e.actor == "faculty" for e in recorded.values())  # the recorder rule's person

    late = engine.propose("working", "attend", 1, session=1)
    assert late.payload["reason"] == "precondition: occurrence_not_yet"


def test_plans_only_for_the_current_step_and_slack_change(engine: Engine) -> None:
    engine.current_step = 3
    ahead = engine.propose("commuter", "attend", 2, session=4)
    assert ahead.payload["reason"] == "precondition: current_step"
    engine.propose("commuter", "attend", 2, session=3, slack_min=40)
    assert engine.attributes[("commuter", "slack_min")] == 40
    bad = engine.propose("commuter", "attend", 2, session=3, slack_min=500)
    assert bad.payload["reason"].startswith("bad parameters")


def test_after_missed_refuses_a_request_for_an_unrecorded_session(engine: Engine) -> None:
    record_through(engine, 2)
    early = engine.propose("working", "submit_exception_request", 2, sessions=[3], reason="shift")
    assert (early.type, early.payload["reason"]) == ("action_rejected", "precondition: occurrence_recorded")
    filed = engine.propose("working", "submit_exception_request", 1, sessions=[2], reason="shift")
    assert filed.type == "request_filed"
    assert engine.record_event[("attend_class", "working", 2)] in filed.caused_by
    again = engine.propose("working", "submit_exception_request", 1, sessions=[2], reason="shift")
    assert again.payload["reason"] == "already covered"
    other = engine.propose("working", "submit_exception_request", 1, sessions=[2], reason="x")
    assert other.type == "action_rejected"


def test_in_advance_accepts_a_request_for_a_session_not_yet_held(template: Template) -> None:
    engine = Engine(template, {**VALUES, "request_timing": "in_advance"})
    record_through(engine, 2)
    ahead = engine.propose("working", "submit_exception_request", 2, sessions=[3], reason="shift")
    assert ahead.type == "request_filed" and engine.requests["R1"].steps == [3]
    past = engine.propose("working", "submit_exception_request", 2, sessions=[1], reason="shift")
    assert past.payload["reason"] == "precondition: occurrence_not_yet"


def test_rate_leaves_out_approved_and_cancelled_and_counts_pending_as_missed(engine: Engine) -> None:
    for step in (1, 2, 3, 4):
        engine.current_step = step
        if step in (1, 3):
            engine.propose("working", "skip", 1, session=step)
        engine.record_step(step)
    engine.current_step = None
    assert engine.count("attendance_pct", "working").text() == "2/4 = 50.0%"

    engine.propose("working", "submit_exception_request", 2, sessions=[1], reason="shift")
    assert engine.count("attendance_pct", "working").text() == "2/4 = 50.0%"  # pending still counts
    assert engine.count("attendance_pct", "working", assume_pending_approved=True).text() == "2/3 = 66.7%"

    engine.decide_request("R1", "approved", "attendance_admin", 2, rule="test")
    assert engine.count("attendance_pct", "working").text() == "2/3 = 66.7%"  # approved is left out

    cancel = engine.propose("faculty", "cancel_session", 3, session=5)
    assert cancel.type == "occurrence_cancelled"
    engine.record_step(5)
    engine.record_step(6)
    assert engine.count("attendance_pct", "working").text() == "3/4 = 75.0%"  # cancelled is left out


def test_bad_proposals_are_refused_not_raised(engine: Engine) -> None:
    for actor, action, params, reason in [
        ("working", "skip", {}, "bad parameters: missing session"),
        ("working", "skip", {"session": 21}, "bad parameters: no session 21"),
        ("working", "skip", {"session": 1, "mood": "x"}, "bad parameters: unknown mood"),
        ("faculty", "edit_attendance", {"student": "nobody", "session": 1, "present": True},
         "bad parameters: unknown person 'nobody'"),
        ("faculty", "edit_attendance", {"student": "working", "session": 1, "present": True},
         "precondition: occurrence_recorded"),
        ("exam_officer", "skip", {"session": 1}, "permission"),
    ]:
        event = engine.propose(actor, action, 1, **params)
        assert (event.type, event.payload["reason"]) == ("action_rejected", reason)


def test_event_ids_are_unique_and_sequential(engine: Engine) -> None:
    record_through(engine, 4)
    ids = [e.event_id for e in engine.events]
    assert ids == [f"E-{n:04d}" for n in range(1, len(ids) + 1)]
