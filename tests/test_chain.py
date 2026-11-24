"""Slice 5: the term loop with fixed inputs and a scripted decider (no model)."""

import copy

import pytest

from rulestorm.policy import Blueprint
from rulestorm.simulation import DecisionContext, PhaseDecision, Proposal, simulate
from test_blueprint import VALID

# Test-only scenario: week 3 transport disruption (45 min) hits the commuter (buffer 30, so
# late if they attend) and the working student; the admin can process nothing, so requests
# stay pending until the week-6 checkpoint.
SCENARIO = {
    "students": [
        {"archetype": "commuter", "description": "travels two hours by bus", "goals": ["keep eligibility"], "constraints": ["long commute"], "travel_buffer_min": 30},
        {"archetype": "resident", "description": "lives in the hostel", "goals": ["good grades"], "constraints": ["none"], "travel_buffer_min": 10},
        {"archetype": "working", "description": "works evening shifts", "goals": ["keep the job"], "constraints": ["fixed work hours"], "travel_buffer_min": 15},
        {"archetype": "family", "description": "cares for a parent", "goals": ["balance home and study"], "constraints": ["care duties"], "travel_buffer_min": 20},
    ],
    "faculty": {"description": "teaches the course", "goals": ["keep participation up"]},
    "advisor": {"description": "advises 40 students", "goals": ["keep advisees eligible"]},
    "admin_capacity_per_week": 0,
    "checkpoint_week": 6,
    "disruptions": [
        {"week": 3, "type": "transport", "description": "bus strike", "delay_min": 45,
         "affected": ["commuter", "working"]},
        {"week": 5, "type": "admin_capacity", "description": "staff away", "admin_capacity_during": 0},
    ],
}


def blueprint(**scenario_changes) -> Blueprint:
    data = copy.deepcopy(VALID)
    data["scenario"] = {**copy.deepcopy(SCENARIO), **scenario_changes}
    return Blueprint.model_validate(data)


def scripted(context: DecisionContext) -> PhaseDecision:
    """Commuter attends anyway (and arrives late); working skips because of the disruption.
    Any student with a recorded absence asks for an exception; the advisor advises."""
    proposals = []
    for trigger in context.triggers:
        if trigger.type == "transport_disruption":
            choice = "attend" if context.agent == "commuter" else "skip"
            proposals.append(Proposal(action=choice, params={"session": context.session}))
        elif trigger.type == "attendance_recorded" and context.role == "student":
            proposals.append(Proposal(action="submit_exception_request",
                                      params={"sessions": [trigger.payload["session"]], "reason": "disruption"}))
        elif trigger.type == "request_pending" and context.role == "advisor":
            proposals.append(Proposal(action="advise_student",
                                      params={"student": trigger.payload["student"], "advice": "follow up"}))
    return PhaseDecision(agent=context.agent, proposals=proposals, reason="scripted")


def decider(contexts: list[DecisionContext]) -> list[PhaseDecision]:
    return [scripted(c) for c in contexts]


@pytest.fixture(scope="module")
def engine():
    return simulate(blueprint(), decider)


def of_type(engine, type_):
    return [e for e in engine.events if e.type == type_]


def decisions_at(engine, session):
    return {e.actor: e for e in of_type(engine, "decision") if e.payload["session"] == session}


# (a) disruptions happen at the blueprint's weeks
def test_disruptions_logged_at_blueprint_weeks(engine) -> None:
    assert [e.week for e in of_type(engine, "transport_disruption")] == [3]
    assert [e.week for e in of_type(engine, "capacity_crunch")] == [5]
    moved = simulate(blueprint(disruptions=[
        {"week": 7, "type": "transport", "description": "x", "delay_min": 5, "affected": ["family"]},
        {"week": 2, "type": "admin_capacity", "description": "y", "admin_capacity_during": 1},
    ]), decider)
    assert [e.week for e in of_type(moved, "transport_disruption")] == [7]
    assert [e.week for e in of_type(moved, "capacity_crunch")] == [2]


def test_capacity_crunch_sets_that_weeks_queue_capacity(engine) -> None:
    crunch = of_type(engine, "capacity_crunch")[0]
    week5 = [e for e in of_type(engine, "exception_queue_processed") if e.week == 5][0]
    assert crunch.event_id in week5.caused_by and week5.payload["capacity"] == 0


# (b) trigger rules fire
def test_disruption_triggers_the_listed_students_only(engine) -> None:
    disruption = of_type(engine, "transport_disruption")[0]
    at_session_5 = decisions_at(engine, 5)
    assert set(at_session_5) == {"commuter", "working"}
    assert all(disruption.event_id in d.caused_by for d in at_session_5.values())


def test_absence_triggers_that_student(engine) -> None:
    absences = {e.payload["student"]: e for e in of_type(engine, "attendance_recorded")
                if e.payload["session"] == 5 and e.state_change[f"attendance.{e.payload['student']}.5"]["to"] == "absent"}
    assert set(absences) == {"commuter", "working"}
    at_session_6 = decisions_at(engine, 6)
    for student, absence in absences.items():
        assert absence.event_id in at_session_6[student].caused_by
    # the other triggers in that phase: near the threshold (advisor) and 2 absent (faculty)
    assert set(at_session_6) == {"advisor", "commuter", "faculty", "working"}


def test_request_pending_a_week_triggers_student_and_advisor(engine) -> None:
    pending = [e for e in of_type(engine, "request_pending") if e.week == 4]
    assert {e.payload["student"] for e in pending} == {"commuter", "working"}
    at_session_7 = decisions_at(engine, 7)
    for event in pending:
        assert event.event_id in at_session_7[event.payload["student"]].caused_by
        assert event.event_id in at_session_7["advisor"].caused_by
    assert of_type(engine, "advice_given")


# (c) the eligibility evaluation links back to the disruption
def path(engine, start: str, goal: str, avoid_other_students: str) -> list[str]:
    """Shortest caused_by path from start to goal that never passes through another
    student's own events, so one student's chain cannot borrow another's."""
    others = {"commuter", "resident", "working", "family"} - {avoid_other_students}
    frontier, came_from = [start], {start: None}
    while frontier:
        current = frontier.pop(0)
        if current == goal:
            chain = []
            while current:
                chain.append(current)
                current = came_from[current]
            return chain[::-1]  # start (eligibility) first, goal (disruption) last
        for parent in engine.event(current).caused_by:
            event = engine.event(parent)
            if parent in came_from or event.actor in others or event.payload.get("student") in others:
                continue
            came_from[parent] = current
            frontier.append(parent)
    return []


def eligibility_of(engine, student):
    return next(e for e in of_type(engine, "eligibility_evaluated") if e.payload["student"] == student)


def test_late_arrival_chain_reaches_the_disruption(engine) -> None:
    disruption = of_type(engine, "transport_disruption")[0]
    late = [e for e in of_type(engine, "attendance_recorded") if e.payload["late"]]
    assert [e.payload["student"] for e in late] == ["commuter"]
    chain = path(engine, eligibility_of(engine, "commuter").event_id, disruption.event_id, "commuter")
    assert [engine.event(i).type for i in chain] == [
        "eligibility_evaluated", "exception_request_submitted", "attendance_recorded", "transport_disruption"]
    assert late[0].event_id in chain  # the late arrival itself links to the disruption


def test_skip_chain_reaches_the_disruption_through_the_decision(engine) -> None:
    disruption = of_type(engine, "transport_disruption")[0]
    eligibility = eligibility_of(engine, "working")
    chain = path(engine, eligibility.event_id, disruption.event_id, "working")
    assert [engine.event(i).type for i in chain] == [
        "eligibility_evaluated", "exception_request_submitted", "attendance_recorded",
        "student_plans_skip", "decision", "transport_disruption"]
    assert len(eligibility.payload["pending_requests"]) == 1  # still waiting at the checkpoint


def test_eligibility_links_to_the_queue_event_that_held_the_request(engine) -> None:
    for student in ("commuter", "working"):
        eligibility = eligibility_of(engine, student)
        held = [engine.event(i) for i in eligibility.caused_by if engine.event(i).type == "queue_over_capacity"]
        assert held and eligibility.payload["pending_requests"][0] in held[0].payload["held"]


def test_no_triggers_no_decisions_before_the_disruption(engine) -> None:
    assert all(e.week >= 3 for e in of_type(engine, "decision"))


def test_profiles_reach_their_decision_context() -> None:
    seen: dict[str, DecisionContext] = {}

    def recording(contexts: list[DecisionContext]) -> list[PhaseDecision]:
        for c in contexts:
            seen.setdefault(c.agent, c)
        return decider(contexts)

    bp = blueprint()
    simulate(bp, recording)
    by_archetype = {s.archetype: s for s in bp.scenario.students}
    assert "commuter" in seen and "advisor" in seen
    commuter = seen["commuter"].profile
    assert commuter.description == by_archetype["commuter"].description
    assert commuter.goals == by_archetype["commuter"].goals
    assert seen["advisor"].profile == bp.scenario.advisor
    assert all(c.profile is None for a, c in seen.items() if a in ("attendance_admin", "exam_officer"))
