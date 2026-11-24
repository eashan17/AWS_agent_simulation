"""Slice L4: a whole term on the general engine, with fixed inputs and a scripted decider (no model).
Ported from test_chain.py (slice 5): same scenario, same assertions, general event names."""

import pytest

from rulestorm.core.model import Template, load_template
from rulestorm.core.term import DecisionContext, PhaseDecision, Proposal, simulate

STUDENTS = {"commuter", "resident", "working", "family"}
PROFILES = {
    "commuter": {"description": "travels two hours by bus", "goals": ["keep eligibility"], "constraints": ["long commute"]},
    "resident": {"description": "lives in the hostel", "goals": ["good grades"], "constraints": ["none"]},
    "working": {"description": "works evening shifts", "goals": ["keep the job"], "constraints": ["fixed work hours"]},
    "family": {"description": "cares for a parent", "goals": ["balance home and study"], "constraints": ["care duties"]},
    "faculty": {"description": "teaches the course", "goals": ["keep participation up"]},
    "advisor": {"description": "advises 40 students", "goals": ["keep advisees eligible"]},
}
# Test-only scenario: week 3 transport disruption (45 min, first session) hits the commuter
# (slack 30, so late if they attend) and the working student; the office can process nothing,
# so requests stay pending until the week-6 checkpoint.
VALUES = {
    "threshold_pct": 80, "scope": "per_course", "request_timing": "after_missed",
    "partial_at_submit": False, "partial_at_decide": False, "decision_rule": "approve_if_covered_missed",
    "office_capacity_per_week": 0, "checkpoint_week": 6,
    "disruptions": [
        {"kind": "transport", "period": 3, "steps": [1], "people": ["commuter", "working"],
         "delay": 45, "description": "bus strike"},
        {"kind": "admin_capacity", "period": 5, "capacity": 0, "description": "staff away"},
    ],
    "profiles": PROFILES,
    "slack_min": {"commuter": 30, "resident": 10, "working": 15, "family": 20},
}


def scripted(context: DecisionContext) -> PhaseDecision:
    """Commuter attends anyway (and arrives late); working skips because of the disruption.
    Any student with a recorded absence asks for an exception; the advisor advises."""
    proposals = []
    for trigger in context.triggers:
        if trigger.type == "obstacle":
            choice = "attend" if context.person == "commuter" else "skip"
            proposals.append(Proposal(action=choice, params={"session": context.step}))
        elif trigger.type == "duty_recorded" and context.role == "student":
            proposals.append(Proposal(action="submit_exception_request",
                                      params={"sessions": [trigger.step], "reason": "disruption"}))
        elif trigger.type == "request_pending" and context.role == "advisor":
            proposals.append(Proposal(action="advise_student",
                                      params={"student": trigger.payload["person"], "advice": "follow up"}))
    return PhaseDecision(person=context.person, proposals=proposals, reason="scripted")


def decider(contexts: list[DecisionContext]) -> list[PhaseDecision]:
    return [scripted(c) for c in contexts]


@pytest.fixture(scope="module")
def template() -> Template:
    return load_template("attendance")


@pytest.fixture(scope="module")
def engine(template):
    return simulate(template, VALUES, decider)


def of_type(engine, type_):
    return [e for e in engine.events if e.type == type_]


def decisions_at(engine, step):
    return {e.actor: e for e in of_type(engine, "decision") if e.step == step}


# (a) disruptions happen at the blueprint's periods
def test_disruptions_logged_at_blueprint_periods(engine, template) -> None:
    assert [(e.period, e.step) for e in of_type(engine, "obstacle")] == [(3, 5)]
    assert [e.period for e in of_type(engine, "capacity_changed")] == [5]
    moved = simulate(template, {**VALUES, "disruptions": [
        {"kind": "transport", "period": 7, "steps": [2], "people": ["family"], "delay": 5, "description": "x"},
        {"kind": "admin_capacity", "period": 2, "capacity": 1, "description": "y"},
    ]}, decider)
    assert [(e.period, e.step) for e in of_type(moved, "obstacle")] == [(7, 14)]
    assert [e.period for e in of_type(moved, "capacity_changed")] == [2]


def test_capacity_disruption_sets_that_periods_queue_capacity(engine) -> None:
    crunch = of_type(engine, "capacity_changed")[0]
    week5 = [e for e in of_type(engine, "queue_processed") if e.period == 5][0]
    assert crunch.event_id in week5.caused_by and week5.payload["capacity"] == 0


# (b) trigger rules fire
def test_disruption_triggers_the_listed_students_only(engine) -> None:
    obstacle = of_type(engine, "obstacle")[0]
    at_step_5 = decisions_at(engine, 5)
    assert set(at_step_5) == {"commuter", "working"}
    assert all(obstacle.event_id in d.caused_by for d in at_step_5.values())


def test_absence_triggers_that_student(engine) -> None:
    absences = {e.payload["person"]: e for e in of_type(engine, "duty_recorded")
                if e.step == 5 and e.payload["outcome"] == "missed"}
    assert set(absences) == {"commuter", "working"}
    at_step_6 = decisions_at(engine, 6)
    for student, absence in absences.items():
        assert absence.event_id in at_step_6[student].caused_by
    # the other triggers in that phase: near the threshold (advisor) and 2 missed (faculty)
    assert set(at_step_6) == {"advisor", "commuter", "faculty", "working"}


def test_request_pending_a_period_triggers_student_and_advisor(engine) -> None:
    pending = [e for e in of_type(engine, "request_pending") if e.period == 4]
    assert {e.payload["person"] for e in pending} == {"commuter", "working"}
    at_step_7 = decisions_at(engine, 7)
    for event in pending:
        assert event.event_id in at_step_7[event.payload["person"]].caused_by
        assert event.event_id in at_step_7["advisor"].caused_by
    assert of_type(engine, "response_given")


def test_rule_roles_are_never_asked(engine) -> None:
    assert {e.actor for e in of_type(engine, "decision")} <= {*STUDENTS, "faculty", "advisor"}


# (c) the check links back to the disruption
def path(engine, start: str, goal: str, avoid_other_students: str) -> list[str]:
    """Shortest caused_by path from start to goal that never passes through another
    student's own events, so one student's chain cannot borrow another's."""
    others = STUDENTS - {avoid_other_students}
    frontier, came_from = [start], {start: None}
    while frontier:
        current = frontier.pop(0)
        if current == goal:
            chain = []
            while current:
                chain.append(current)
                current = came_from[current]
            return chain[::-1]  # start (check) first, goal (disruption) last
        for parent in engine.event(current).caused_by:
            event = engine.event(parent)
            if parent in came_from or event.actor in others or event.payload.get("person") in others:
                continue
            came_from[parent] = current
            frontier.append(parent)
    return []


def check_of(engine, student):
    return next(e for e in of_type(engine, "check_evaluated") if e.payload["person"] == student)


def test_late_arrival_chain_reaches_the_disruption(engine) -> None:
    obstacle = of_type(engine, "obstacle")[0]
    late = [e for e in of_type(engine, "duty_recorded") if e.payload["obstacle"]]
    assert [e.payload["person"] for e in late] == ["commuter"]
    assert late[0].payload["plan"] == "meet"  # they planned to attend and the delay made them miss
    chain = path(engine, check_of(engine, "commuter").event_id, obstacle.event_id, "commuter")
    assert [engine.event(i).type for i in chain] == [
        "check_evaluated", "request_filed", "duty_recorded", "obstacle"]
    assert late[0].event_id in chain  # the late arrival itself links to the disruption


def test_skip_chain_reaches_the_disruption_through_the_decision(engine) -> None:
    obstacle = of_type(engine, "obstacle")[0]
    check = check_of(engine, "working")
    chain = path(engine, check.event_id, obstacle.event_id, "working")
    assert [engine.event(i).type for i in chain] == [
        "check_evaluated", "request_filed", "duty_recorded", "duty_planned", "decision", "obstacle"]
    assert len(check.payload["pending_requests"]) == 1  # still waiting at the checkpoint


def test_check_links_to_the_queue_event_that_held_the_request(engine) -> None:
    for student in ("commuter", "working"):
        check = check_of(engine, student)
        held = [engine.event(i) for i in check.caused_by if engine.event(i).type == "queue_over_capacity"]
        assert held and check.payload["pending_requests"][0] in held[0].payload["held"]


def test_no_triggers_no_decisions_before_the_disruption(engine) -> None:
    assert all(e.period >= 3 for e in of_type(engine, "decision"))


def test_profiles_reach_their_decision_context(template) -> None:
    seen: dict[str, DecisionContext] = {}

    def recording(contexts: list[DecisionContext]) -> list[PhaseDecision]:
        for c in contexts:
            seen.setdefault(c.person, c)
        return decider(contexts)

    simulate(template, VALUES, recording)
    assert "commuter" in seen and "advisor" in seen
    assert seen["commuter"].profile == PROFILES["commuter"]
    assert seen["advisor"].profile == PROFILES["advisor"]
    assert seen["commuter"].counts["attendance_pct"].kind == "rate"
    assert seen["commuter"].attributes == {"travel_buffer_min": 30}
    assert "attendance_admin" not in seen and "exam_officer" not in seen


# (d) the fixed phase order
def test_in_the_check_period_a_request_filed_before_period_end_is_processed_before_the_check(template) -> None:
    values = {**VALUES, "office_capacity_per_week": 5, "checkpoint_week": 3,
              "disruptions": [VALUES["disruptions"][0]]}
    engine = simulate(template, values, decider)
    filed = next(e for e in of_type(engine, "request_filed") if e.payload["person"] == "working")
    assert (filed.period, filed.step) == (3, 6)  # filed in the check period, before its end
    queue = next(e for e in of_type(engine, "queue_processed") if e.period == 3)
    check = check_of(engine, "working")
    assert check.period == 3 and queue.seq < check.seq
    assert engine.requests[filed.payload["request_id"]].status == "approved"
    assert check.payload["pending_requests"] == []
    assert check.payload["count"]["value"] == 100.0  # the approved miss is left out: 5/5
