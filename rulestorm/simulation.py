"""The term loop: one decision phase per session over the approved blueprint.

Each week: scheduled capacity crunches, pending-request triggers, then each session's phase
(disruptions -> triggered agents decide -> arrivals and the lateness rule -> attendance
recorded), then the attendance admin works the queue and, at the checkpoint, the examination
officer evaluates eligibility. Both are rule agents in code.

Every number comes from the blueprint (user facts or approved AI assumptions); the code holds
only the general mechanics (docs/ARCHITECTURE.md, Where scenario values come from).
"""

from collections import defaultdict
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field

from rulestorm.education import (
    AGENT_ROLES,
    FALLING_ATTENDANCE_ABSENT,
    NEAR_THRESHOLD_POINTS,
    PENDING_TRIGGER_WEEKS,
    SESSIONS_PER_WEEK,
    TERM_WEEKS,
)
from rulestorm.engine import Attendance, Engine, Event
from rulestorm.policy import Blueprint, Profile


class Proposal(BaseModel):
    action: str
    params: dict[str, Any] = Field(default_factory=dict)


class DecisionContext(BaseModel):
    """What a triggered agent sees. All contexts of one phase share the same snapshot."""

    agent: str
    role: str
    week: int
    session: int
    triggers: list[Event]
    attendance: Attendance | None = None  # students only
    travel_buffer_min: int | None = None  # students only
    profile: Profile | None = None  # LLM agents: description and goals (students: constraints too) from the blueprint
    pending_requests: list[str] = Field(default_factory=list)


class PhaseDecision(BaseModel):
    agent: str
    proposals: list[Proposal] = Field(default_factory=list)
    reason: str = ""
    strategy: str = ""
    error: str | None = None  # set when the agent's call failed: recorded as "no action"


# Given every triggered agent's context for one phase, return their decisions.
# Slice 5 tests pass a scripted decider; the LLM agents are rulestorm.agents.Agents.decide_phase.
Decider = Callable[[list[DecisionContext]], list[PhaseDecision]]


def session_numbers(week: int) -> list[int]:
    first = (week - 1) * SESSIONS_PER_WEEK + 1
    return list(range(first, first + SESSIONS_PER_WEEK))


class Term:
    def __init__(self, blueprint: Blueprint, decider: Decider) -> None:
        self.bp = blueprint
        self.decider = decider
        students = [s.archetype for s in blueprint.scenario.students]
        self.engine = Engine(blueprint.policy.threshold_pct, students)
        self.engine.travel_buffer = {s.archetype: s.travel_buffer_min for s in blueprint.scenario.students}
        self.profiles: dict[str, Profile] = {s.archetype: s for s in blueprint.scenario.students}
        self.profiles.update(faculty=blueprint.scenario.faculty, advisor=blueprint.scenario.advisor)
        self.triggers: dict[str, list[str]] = defaultdict(list)
        self.near_threshold: set[str] = set()

    def trigger(self, agent: str, event: Event) -> None:
        if event.event_id not in self.triggers[agent]:
            self.triggers[agent].append(event.event_id)

    def run(self, on_week: Callable[[int], None] | None = None) -> Engine:
        for week in range(1, TERM_WEEKS + 1):
            self.run_week(week)
            if on_week:
                on_week(week)
        self.engine.current_session = None
        return self.engine

    def run_week(self, week: int) -> None:
        e = self.engine
        capacity = self.bp.scenario.admin_capacity_per_week
        capacity_causes: list[str] = []
        for d in self.bp.scenario.disruptions:
            if d.type == "admin_capacity" and d.week == week:
                crunch = e.emit(
                    "capacity_crunch", "environment", week,
                    payload={"description": d.description, "capacity": d.admin_capacity_during},
                    state_change={f"admin_capacity.week{week}": {"from": capacity, "to": d.admin_capacity_during}},
                )
                capacity = d.admin_capacity_during
                capacity_causes = [crunch.event_id]

        for request in list(e.requests.values()):
            waited = week - request.submitted_week
            if request.status == "pending" and waited >= PENDING_TRIGGER_WEEKS:
                pending = e.emit(
                    "request_pending", "engine", week,
                    payload={"request_id": request.request_id, "student": request.student, "weeks_pending": waited},
                    caused_by=e.pending_causes([request.request_id]),
                )
                self.trigger(request.student, pending)
                self.trigger("advisor", pending)

        for session in session_numbers(week):
            self.run_session(week, session, first_of_week=session == session_numbers(week)[0])

        e.propose("attendance_admin", "attendance_admin", "process_exception_queue", week,
                  caused_by=capacity_causes, capacity=capacity)
        if week == self.bp.scenario.checkpoint_week:
            for student in e.students:
                e.propose("exam_officer", "exam_officer", "evaluate_eligibility", week, student=student)

    def run_session(self, week: int, session: int, first_of_week: bool) -> None:
        e = self.engine
        e.current_session = session
        transport: list[tuple[Any, Event]] = []
        if first_of_week:
            for d in self.bp.scenario.disruptions:
                if d.type == "transport" and d.week == week:
                    event = e.emit(
                        "transport_disruption", "environment", week,
                        payload={"session": session, "description": d.description,
                                 "delay_min": d.delay_min, "affected": d.affected},
                    )
                    transport.append((d, event))
                    for student in d.affected:
                        self.trigger(student, event)

        self.decision_phase(week, session)
        self.record_arrivals(week, session, transport)

    def decision_phase(self, week: int, session: int) -> None:
        e = self.engine
        if not self.triggers:
            return
        contexts = []
        for agent in sorted(self.triggers):  # sorted by agent ID: results never depend on timing
            role = AGENT_ROLES[agent]
            context = DecisionContext(
                agent=agent, role=role, week=week, session=session,
                triggers=[e.event(t) for t in self.triggers[agent]],
                profile=self.profiles.get(agent),  # rule agents have none
            )
            if role == "student":
                context.attendance = e.attendance(agent)
                context.travel_buffer_min = e.travel_buffer.get(agent)
                context.pending_requests = context.attendance.pending
            else:
                context.pending_requests = [r.request_id for r in e.requests.values() if r.status == "pending"]
            contexts.append(context)
        self.triggers.clear()

        by_agent = {d.agent: d for d in self.decider(contexts)}
        for context in contexts:
            decision = by_agent.get(context.agent, PhaseDecision(agent=context.agent, error="no decision returned"))
            recorded = e.emit(
                "decision", context.agent, week,
                payload={
                    "session": session,
                    "proposals": [p.model_dump() for p in decision.proposals],
                    "reason": decision.reason,
                    "strategy": decision.strategy,
                    "no_action": not decision.proposals,
                    "error": decision.error,
                },
                caused_by=[t.event_id for t in context.triggers],
            )
            for proposal in decision.proposals:
                e.propose(context.role, context.agent, proposal.action, week,
                          caused_by=[recorded.event_id], **proposal.params)

    def record_arrivals(self, week: int, session: int, transport: list[tuple[Any, Event]]) -> None:
        """The lateness rule: a student who attends is late (an absence) when the disruption's
        delay is longer than their travel buffer. Faculty records attendance as a rule."""
        e = self.engine
        if session in e.cancelled:
            return
        absences = []
        for student in e.students:
            choice, intent_event = e.intents.get((student, session), ("attend", None))
            causes = [intent_event] if intent_event else []
            present, late = choice == "attend", False
            if present:
                for disruption, event in transport:
                    if student in disruption.affected and disruption.delay_min > e.travel_buffer[student]:
                        present, late = False, True
                        causes = [event.event_id, *causes]
            recorded = e.propose("faculty", "faculty", "record_attendance", week, caused_by=causes,
                                 student=student, session=session, present=present, late=late)
            if not present:
                absences.append(recorded)
                self.trigger(student, recorded)
            self.check_near_threshold(week, student, recorded)

        if len(absences) >= FALLING_ATTENDANCE_ABSENT:
            falling = e.emit("attendance_falling", "engine", week,
                             payload={"session": session, "absent": [a.payload["student"] for a in absences]},
                             caused_by=[a.event_id for a in absences])
            self.trigger("faculty", falling)

    def check_near_threshold(self, week: int, student: str, latest: Event) -> None:
        e = self.engine
        pct = e.attendance(student).pct
        near = pct is not None and abs(pct - e.threshold_pct) <= NEAR_THRESHOLD_POINTS
        if near and student not in self.near_threshold:
            event = e.emit("attendance_near_threshold", "engine", week,
                           payload={"student": student, "pct": pct, "threshold_pct": e.threshold_pct},
                           caused_by=[latest.event_id])
            self.trigger(student, event)
            self.trigger("advisor", event)
        if near:
            self.near_threshold.add(student)
        else:
            self.near_threshold.discard(student)


def simulate(blueprint: Blueprint, decider: Decider, on_week: Callable[[int], None] | None = None) -> Engine:
    return Term(blueprint, decider).run(on_week)
