"""Slices L2-L3: the general engine, driven only by the template and the blueprint's values."""

import json
from pathlib import Path

import pytest

from rulestorm.core.cases import run_case
from rulestorm.core.engine import Engine, Obstacle
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
        "queue FIFO: R1,R2 processed, R3 pending (capacity 2)",
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
    allowed = loose.propose("working", "edit_attendance", 1, student="working", session=1, present=True)
    # Past the permission check now; refused only because session 1 really was attended (26 Nov:
    # a correction must match what happened).
    assert allowed.type == "action_rejected" and allowed.payload["reason"] == "precondition: record_differs"


def test_a_correction_must_change_a_mark_and_match_what_happened(engine: Engine) -> None:
    engine.current_step = 1
    engine.propose("working", "skip", 1, session=1)
    engine.record_step(1)
    engine.current_step = None
    same = engine.propose("faculty", "edit_attendance", 1, student="working", session=1, present=False)
    assert same.payload["reason"] == "precondition: record_differs"
    false = engine.propose("faculty", "edit_attendance", 1, student="working", session=1, present=True)
    assert false.payload["reason"] == "precondition: matches_what_happened"
    assert engine.records[("attend_class", "working", 1)] == "missed"
    assert not engine.has_wrong_record("attend_class")


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
    engine.propose("commuter", "attend", 2, session=3, travel_buffer_min=40)
    # A change made during a step applies from the next one: it can't beat this step's delay.
    assert engine.attributes[("commuter", "travel_buffer_min")] == 10
    bad = engine.propose("commuter", "attend", 2, session=3, travel_buffer_min=500)
    assert bad.payload["reason"].startswith("bad parameters")
    engine.record_step(3)
    assert engine.attributes[("commuter", "travel_buffer_min")] == 40


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


# --- slice L3: queues, decision rules, partial acceptance, disruptions, checks ------------------


def strikes(template: Template, skips: dict[str, set[int]]) -> list[dict]:
    """A transport strike (outside the students' control) at each step a student misses."""
    spp = template.calendar.steps_per_period
    return [{"kind": "transport", "period": (s - 1) // spp + 1, "steps": [(s - 1) % spp + 1], "people": [person],
             "delay": 999, "description": "bus strike"} for person, steps in skips.items() for s in sorted(steps)]


def skipping(template: Template, values: dict | None = None, skips: dict[str, set[int]] | None = None,
             last_step: int = 4, excused: bool = True) -> Engine:
    """Steps 1..last_step recorded; `skips` maps a student to the steps they skip (default:
    'working' misses steps 1 and 3). With `excused`, a strike kept them away each time, so each
    absence is a valid exception (26 Nov); without it, they skipped by choice."""
    skips = {"working": {1, 3}} if skips is None else skips
    values = {**VALUES, **(values or {})}
    if excused:
        values["disruptions"] = [*values.get("disruptions", []), *strikes(template, skips)]
    engine = Engine(template, values)
    for step in range(1, last_step + 1):
        engine.start_step(step)
        engine.current_step = step
        for person, steps in skips.items():
            if step in steps:
                engine.propose(person, "skip", engine.period_of(step), session=step)
        engine.record_step(step)
    engine.current_step = None
    return engine


def test_only_an_absence_a_non_routine_disruption_caused_is_excused(template: Template) -> None:
    by_choice = skipping(template, {"office_capacity_per_week": 5}, excused=False)
    by_choice.propose("working", "submit_exception_request", 2, sessions=[1], reason="felt like it")
    by_choice.process_queue("exception", 2)
    assert by_choice.requests["R1"].status == "rejected"
    recorded = next(e for e in by_choice.events if e.type == "duty_recorded" and e.payload["person"] == "working")
    assert (recorded.payload["cause"], recorded.payload["excusable"]) == (None, False)

    # A delay no longer than their slack (working: 15 min) didn't stop them, so skipping is a choice.
    small = {"kind": "transport", "period": 1, "steps": [1], "people": ["working"], "delay": 15, "description": "slow bus"}
    within = skipping(template, {"office_capacity_per_week": 5, "disruptions": [small]}, excused=False)
    within.propose("working", "submit_exception_request", 2, sessions=[1], reason="bus")
    within.process_queue("exception", 2)
    assert within.requests["R1"].status == "rejected"

    excused = skipping(template, {"office_capacity_per_week": 5})
    excused.propose("working", "submit_exception_request", 2, sessions=[1], reason="strike")
    excused.process_queue("exception", 2)
    assert excused.requests["R1"].status == "approved"
    assert "outside their control" in excused.cause_text("attend_class", "working", 1)


def test_a_routine_clash_is_not_excused_and_an_emergency_is(template: Template) -> None:
    clashes = [{"kind": "work_shift_clash", "period": 1, "steps": [1], "people": ["working"], "description": "shift"},
               {"kind": "family_emergency", "period": 2, "steps": [1], "people": ["family"], "description": "hospital"}]
    engine = skipping(template, {"office_capacity_per_week": 5, "disruptions": clashes},
                      skips={"working": {1}, "family": {3}}, excused=False)
    engine.propose("working", "submit_exception_request", 2, sessions=[1], reason="shift")
    engine.propose("family", "submit_exception_request", 2, sessions=[3], reason="hospital")
    engine.process_queue("exception", 2)
    assert (engine.requests["R1"].status, engine.requests["R2"].status) == ("rejected", "approved")
    # A clash only matters if they chose to miss: no plan means they came anyway.
    came = skipping(template, {"disruptions": clashes}, skips={}, excused=False)
    assert came.records[("attend_class", "working", 1)] == "met"


def test_a_step_written_as_text_is_read_as_its_number(engine: Engine) -> None:
    engine.current_step = 9
    planned = engine.propose("working", "skip", 5, session="week 5 session 9")
    assert planned.type == "duty_planned" and planned.step == 9
    wrong = engine.propose("working", "skip", 5, session="tomorrow")
    assert wrong.payload["reason"] == "bad parameters: session must be a whole number"


def test_queue_is_fifo_within_capacity_and_records_what_it_holds(template: Template) -> None:
    engine = skipping(template, {"office_capacity_per_week": 1})
    for session in (1, 3):
        engine.propose("working", "submit_exception_request", 2, sessions=[session], reason="r")
    first = engine.process_queue("exception", 2)
    assert first.payload["processed"] == ["R1"] and first.payload["pending"] == ["R2"]
    assert first.actor == "attendance_admin"  # the queue processor rule's person
    held = engine.events[-1]
    assert held.type == "queue_over_capacity" and held.payload["held"] == ["R2"]
    assert engine.requests["R2"].filed_event in held.caused_by
    with pytest.raises(ValueError):  # one processing per slot
        engine.process_queue("exception", 2)
    assert engine.requests["R1"].status == "approved"
    assert engine.count("attendance_pct", "working").text() == "2/3 = 66.7%"


def test_request_for_an_attended_session_is_rejected(template: Template) -> None:
    engine = skipping(template, {"office_capacity_per_week": 5})
    engine.propose("resident", "submit_exception_request", 2, sessions=[2], reason="r")
    engine.process_queue("exception", 2)
    assert engine.requests["R1"].status == "rejected"
    assert engine.count("attendance_pct", "resident").text() == "4/4 = 100.0%"


def test_partial_at_submit_drops_a_not_yet_recorded_session(template: Template) -> None:
    whole = skipping(template)
    refused = whole.propose("working", "submit_exception_request", 2, sessions=[3, 5], reason="r")
    assert refused.payload["reason"] == "precondition: occurrence_recorded"  # without it: refused whole

    engine = skipping(template, {"partial_at_submit": True})
    filed = engine.propose("working", "submit_exception_request", 2, sessions=[3, 5], reason="r")
    assert filed.type == "request_filed"
    assert engine.requests["R1"].steps == [3]
    assert filed.payload["dropped"] == [{"step": 5, "reason": "precondition: occurrence_recorded",
                                         "detail": "session 5 had not been recorded yet when you sent this"}]
    nothing_left = engine.propose("working", "submit_exception_request", 2, sessions=[6], reason="r")
    assert nothing_left.type == "action_rejected"


def test_partial_at_decide_approves_the_missed_sessions_and_rejects_the_attended_one(template: Template) -> None:
    whole = skipping(template, {"office_capacity_per_week": 5})
    whole.propose("working", "submit_exception_request", 2, sessions=[1, 2, 3], reason="r")
    whole.process_queue("exception", 2)
    assert whole.requests["R1"].status == "rejected"  # without it: rejected whole

    engine = skipping(template, {"office_capacity_per_week": 5, "partial_at_decide": True})
    engine.propose("working", "submit_exception_request", 2, sessions=[1, 2, 3], reason="r")
    engine.process_queue("exception", 2)
    decided = next(e for e in engine.events if e.type == "request_decided")
    request = engine.requests["R1"]
    assert (request.status, request.approved_steps, request.rejected_steps) == ("approved", [1, 3], [2])
    assert decided.payload["approved_steps"] == [1, 3] and decided.payload["rejected_steps"] == [2]
    assert engine.count("attendance_pct", "working").text() == "2/2 = 100.0%"
    again = engine.propose("working", "submit_exception_request", 2, sessions=[2], reason="r")
    assert again.type == "request_filed"  # a rejected step is not covered


def test_other_decision_rules(template: Template) -> None:
    emergency = {"kind": "family_emergency", "period": 1, "steps": [2], "people": ["working"], "description": "parent ill"}
    engine = Engine(template, {**VALUES, "request_timing": "in_advance",
                               "decision_rule": "approve_if_filed_before_occurrence",
                               "office_capacity_per_week": 5, "disruptions": [emergency]})
    engine.propose("working", "submit_exception_request", 1, sessions=[2], reason="parent ill")
    engine.propose("resident", "submit_exception_request", 1, sessions=[2], reason="dentist")
    engine.record_step(1)
    engine.start_step(2)
    engine.current_step = 2
    engine.propose("working", "skip", 1, session=2)
    engine.record_step(2)
    engine.current_step = None
    engine.process_queue("exception", 1)
    # filed before, and the absence had a valid cause: approved; filed before but attended: rejected
    assert (engine.requests["R1"].status, engine.requests["R2"].status) == ("approved", "rejected")

    lenient = skipping(template, {"decision_rule": "approve_all", "office_capacity_per_week": 5})
    lenient.propose("resident", "submit_exception_request", 2, sessions=[2], reason="r")
    lenient.process_queue("exception", 2)
    assert lenient.requests["R1"].status == "approved"


def test_a_capacity_disruption_changes_that_periods_processing(template: Template) -> None:
    crunch = {"kind": "admin_capacity", "period": 2, "capacity": 0, "description": "office staff away"}
    engine = skipping(template, {"office_capacity_per_week": 5, "disruptions": [crunch]})
    engine.propose("working", "submit_exception_request", 2, sessions=[1], reason="r")
    changed = engine.start_period(2)
    assert [e.type for e in changed] == ["capacity_changed"]
    assert changed[0].state_change == {"capacity.exception.2": {"from": 5, "to": 0}}
    week2 = engine.process_queue("exception", 2)
    assert week2.payload == {"request_type": "exception", "capacity": 0, "processed": [], "pending": ["R1"]}
    assert changed[0].event_id in week2.caused_by
    assert engine.start_period(3) == []
    week3 = engine.process_queue("exception", 3)
    assert week3.payload["capacity"] == 5 and week3.payload["processed"] == ["R1"]


def test_an_obstacle_hits_only_its_listed_steps(template: Template) -> None:
    strike = {"kind": "transport", "period": 2, "steps": [1], "people": ["commuter", "working"],
              "delay": 40, "description": "bus strike"}
    engine = Engine(template, {**VALUES, "disruptions": [strike]})
    hits = {}
    for step in range(1, 7):
        hits[step] = engine.start_step(step)
        engine.record_step(step)
    assert [s for s, events in hits.items() if events] == [3]  # period 2, its first step

    def outcome(person: str, step: int) -> str:
        return engine.records[("attend_class", person, step)]

    assert (outcome("commuter", 3), outcome("working", 3)) == ("missed", "missed")  # 40 > 10, 40 > 15
    assert outcome("resident", 3) == "met"  # not listed
    assert outcome("commuter", 4) == "met"  # not a listed step
    assert hits[3][0].event_id in engine.event(engine.record_event[("attend_class", "commuter", 3)]).caused_by


def test_a_cancellation_disruption_cancels_its_steps(template: Template) -> None:
    closed = {"kind": "session_cancelled", "period": 1, "steps": [2], "description": "campus closed"}
    engine = Engine(template, {**VALUES, "disruptions": [closed]})
    for step in (1, 2):
        engine.start_step(step)
        engine.record_step(step)
    assert engine.cancelled["attend_class"] == {2}
    assert engine.count("attendance_pct", "working").text() == "1/1 = 100.0%"


def test_bad_disruptions_are_refused(template: Template) -> None:
    for d, message in [
        ({"kind": "flood", "period": 1}, "unknown disruption kind"),
        ({"kind": "transport", "period": 1, "steps": [1], "people": ["dean"], "delay": 5}, "unknown people"),
        ({"kind": "transport", "period": 1, "steps": [3], "people": ["working"], "delay": 5}, "outside"),
        ({"kind": "admin_capacity", "period": 1}, "needs a capacity"),
    ]:
        with pytest.raises(ValueError, match=message):
            Engine(template, {**VALUES, "disruptions": [d]})


def test_a_single_threshold_check_records_both_figures_and_pending_requests(template: Template) -> None:
    engine = skipping(template, {"checkpoint_week": 2, "office_capacity_per_week": 0})
    filed = engine.propose("working", "submit_exception_request", 2, sessions=[1], reason="r")
    engine.process_queue("exception", 2)
    held = engine.events[-1]
    assert engine.run_checks(1) == []  # not due yet
    checks = {e.payload["person"]: e for e in engine.run_checks(2)}
    assert set(checks) == {"commuter", "resident", "working", "family"}
    working = checks["working"]
    assert working.type == "check_evaluated" and working.actor == "exam_officer"
    assert working.payload["passed"] is False and working.payload["threshold"] == 80
    assert working.payload["count"]["value"] == 50.0
    assert working.payload["count_if_pending_approved"]["value"] == 66.7
    assert working.payload["pending_requests"] == ["R1"]
    assert {filed.event_id, held.event_id} <= set(working.caused_by)
    # the check records its count: the uncovered miss directly, the covered one through its request
    assert engine.record_event[("attend_class", "working", 3)] in working.caused_by
    assert engine.record_event[("attend_class", "working", 1)] not in working.caused_by
    assert engine.record_event[("attend_class", "working", 1)] in filed.caused_by
    assert checks["resident"].payload["passed"] is True


def test_every_refusal_has_a_plain_detail_from_the_template_labels(engine: Engine) -> None:
    """The reason code stays for summaries; the person is shown plain words built from the fixed
    reason library and the template's labels (no per-template refusal sentences)."""
    engine.current_step = 1
    cases = [
        (("working", "edit_attendance", {"student": "working", "session": 1, "present": True}),
         "permission", "a Student is not allowed to correct a recorded attendance mark"),
        (("working", "submit_exception_request", {"sessions": [1], "reason": "r"}),
         "precondition: occurrence_recorded", "session 1 had not been recorded yet when you sent this"),
        (("working", "skip", {"session": 2}),
         "precondition: current_step", "plans can be made only for the current session (session 1)"),
    ]
    for (actor, action, params), reason, detail in cases:
        event = engine.propose(actor, action, 1, **params)
        assert (event.payload["reason"], event.payload["detail"]) == (reason, detail)
    engine.record_step(1)
    engine.current_step = None
    engine.propose("working", "submit_exception_request", 1, sessions=[1], reason="r")
    again = engine.propose("working", "submit_exception_request", 1, sessions=[1], reason="r")
    assert again.payload["detail"] == "session 1 is already covered by one of your exception requests"
