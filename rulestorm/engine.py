"""Deterministic rule engine: state, actions, permissions, attendance and eligibility maths, event log.

Agents only propose actions. The engine checks the role's permission and the action's
preconditions, then commits state. Every committed or refused action becomes an event with an
ID, the state change it made, and `caused_by` links to the events that led to it.

Formula (BRIEF must-have 3): attendance % = attended / countable completed sessions x 100.
Cancelled sessions and sessions covered by approved exceptions are not countable; pending or
rejected exceptions count as absences.
"""

import inspect
from typing import Any, Literal

from pydantic import BaseModel, Field

from rulestorm.education import ROLE_ACTIONS, SESSIONS_PER_WEEK, TERM_WEEKS


class Event(BaseModel):
    event_id: str
    seq: int
    week: int
    type: str
    actor: str
    payload: dict[str, Any] = Field(default_factory=dict)
    state_change: dict[str, Any] = Field(default_factory=dict)
    caused_by: list[str] = Field(default_factory=list)


class ExceptionRequest(BaseModel):
    request_id: str
    student: str
    sessions: list[int]
    reason: str
    submitted_week: int
    submitted_event: str
    status: Literal["pending", "approved", "rejected"] = "pending"
    decided_week: int | None = None


class Attendance(BaseModel):
    student: str
    attended: int
    countable: int
    pct: float | None  # None while no session is countable
    pending: list[str]
    approved: list[str]
    rejected: list[str]

    def text(self) -> str:
        pct = "n/a" if self.pct is None else f"{self.pct:.1f}%"
        return f"{self.attended}/{self.countable} = {pct}"


class ActionRefused(Exception):
    """A precondition failed; the engine records the refusal instead of committing."""


def session_week(session: int) -> int:
    return (session - 1) // SESSIONS_PER_WEEK + 1


class Engine:
    def __init__(
        self,
        threshold_pct: int,
        students: list[str],
        total_sessions: int = TERM_WEEKS * SESSIONS_PER_WEEK,
    ) -> None:
        self.threshold_pct = threshold_pct
        self.students = list(students)
        self.total_sessions = total_sessions
        self.events: list[Event] = []
        self.present: dict[tuple[str, int], bool] = {}
        self.record_event: dict[tuple[str, int], str] = {}
        self.cancelled: set[int] = set()
        self.completed: set[int] = set()
        self.requests: dict[str, ExceptionRequest] = {}  # insertion order = FIFO order
        self.queue_weeks: set[int] = set()
        # Set by the term loop (rulestorm/simulation.py); unused by fixed cases.
        self.current_session: int | None = None
        self.travel_buffer: dict[str, int] = {}
        self.intents: dict[tuple[str, int], tuple[str, str]] = {}  # (student, session) -> (choice, event_id)

    # --- event log ------------------------------------------------------------------------

    def emit(
        self,
        type: str,
        actor: str,
        week: int,
        payload: dict[str, Any] | None = None,
        state_change: dict[str, Any] | None = None,
        caused_by: list[str] | None = None,
    ) -> Event:
        seq = len(self.events) + 1
        event = Event(
            event_id=f"E-{seq:04d}",
            seq=seq,
            week=week,
            type=type,
            actor=actor,
            payload=payload or {},
            state_change=state_change or {},
            caused_by=list(dict.fromkeys(caused_by or [])),
        )
        self.events.append(event)
        return event

    def event(self, event_id: str) -> Event:
        return self.events[int(event_id.removeprefix("E-")) - 1]

    def ancestors(self, event_id: str) -> list[str]:
        """Every event reachable by following `caused_by` links back, nearest first."""
        seen: list[str] = []
        frontier = list(self.event(event_id).caused_by)
        while frontier:
            current = frontier.pop(0)
            if current not in seen:
                seen.append(current)
                frontier.extend(self.event(current).caused_by)
        return seen

    # --- actions: agents propose, the engine validates and commits --------------------------

    def propose(
        self,
        role: str,
        actor: str,
        action: str,
        week: int,
        caused_by: list[str] | None = None,
        **params: Any,
    ) -> Event:
        caused_by = caused_by or []
        if action not in ROLE_ACTIONS.get(role, frozenset()):
            return self._refuse(role, actor, action, week, caused_by, params, "permission")
        handler = getattr(self, f"_do_{action}", None)
        if handler is None:
            return self._refuse(role, actor, action, week, caused_by, params, "unsupported action")
        try:  # a proposal with missing or unknown parameters is refused, not a crash
            inspect.signature(handler).bind(actor, week, caused_by, **params)
        except TypeError as exc:
            return self._refuse(role, actor, action, week, caused_by, params, f"bad parameters: {exc}")
        try:
            return handler(actor, week, caused_by, **params)
        except ActionRefused as exc:
            return self._refuse(role, actor, action, week, caused_by, params, str(exc))

    def _refuse(self, role, actor, action, week, caused_by, params, reason) -> Event:
        return self.emit(
            "action_rejected",
            actor,
            week,
            payload={"role": role, "action": action, "params": params, "reason": reason},
            caused_by=caused_by,
        )

    def _check_student(self, student: str) -> None:
        if student not in self.students:
            raise ActionRefused(f"unknown student {student!r}")

    def _check_session(self, session: int, week: int) -> None:
        if not 1 <= session <= self.total_sessions:
            raise ActionRefused(f"no session {session}")
        if session_week(session) > week:
            raise ActionRefused(f"session {session} has not happened by week {week}")

    def _check_own_intent(self, student: str, session: int) -> None:
        self._check_student(student)
        if self.current_session is not None and session != self.current_session:
            raise ActionRefused(f"only the current session ({self.current_session}) can be decided")
        if (student, session) in self.present or session in self.cancelled:
            raise ActionRefused(f"session {session} is already recorded or cancelled")

    def _do_attend(self, actor, week, caused_by, session: int, travel_buffer_min: int | None = None) -> Event:
        """A student plans to attend; optionally with a new travel buffer (a strategy change)."""
        self._check_own_intent(actor, session)
        state_change = {f"intent.{actor}.{session}": {"from": None, "to": "attend"}}
        if travel_buffer_min is not None:
            if not 0 <= travel_buffer_min <= 180:
                raise ActionRefused("travel_buffer_min must be 0-180")
            state_change[f"travel_buffer.{actor}"] = {"from": self.travel_buffer.get(actor), "to": travel_buffer_min}
            self.travel_buffer[actor] = travel_buffer_min
        event = self.emit("student_plans_attend", actor, week, payload={"session": session},
                          state_change=state_change, caused_by=caused_by)
        self.intents[(actor, session)] = ("attend", event.event_id)
        return event

    def _do_skip(self, actor, week, caused_by, session: int) -> Event:
        self._check_own_intent(actor, session)
        event = self.emit("student_plans_skip", actor, week, payload={"session": session},
                          state_change={f"intent.{actor}.{session}": {"from": None, "to": "skip"}},
                          caused_by=caused_by)
        self.intents[(actor, session)] = ("skip", event.event_id)
        return event

    def _do_ask_advisor(self, actor, week, caused_by, message: str = "") -> Event:
        self._check_student(actor)
        return self.emit("advisor_asked", actor, week, payload={"message": message[:300]}, caused_by=caused_by)

    def _do_advise_student(self, actor, week, caused_by, student: str, advice: str = "") -> Event:
        self._check_student(student)
        return self.emit("advice_given", actor, week, payload={"student": student, "advice": advice[:300]},
                         caused_by=caused_by)

    def _do_record_attendance(
        self, actor, week, caused_by, student: str, session: int, present: bool, late: bool = False
    ) -> Event:
        self._check_student(student)
        self._check_session(session, week)
        if session in self.cancelled:
            raise ActionRefused(f"session {session} was cancelled")
        if (student, session) in self.present:
            raise ActionRefused("attendance already recorded; use edit_attendance")
        self.present[(student, session)] = present
        self.completed.add(session)
        event = self.emit(
            "attendance_recorded",
            actor,
            week,
            payload={"student": student, "session": session, "late": late},
            state_change={f"attendance.{student}.{session}": {"from": None, "to": _mark(present)}},
            caused_by=caused_by,
        )
        self.record_event[(student, session)] = event.event_id
        return event

    def _do_edit_attendance(self, actor, week, caused_by, student: str, session: int, present: bool) -> Event:
        if (student, session) not in self.present:
            raise ActionRefused("no attendance record to edit")
        before = self.present[(student, session)]
        self.present[(student, session)] = present
        event = self.emit(
            "attendance_edited",
            actor,
            week,
            payload={"student": student, "session": session},
            state_change={f"attendance.{student}.{session}": {"from": _mark(before), "to": _mark(present)}},
            caused_by=[*caused_by, self.record_event[(student, session)]],
        )
        self.record_event[(student, session)] = event.event_id
        return event

    def _do_cancel_session(self, actor, week, caused_by, session: int) -> Event:
        self._check_session(session, week)
        if session in self.completed:
            raise ActionRefused(f"session {session} already took place")
        self.cancelled.add(session)
        self.completed.add(session)
        return self.emit(
            "session_cancelled",
            actor,
            week,
            payload={"session": session},
            state_change={f"session.{session}": {"from": "scheduled", "to": "cancelled"}},
            caused_by=caused_by,
        )

    def _do_submit_exception_request(self, actor, week, caused_by, sessions: list[int], reason: str) -> Event:
        student = actor  # a student can only ask for themself
        self._check_student(student)
        if not sessions:
            raise ActionRefused("a request must cover at least one session")
        covered = {
            s for r in self.requests.values() if r.student == student and r.status != "rejected" for s in r.sessions
        }
        for session in sessions:
            self._check_session(session, week)
            if session not in self.completed or session in self.cancelled:
                raise ActionRefused(f"session {session} is not a completed, countable session")
            if session in covered:
                raise ActionRefused(f"session {session} is already covered by a request")
        request_id = f"R{len(self.requests) + 1}"
        absences = [self.record_event[(student, s)] for s in sessions if (student, s) in self.record_event]
        event = self.emit(
            "exception_request_submitted",
            actor,
            week,
            payload={"request_id": request_id, "student": student, "sessions": sessions, "reason": reason},
            state_change={f"request.{request_id}": {"from": None, "to": "pending"}},
            caused_by=[*caused_by, *absences],
        )
        self.requests[request_id] = ExceptionRequest(
            request_id=request_id,
            student=student,
            sessions=sorted(sessions),
            reason=reason,
            submitted_week=week,
            submitted_event=event.event_id,
        )
        return event

    def _do_process_exception_queue(self, actor, week, caused_by, capacity: int) -> Event:
        """FIFO within this week's capacity. A request is approved only if every session it
        covers is a recorded absence of that student."""
        if capacity < 0:
            raise ActionRefused("capacity cannot be negative")
        if week in self.queue_weeks:
            raise ActionRefused(f"the queue was already processed in week {week}")
        self.queue_weeks.add(week)
        pending = [r for r in self.requests.values() if r.status == "pending"]
        processed, held = pending[:capacity], pending[capacity:]
        decisions = []
        for request in processed:
            valid = all(self.present.get((request.student, s)) is False for s in request.sessions)
            request.status = "approved" if valid else "rejected"
            request.decided_week = week
            decisions.append(
                self.emit(
                    "exception_request_decided",
                    actor,
                    week,
                    payload={
                        "request_id": request.request_id,
                        "decision": request.status,
                        "waited_weeks": week - request.submitted_week,
                        "rule": "approved if every covered session is a recorded absence",
                    },
                    state_change={f"request.{request.request_id}": {"from": "pending", "to": request.status}},
                    caused_by=[*caused_by, request.submitted_event],
                ).event_id
            )
        event = self.emit(
            "exception_queue_processed",
            actor,
            week,
            payload={
                "capacity": capacity,
                "processed": [r.request_id for r in processed],
                "pending": [r.request_id for r in held],
            },
            caused_by=[*caused_by, *decisions],
        )
        if held:
            self.emit(
                "queue_over_capacity",
                actor,
                week,
                payload={"capacity": capacity, "held": [r.request_id for r in held]},
                caused_by=[event.event_id, *(r.submitted_event for r in held)],
            )
        return event

    def _do_evaluate_eligibility(self, actor, week, caused_by, student: str) -> Event:
        self._check_student(student)
        now = self.attendance(student)
        if_approved = self.attendance(student, assume_pending_approved=True)
        eligible = now.pct is not None and now.pct >= self.threshold_pct
        return self.emit(
            "eligibility_evaluated",
            actor,
            week,
            payload={
                "student": student,
                "threshold_pct": self.threshold_pct,
                "attendance": now.model_dump(),
                "attendance_if_pending_approved": if_approved.model_dump(),
                "pending_requests": now.pending,
                "eligible": eligible,
            },
            state_change={f"eligibility.{student}": {"from": None, "to": "eligible" if eligible else "not eligible"}},
            caused_by=[*caused_by, *self.pending_causes(now.pending)],
        )

    def pending_causes(self, request_ids: list[str]) -> list[str]:
        """For each pending request: its submission, and the latest queue event that held it."""
        causes = []
        for request_id in request_ids:
            causes.append(self.requests[request_id].submitted_event)
            held = [e for e in self.events if e.type == "queue_over_capacity" and request_id in e.payload["held"]]
            if held:
                causes.append(held[-1].event_id)
        return causes

    # --- calculations ----------------------------------------------------------------------

    def attendance(self, student: str, assume_pending_approved: bool = False) -> Attendance:
        own = [r for r in self.requests.values() if r.student == student]
        excused_status = {"approved", "pending"} if assume_pending_approved else {"approved"}
        excused = {s for r in own if r.status in excused_status for s in r.sessions}
        countable = sorted(s for s in self.completed if s not in self.cancelled and s not in excused)
        attended = sum(1 for s in countable if self.present.get((student, s)) is True)
        return Attendance(
            student=student,
            attended=attended,
            countable=len(countable),
            pct=round(attended * 100 / len(countable), 1) if countable else None,
            pending=[r.request_id for r in own if r.status == "pending"],
            approved=[r.request_id for r in own if r.status == "approved"],
            rejected=[r.request_id for r in own if r.status == "rejected"],
        )

    def calculate_attendance(self, student: str, week: int, assume_pending_approved: bool = False) -> Event:
        result = self.attendance(student, assume_pending_approved)
        pending_events = [self.requests[r].submitted_event for r in self.attendance(student).pending]
        return self.emit(
            "attendance_calculated",
            "engine",
            week,
            payload={"assume_pending_approved": assume_pending_approved, **result.model_dump()},
            caused_by=pending_events,
        )


def _mark(present: bool) -> str:
    return "present" if present else "absent"


# --- fixed test cases (`cli engine check --case <file>`) ---------------------------------------


def run_case(case: dict[str, Any]) -> list[str]:
    """Plays a fixed case through the engine and returns the lines to print, each with its event ID."""
    engine = Engine(case["threshold_pct"], case["students"])
    focus = case["focus_student"]
    absent = {student: set(sessions) for student, sessions in case["absent"].items()}
    requests = sorted(case["requests"], key=lambda r: min(r["sessions"]))
    last_week = session_week(engine.total_sessions)

    for week in range(1, last_week + 1):
        week_sessions = [s for s in range(1, engine.total_sessions + 1) if session_week(s) == week]
        for session in week_sessions:
            for student in engine.students:
                engine.propose(
                    "faculty", "faculty", "record_attendance", week,
                    student=student, session=session, present=session not in absent.get(student, set()),
                )
        for request in requests:
            if session_week(max(request["sessions"])) == week:
                engine.propose(
                    "student", request["student"], "submit_exception_request", week,
                    sessions=request["sessions"], reason=request["reason"],
                )

    now = engine.calculate_attendance(focus, last_week)
    projected = engine.calculate_attendance(focus, last_week, assume_pending_approved=True)
    queue = engine.propose("attendance_admin", "attendance_admin", "process_exception_queue", last_week,
                           capacity=case["admin_capacity"])
    check = case["permission_check"]
    refused = engine.propose(check["role"], check["actor"], check["action"], last_week, **check["params"])

    n_pending = len(now.payload["pending"])
    p = queue.payload
    return [
        f"{_fraction(now)} ({n_pending} exceptions pending)  [{now.event_id}]",
        f"{_fraction(projected)} (if {n_pending} approved)  [{projected.event_id}]",
        f"queue FIFO: {','.join(p['processed'])} processed, {','.join(p['pending']) or 'none'} pending "
        f"(capacity {p['capacity']})  [{queue.event_id}]",
        f"{check['role']} {check['action']}: "
        + (f"rejected ({refused.payload['reason']})" if refused.type == "action_rejected" else "allowed")
        + f"  [{refused.event_id}]",
    ]


def _fraction(event: Event) -> str:
    return Attendance(**{k: event.payload[k] for k in Attendance.model_fields}).text()
