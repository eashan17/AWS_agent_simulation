"""The general engine: state, actions, permissions, preconditions, duties, requests and counts.

Everything it knows about the rule world comes from a checked Template (rulestorm/core/model.py)
plus the blueprint's values. No policy rule and no domain word lives here.

People only propose actions. The engine checks the person's role may take the action (reason
`permission`), the parameters, and the action's preconditions (reason `precondition: <name>`),
then commits the action's effects. Every committed or refused action becomes an event with an
ID, the state change it made, and `caused_by` links to the events that led to it.

Recording is not an action: the recorder rule (`record_step`) records met or missed for every
person who owes a duty, applying each person's plan and any obstacle.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field

from rulestorm.core.model import Action, Duty, Template

Outcome = Literal["met", "missed"]
NO_PLAN = "meet"  # a person with no plan is treated as planning to meet the duty


class Event(BaseModel):
    event_id: str
    seq: int
    period: int
    step: int | None = None
    type: str
    actor: str
    payload: dict[str, Any] = Field(default_factory=dict)
    state_change: dict[str, Any] = Field(default_factory=dict)
    caused_by: list[str] = Field(default_factory=list)


class Request(BaseModel):
    request_id: str
    request_type: str
    person: str
    steps: list[int]
    reason: str = ""
    filed_period: int
    filed_event: str
    status: Literal["pending", "approved", "rejected"] = "pending"
    decided_period: int | None = None


class Obstacle(BaseModel):
    """An obstacle disruption that hits one step: its event, who it hits, and the delay."""

    event_id: str
    duty: str
    people: list[str]
    delay: int


class CountResult(BaseModel):
    count: str
    person: str
    kind: Literal["rate", "tally"]
    met: int
    due: int
    missed: int
    value: float | None  # rate: percent (None while nothing is due); tally: missed
    pending: list[str]
    approved: list[str]
    rejected: list[str]

    def text(self) -> str:
        if self.kind == "tally":
            return str(self.missed)
        pct = "n/a" if self.value is None else f"{self.value:.1f}%"
        return f"{self.met}/{self.due} = {pct}"


class Refused(Exception):
    """An action failed a check; the engine records the refusal instead of committing."""


class Engine:
    def __init__(self, template: Template, values: dict[str, Any]) -> None:
        self.t = template
        self.values = dict(values)
        self.role_of = {p.id: p.role for p in template.people}
        self.roles = {r.id: r for r in template.roles}
        self.actions = {a.id: a for a in template.actions}
        self.duties = {d.id: d for d in template.duties}
        self.request_types = {r.id: r for r in template.request_types}
        self.counts = {c.id: c for c in template.counts}
        self.total_steps = template.calendar.periods * template.calendar.steps_per_period
        self.step_label = template.calendar.step_label

        self.events: list[Event] = []
        self.records: dict[tuple[str, str, int], Outcome] = {}  # (duty, person, step) -> outcome
        self.record_event: dict[tuple[str, str, int], str] = {}
        self.recorded_steps: dict[str, set[int]] = {d: set() for d in self.duties}
        self.cancelled: dict[str, set[int]] = {d: set() for d in self.duties}
        self.plans: dict[tuple[str, str, int], tuple[str, str]] = {}  # -> (meet|miss, event_id)
        self.requests: dict[str, Request] = {}  # insertion order = filing order
        self.attributes: dict[tuple[str, str], int] = {}
        for p in template.parameters:
            if p.type == "attribute":
                for person, value in (self.values.get(p.name) or {}).items():
                    self.attributes[(person, p.attribute)] = value
        # Set by the term loop; while set, plans can be made only for this step.
        self.current_step: int | None = None

    # --- values and the calendar ----------------------------------------------------------

    def value(self, name: str) -> Any:
        if name not in self.values:
            raise KeyError(f"missing value for parameter '{name}'")
        return self.values[name]

    def period_of(self, step: int) -> int:
        return (step - 1) // self.t.calendar.steps_per_period + 1

    def owes(self, person: str, duty: Duty) -> bool:
        return self.role_of.get(person) == duty.owed_by

    def people_owing(self, duty: Duty) -> list[str]:
        return [p for p in self.role_of if self.owes(p, duty)]

    def person_with_role(self, role: str) -> str:
        return next(p for p, r in self.role_of.items() if r == role)

    # --- event log ------------------------------------------------------------------------

    def emit(self, type: str, actor: str, period: int, step: int | None = None,
             payload: dict[str, Any] | None = None, state_change: dict[str, Any] | None = None,
             caused_by: list[str] | None = None) -> Event:
        seq = len(self.events) + 1
        event = Event(event_id=f"E-{seq:04d}", seq=seq, period=period, step=step, type=type, actor=actor,
                      payload=payload or {}, state_change=state_change or {},
                      caused_by=list(dict.fromkeys(caused_by or [])))
        self.events.append(event)
        return event

    def event(self, event_id: str) -> Event:
        return self.events[int(event_id.removeprefix("E-")) - 1]

    # --- actions: people propose, the engine validates and commits ---------------------------

    def propose(self, actor: str, action_id: str, period: int, caused_by: list[str] | None = None,
                **params: Any) -> Event:
        caused_by = caused_by or []
        role = self.role_of.get(actor)
        if role is None:
            return self._refuse(actor, None, action_id, period, caused_by, params, f"unknown person {actor!r}")
        if action_id not in self.roles[role].actions:
            return self._refuse(actor, role, action_id, period, caused_by, params, "permission")
        action = self.actions[action_id]
        try:
            self._check_params(action, params)
            return self._commit(actor, action, period, caused_by, params)
        except Refused as exc:
            return self._refuse(actor, role, action_id, period, caused_by, params, str(exc))

    def _refuse(self, actor, role, action, period, caused_by, params, reason) -> Event:
        return self.emit("action_rejected", actor, period, step=self.current_step,
                         payload={"role": role, "action": action, "params": params, "reason": reason},
                         caused_by=caused_by)

    def _check_params(self, action: Action, params: dict[str, Any]) -> None:
        specs = {p.name: p for p in action.params}
        unknown = sorted(set(params) - set(specs))
        if unknown:
            raise Refused(f"bad parameters: unknown {', '.join(unknown)}")
        for spec in action.params:
            if spec.name not in params or params[spec.name] is None:
                if spec.required:
                    raise Refused(f"bad parameters: missing {spec.name}")
                continue
            value = params[spec.name]
            if spec.type in ("int", "step") and (isinstance(value, bool) or not isinstance(value, int)):
                raise Refused(f"bad parameters: {spec.name} must be a whole number")
            if spec.type == "step_list" and (not isinstance(value, list) or not value
                                             or any(isinstance(v, bool) or not isinstance(v, int) for v in value)):
                raise Refused(f"bad parameters: {spec.name} must be a non-empty list of {self.step_label}s")
            if spec.type == "step_list" and len(set(value)) != len(value):
                raise Refused(f"bad parameters: {spec.name} lists a {self.step_label} twice")
            if spec.type == "bool" and not isinstance(value, bool):
                raise Refused(f"bad parameters: {spec.name} must be true or false")
            if spec.type in ("str", "person") and not isinstance(value, str):
                raise Refused(f"bad parameters: {spec.name} must be text")
            if spec.type == "person" and value not in self.role_of:
                raise Refused(f"bad parameters: unknown person {value!r}")
            steps = value if spec.type == "step_list" else [value] if spec.type == "step" else []
            for step in steps:
                if not 1 <= step <= self.total_steps:
                    raise Refused(f"bad parameters: no {self.step_label} {step}")

    def _param_of_type(self, action: Action, params: dict[str, Any], *types: str) -> Any:
        return next((params.get(p.name) for p in action.params if p.type in types), None)

    def _commit(self, actor: str, action: Action, period: int, caused_by: list[str],
                params: dict[str, Any]) -> Event:
        steps = self._param_of_type(action, params, "step", "step_list")
        steps = [steps] if isinstance(steps, int) else list(steps or [])
        target = self._param_of_type(action, params, "person") or actor

        # Every check runs before anything is committed, so a refusal changes nothing.
        for effect in action.effects:
            duty = self._duty_of(effect)
            if effect.kind in ("plan_meet", "plan_miss") and self.current_step is not None:
                if any(s != self.current_step for s in steps):
                    raise Refused("precondition: current_step")
            if duty is not None:
                for precondition in action.preconditions:
                    for step in steps:
                        self._precondition(precondition, actor, target, duty, step, effect.request_type)
            if effect.kind == "file_request":
                timing = self.value(self.request_types[effect.request_type].timing_param)
                need = "occurrence_recorded" if timing == "after_missed" else "occurrence_not_yet"
                for step in steps:
                    self._precondition(need, actor, actor, duty, step, effect.request_type)
            if effect.kind == "set_attribute" and params.get(effect.attribute) is not None:
                attribute = next(a for a in self.t.attributes if a.id == effect.attribute)
                if not attribute.min <= params[effect.attribute] <= attribute.max:
                    raise Refused(f"bad parameters: {effect.attribute} must be {attribute.min}-{attribute.max}")
            if effect.kind in ("endorse", "decide_request"):
                raise Refused(f"unsupported effect {effect.kind}")  # slices L9a-L9b

        events = [self._apply(effect, actor, target, action, period, steps, params, caused_by)
                  for effect in action.effects]
        events = [e for e in events if e is not None]
        return events[0]

    def _duty_of(self, effect) -> Duty | None:
        if effect.duty:
            return self.duties[effect.duty]
        if effect.request_type:
            return self.duties[self.request_types[effect.request_type].covers]
        return None

    def _precondition(self, name: str, actor: str, target: str, duty: Duty, step: int,
                      request_type: str | None) -> None:
        recorded = (duty.id, target, step) in self.records
        ok = {
            "own_occurrence": lambda: self.owes(actor, duty) and target == actor,
            "occurrence_recorded": lambda: recorded,
            "occurrence_not_yet": lambda: (step not in self.recorded_steps[duty.id]
                                           and step not in self.cancelled[duty.id]),
            "not_already_covered": lambda: not self._covered(actor, step, request_type),
        }[name]()
        if not ok:
            raise Refused("already covered" if name == "not_already_covered" else f"precondition: {name}")

    def _covered(self, person: str, step: int, request_type: str | None) -> bool:
        return any(r.person == person and r.status != "rejected" and step in r.steps
                   and (request_type is None or r.request_type == request_type)
                   for r in self.requests.values())

    def _apply(self, effect, actor, target, action, period, steps, params, caused_by) -> Event | None:
        kind = effect.kind
        step = steps[0] if steps else None
        if kind in ("plan_meet", "plan_miss"):
            plan = "meet" if kind == "plan_meet" else "miss"
            event = self.emit("duty_planned", actor, period, step,
                              payload={"action": action.id, "duty": effect.duty, "plan": plan},
                              state_change={f"plan.{effect.duty}.{actor}.{step}": {"from": None, "to": plan}},
                              caused_by=caused_by)
            self.plans[(effect.duty, actor, step)] = (plan, event.event_id)
            return event
        if kind == "set_attribute":
            new = params.get(effect.attribute)
            if new is None:
                return None
            key = (actor, effect.attribute)
            event = self.emit("attribute_set", actor, period, self.current_step,
                              payload={"action": action.id, "attribute": effect.attribute},
                              state_change={f"{effect.attribute}.{actor}": {"from": self.attributes.get(key), "to": new}},
                              caused_by=caused_by)
            self.attributes[key] = new
            return event
        if kind == "file_request":
            return self._file_request(actor, effect.request_type, action, period, steps, params, caused_by)
        if kind == "correct_record":
            key = (effect.duty, target, step)
            before = self.records[key]
            after: Outcome = "met" if self._param_of_type(action, params, "bool") else "missed"
            self.records[key] = after
            event = self.emit("record_corrected", actor, period, step,
                              payload={"action": action.id, "duty": effect.duty, "person": target},
                              state_change={f"record.{effect.duty}.{target}.{step}": {"from": before, "to": after}},
                              caused_by=[*caused_by, self.record_event[key]])
            self.record_event[key] = event.event_id
            return event
        if kind == "cancel_occurrence":
            self.cancelled[effect.duty].add(step)
            return self.emit("occurrence_cancelled", actor, period, step,
                             payload={"action": action.id, "duty": effect.duty},
                             state_change={f"occurrence.{effect.duty}.{step}": {"from": "scheduled", "to": "cancelled"}},
                             caused_by=caused_by)
        # message / respond: no state change, the words are kept for the people involved
        text = {k: (v[:300] if isinstance(v, str) else v) for k, v in params.items()}
        to = effect.to if kind == "message" else self._param_of_type(action, params, "person")
        return self.emit("message_sent" if kind == "message" else "response_given", actor, period,
                         self.current_step, payload={"action": action.id, "to": to, **text}, caused_by=caused_by)

    def _file_request(self, actor, request_type, action, period, steps, params, caused_by) -> Event:
        rt = self.request_types[request_type]
        request_id = f"R{len(self.requests) + 1}"
        covered = [self.record_event[(rt.covers, actor, s)] for s in steps if (rt.covers, actor, s) in self.record_event]
        reason = next((v for p in action.params if p.type == "str" and (v := params.get(p.name))), "")
        event = self.emit("request_filed", actor, period, self.current_step,
                          payload={"request_id": request_id, "request_type": request_type, "person": actor,
                                   "steps": sorted(steps), "reason": reason[:300]},
                          state_change={f"request.{request_id}": {"from": None, "to": "pending"}},
                          caused_by=[*caused_by, *covered])
        self.requests[request_id] = Request(request_id=request_id, request_type=request_type, person=actor,
                                            steps=sorted(steps), reason=reason[:300], filed_period=period,
                                            filed_event=event.event_id)
        return event

    def decide_request(self, request_id: str, outcome: Literal["approved", "rejected"], actor: str,
                       period: int, rule: str, caused_by: list[str] | None = None) -> Event:
        """Sets a pending request's outcome. Called by the queue processor rule (slice L3) or an
        LLM decider (slice L9b); the caller enforces capacity and order."""
        request = self.requests[request_id]
        if request.status != "pending":
            raise ValueError(f"request {request_id} is already {request.status}")
        request.status, request.decided_period = outcome, period
        return self.emit("request_decided", actor, period,
                         payload={"request_id": request_id, "decision": outcome, "rule": rule,
                                  "waited_periods": period - request.filed_period},
                         state_change={f"request.{request_id}": {"from": "pending", "to": outcome}},
                         caused_by=[*(caused_by or []), request.filed_event])

    # --- the recorder rule --------------------------------------------------------------------

    def record_step(self, step: int, obstacles: list[Obstacle] | None = None) -> list[Event]:
        """Records met or missed for everyone who owes each duty at this step, applying their plan
        and any obstacle (a delay above the person's obstacle attribute means missed)."""
        period = self.period_of(step)
        recorded = []
        for duty in self.t.duties:
            if step in self.cancelled[duty.id] or step in self.recorded_steps[duty.id]:
                continue
            self.recorded_steps[duty.id].add(step)
            recorder = self.person_with_role(duty.recorded_by)
            for person in self.people_owing(duty):
                plan, plan_event = self.plans.get((duty.id, person, step), (NO_PLAN, None))
                causes = [plan_event] if plan_event else []
                outcome: Outcome = "met" if plan == "meet" else "missed"
                hit_by = None
                if outcome == "met" and duty.obstacle_attribute:
                    for o in obstacles or []:
                        if o.duty == duty.id and person in o.people:
                            slack = self.attributes.get((person, duty.obstacle_attribute))
                            if slack is None:
                                raise KeyError(f"missing value '{duty.obstacle_attribute}' for {person}")
                            if o.delay > slack:
                                outcome, hit_by = "missed", o
                                causes = [o.event_id, *causes]
                                break
                key = (duty.id, person, step)
                self.records[key] = outcome
                event = self.emit("duty_recorded", recorder, period, step,
                                  payload={"duty": duty.id, "person": person, "outcome": outcome,
                                           "plan": plan, "obstacle": hit_by.event_id if hit_by else None},
                                  state_change={f"record.{duty.id}.{person}.{step}": {"from": None, "to": outcome}},
                                  caused_by=causes)
                self.record_event[key] = event.event_id
                recorded.append(event)
        return recorded

    # --- counts -----------------------------------------------------------------------------

    def count(self, count_id: str, person: str, assume_pending_approved: bool = False) -> CountResult:
        """Always recomputed from the records. Pending requests count as missed unless assumed approved."""
        c = self.counts[count_id]
        own = [r for r in self.requests.values() if r.person == person
               and self.request_types[r.request_type].covers == c.duty]
        excused_status = {"approved", "pending"} if assume_pending_approved else {"approved"}
        excused = ({s for r in own if r.status in excused_status for s in r.steps}
                   if "approved_request" in c.exclude else set())
        cancelled = self.cancelled[c.duty] if "cancelled" in c.exclude else set()
        due = sorted(s for s in self.recorded_steps[c.duty] | cancelled
                     if s not in cancelled and s not in excused and (c.duty, person, s) in self.records)
        met = sum(1 for s in due if self.records[(c.duty, person, s)] == "met")
        missed = len(due) - met
        if c.kind == "rate":
            value = round(met * 100 / len(due), 1) if due else None
        else:
            value = float(missed)
        return CountResult(count=count_id, person=person, kind=c.kind, met=met, due=len(due), missed=missed,
                           value=value, pending=[r.request_id for r in own if r.status == "pending"],
                           approved=[r.request_id for r in own if r.status == "approved"],
                           rejected=[r.request_id for r in own if r.status == "rejected"])

    def calculate(self, count_id: str, person: str, period: int, assume_pending_approved: bool = False) -> Event:
        result = self.count(count_id, person, assume_pending_approved)
        return self.emit("count_calculated", "engine", period,
                         payload={"assume_pending_approved": assume_pending_approved, **result.model_dump()},
                         caused_by=[self.requests[r].filed_event for r in self.count(count_id, person).pending])


# --- fixed test cases (`cli engine check --case <file> --core`) ----------------------------------


def run_case(case: dict[str, Any], template: Template) -> list[str]:
    """Plays a fixed case through the general engine; returns the lines to print, each with its event ID."""
    engine = Engine(template, case["values"])
    count_id = case["count"]
    focus = case["focus_student"]
    absent = {person: set(steps) for person, steps in case["absent"].items()}
    requests = sorted(case["requests"], key=lambda r: min(r["sessions"]))
    plan_actions = {e.kind: a.id for a in template.actions for e in a.effects if e.kind in ("plan_meet", "plan_miss")}
    file_action = next(a.id for a in template.actions if any(e.kind == "file_request" for e in a.effects))
    step_param = lambda action_id: next(p.name for p in engine.actions[action_id].params  # noqa: E731
                                        if p.type in ("step", "step_list"))

    for step in range(1, engine.total_steps + 1):
        engine.current_step = step
        for person, steps in absent.items():
            if step in steps:
                engine.propose(person, plan_actions["plan_miss"], engine.period_of(step),
                               **{step_param(plan_actions["plan_miss"]): step})
        engine.record_step(step)
        engine.current_step = None
        for request in requests:
            if max(request["sessions"]) == step:
                engine.propose(request["student"], file_action, engine.period_of(step),
                               **{step_param(file_action): request["sessions"], "reason": request["reason"]})

    last_period = template.calendar.periods
    now = engine.calculate(count_id, focus, last_period)
    projected = engine.calculate(count_id, focus, last_period, assume_pending_approved=True)
    check = case["permission_check"]
    refused = engine.propose(check["actor"], check["action"], last_period, **check["params"])

    word = template.terms.get("requests", "requests")
    n_pending = len(now.payload["pending"])
    return [
        f"{CountResult(**_result(now)).text()} ({n_pending} {word} pending)  [{now.event_id}]",
        f"{CountResult(**_result(projected)).text()} (if {n_pending} approved)  [{projected.event_id}]",
        f"{check['role']} {check['action']}: "
        + (f"rejected ({refused.payload['reason']})" if refused.type == "action_rejected" else "allowed")
        + f"  [{refused.event_id}]",
    ]


def _result(event: Event) -> dict[str, Any]:
    return {k: event.payload[k] for k in CountResult.model_fields}
