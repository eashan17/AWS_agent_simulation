"""The general engine: state, actions, permissions, preconditions, duties, requests and counts.

Everything it knows about the rule world comes from a checked Template (rulestorm/core/model.py)
plus the blueprint's values. No policy rule and no domain word lives here.

People only propose actions. The engine checks the person's role may take the action (reason
`permission`), the parameters, and the action's preconditions (reason `precondition: <name>`),
then commits the action's effects. A refusal records the reason code (for summaries and checks)
and a plain `detail` the person is shown, written here from the fixed reason library and the
template's own labels, so no template needs its own refusal sentences. Every committed or refused action becomes an event with an
ID, the state change it made, and `caused_by` links to the events that led to it.

Recording is not an action: the recorder rule (`record_step`) records met or missed for every
person who owes a duty, applying each person's plan and any obstacle.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field

from rulestorm.core.model import REQUEST_OUTCOMES, Action, Duty, Template

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
    recorded_at_filing: list[int] = Field(default_factory=list, description="covered steps already recorded")
    dropped: list[dict[str, Any]] = Field(default_factory=list, description="partial_at_submit: steps left out")
    approved_steps: list[int] = Field(default_factory=list)  # partial_at_decide: may be a subset
    rejected_steps: list[int] = Field(default_factory=list)
    # Consent (request types with endorsed_by): a request waits for it before it is queued;
    # refused consent ends it (status rejected).
    endorsement: Literal["awaiting", "given", "refused"] | None = None


class DisruptionValue(BaseModel):
    """One disruption from the blueprint. `kind` is a disruption ID from the template;
    `steps` are positions within the period (1 = its first step)."""

    kind: str
    period: int = Field(ge=1)
    steps: list[int] = Field(default_factory=list)
    people: list[str] = Field(default_factory=list)
    delay: int = Field(0, ge=0)
    capacity: int | None = Field(None, ge=0)
    description: str = ""


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


def count_value(kind: str, met: int, missed: int) -> float | None:
    """A count's value from its met and missed records: a rate is the % met (None before anything
    is due), a tally the number missed. Shared by the engine and the stress-variant maths."""
    if kind == "rate":
        due = met + missed
        return round(met * 100 / due, 1) if due else None
    return float(missed)


def passes(value: float | None, comparison: str, threshold: float) -> bool:
    """Whether a count's value passes a check (no value yet never passes)."""
    if value is None:
        return False
    return {">=": value >= threshold, "<=": value <= threshold,
            ">": value > threshold, "<": value < threshold}[comparison]


class Refused(Exception):
    """An action failed a check; the engine records the refusal instead of committing.
    `reason` is the code from the fixed library; `detail` says it in plain words."""

    def __init__(self, reason: str, detail: str | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.detail = detail or reason


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
        self.disruption_kinds = {d.id: d for d in template.disruptions}
        self.disruptions = self._disruptions()
        self.capacity_override: dict[tuple[str, int], tuple[int, str]] = {}  # (request type, period) -> (cap, event)
        self.obstacles_by_step: dict[int, list[Obstacle]] = {}
        self.processed_slots: set[tuple[str, int, int | None]] = set()
        self.ladder_reached: dict[tuple[str, str], int] = {}  # (check, person) -> ladder steps reached
        # Request types decided by an LLM person: the slot open now (only while it is open can
        # its offered requests be decided).
        self.open_slots: dict[str, dict[str, Any]] = {}

    def _disruptions(self) -> list[DisruptionValue]:
        names = [p.name for p in self.t.parameters if p.type == "disruptions"]
        found = [DisruptionValue.model_validate(d) for name in names for d in self.values.get(name) or []]
        spp = self.t.calendar.steps_per_period
        for d in found:
            kind = self.disruption_kinds.get(d.kind)
            if kind is None:
                raise ValueError(f"unknown disruption kind '{d.kind}'")
            if d.period > self.t.calendar.periods or any(not 1 <= s <= spp for s in d.steps):
                raise ValueError(f"disruption '{d.kind}' is outside the calendar")
            unknown = [p for p in d.people if p not in self.role_of]
            if unknown:
                raise ValueError(f"disruption '{d.kind}' names unknown people: {', '.join(unknown)}")
            if kind.kind == "obstacle" and (not d.steps or not d.people or d.delay <= 0):
                raise ValueError(f"obstacle '{d.kind}' needs steps, people and a delay above 0")
            if kind.kind == "obstacle":
                duty = self.duties[kind.duty]
                free = [p for p in d.people if not self.owes(p, duty)]
                if free:
                    raise ValueError(f"obstacle '{d.kind}' hits people who don't owe '{duty.id}': {', '.join(free)}")
            if kind.kind == "cancellation" and not d.steps:
                raise ValueError(f"cancellation '{d.kind}' needs steps")
            if kind.kind == "capacity" and d.capacity is None:
                raise ValueError(f"capacity disruption '{d.kind}' needs a capacity")
        return found

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
            what = self.actions[action_id].label if action_id in self.actions else f"take the action {action_id!r}"
            return self._refuse(actor, role, action_id, period, caused_by, params, "permission",
                                f"a {self.roles[role].label} is not allowed to {what}")
        action = self.actions[action_id]
        try:
            self._check_params(action, params)
            return self._commit(actor, action, period, caused_by, params)
        except Refused as exc:
            return self._refuse(actor, role, action_id, period, caused_by, params, exc.reason, exc.detail)

    def _refuse(self, actor, role, action, period, caused_by, params, reason, detail=None) -> Event:
        return self.emit("action_rejected", actor, period, step=self.current_step,
                         payload={"role": role, "action": action, "params": params, "reason": reason,
                                  "detail": detail or reason},
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
            if spec.type == "request" and (not isinstance(value, str) or value not in self.requests):
                raise Refused(f"bad parameters: unknown {self.t.terms.get('request', 'request')} {value!r}")
            if spec.type == "outcome" and value not in REQUEST_OUTCOMES:
                raise Refused("bad parameters: outcome",
                              f"{spec.name} must be one of {', '.join(REQUEST_OUTCOMES)}, not {value!r}")
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
        dropped: list[dict[str, Any]] = []
        for effect in action.effects:
            duty = self._duty_of(effect)
            if effect.kind in ("plan_meet", "plan_miss") and self.current_step is not None:
                if any(s != self.current_step for s in steps):
                    raise Refused("precondition: current_step", f"plans can be made only for the current "
                                  f"{self.step_label} ({self.step_label} {self.current_step})")
            if effect.kind == "file_request":
                steps, dropped = self._request_steps(actor, action, effect.request_type, duty, steps)
            elif duty is not None:
                for precondition in action.preconditions:
                    for step in steps:
                        self._precondition(precondition, actor, target, duty, step, effect.request_type)
            if effect.kind == "set_attribute" and params.get(effect.attribute) is not None:
                attribute = next(a for a in self.t.attributes if a.id == effect.attribute)
                if not attribute.min <= params[effect.attribute] <= attribute.max:
                    raise Refused(f"bad parameters: {effect.attribute} must be {attribute.min}-{attribute.max}")
            if effect.kind == "endorse":
                request = self.requests[self._param_of_type(action, params, "request")]
                if (request.request_type != effect.request_type or request.status != "pending"
                        or request.endorsement != "awaiting"):
                    word = self.t.terms.get("request", "request")
                    raise Refused("precondition: awaiting_endorsement",
                                  f"{word} {request.request_id} is not waiting for consent")
            if effect.kind == "decide_request":
                self._check_decision(action, effect.request_type, params, steps)

        events = [self._apply(effect, actor, target, action, period, steps, params, caused_by, dropped)
                  for effect in action.effects]
        events = [e for e in events if e is not None]
        return events[0]

    def _request_steps(self, actor: str, action: Action, request_type: str, duty: Duty,
                       steps: list[int]) -> tuple[list[int], list[dict[str, Any]]]:
        """Checks each covered step against the action's preconditions and the policy's request
        timing. With partial_at_submit the failing steps are dropped and the rest kept;
        without it, one failing step refuses the whole request."""
        rt = self.request_types[request_type]
        timing = self.value(rt.timing_param)
        needed = [*action.preconditions, "occurrence_recorded" if timing == "after_missed" else "occurrence_not_yet"]
        kept, dropped = [], []
        for step in steps:
            try:
                for precondition in needed:
                    self._precondition(precondition, actor, actor, duty, step, request_type)
                kept.append(step)
            except Refused as exc:
                dropped.append({"step": step, "reason": exc.reason, "detail": exc.detail})
        if dropped and (not kept or not self.value(rt.partial_at_submit_param)):
            raise Refused(dropped[0]["reason"], "; ".join(d["detail"] for d in dropped))
        return kept, dropped

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
            raise Refused("already covered" if name == "not_already_covered" else f"precondition: {name}",
                          self._explain(name, step))

    def _explain(self, precondition: str, step: int) -> str:
        """The fixed preconditions in plain words, with the template's own labels."""
        occurrence = f"{self.step_label} {step}"
        request = self.t.terms.get("request", "request")
        return {
            "own_occurrence": f"you can do this only for your own {self.step_label}s",
            "occurrence_recorded": f"{occurrence} had not been recorded yet when you sent this",
            "occurrence_not_yet": f"{occurrence} had already been recorded or cancelled when you sent this",
            "not_already_covered": f"{occurrence} is already covered by one of your {request}s",
        }[precondition]

    def _covered(self, person: str, step: int, request_type: str | None) -> bool:
        return any(r.person == person and step in (r.steps if r.status == "pending" else r.approved_steps)
                   and (request_type is None or r.request_type == request_type)
                   for r in self.requests.values())

    def _apply(self, effect, actor, target, action, period, steps, params, caused_by, dropped) -> Event | None:
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
            return self._file_request(actor, effect.request_type, action, period, steps, params, caused_by, dropped)
        if kind == "endorse":
            return self._endorse(actor, action, period, params, caused_by)
        if kind == "decide_request":
            request_id = self._param_of_type(action, params, "request")
            outcome = self._param_of_type(action, params, "outcome")
            listed = self._param_of_type(action, params, "step_list")
            reason = next((v for p in action.params if p.type == "str" and (v := params.get(p.name))), "")
            slot = self.open_slots[effect.request_type]
            event = self.decide_request(request_id, outcome, actor, period, "llm",
                                        [*caused_by, slot["event"]],
                                        sorted(listed) if outcome == "approved" and listed else None,
                                        reason=reason[:300])
            slot["decided"].append(request_id)
            return event
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

    def _file_request(self, actor, request_type, action, period, steps, params, caused_by, dropped) -> Event:
        rt = self.request_types[request_type]
        request_id = f"R{len(self.requests) + 1}"
        covered = [self.record_event[(rt.covers, actor, s)] for s in steps if (rt.covers, actor, s) in self.record_event]
        reason = next((v for p in action.params if p.type == "str" and (v := params.get(p.name))), "")
        event = self.emit("request_filed", actor, period, self.current_step,
                          payload={"request_id": request_id, "request_type": request_type, "person": actor,
                                   "steps": sorted(steps), "dropped": dropped, "reason": reason[:300],
                                   "awaiting_endorsement_by": rt.endorsed_by},
                          state_change={f"request.{request_id}": {"from": None, "to": "pending"}},
                          caused_by=[*caused_by, *covered])
        self.requests[request_id] = Request(
            request_id=request_id, request_type=request_type, person=actor, steps=sorted(steps),
            reason=reason[:300], filed_period=period, filed_event=event.event_id, dropped=dropped,
            recorded_at_filing=[s for s in steps if s in self.recorded_steps[rt.covers]],
            endorsement="awaiting" if rt.endorsed_by else None)
        return event

    def _endorse(self, actor, action, period, params, caused_by) -> Event:
        """Consent given: the request joins its queue. Refused: the request ends, rejected."""
        request = self.requests[self._param_of_type(action, params, "request")]
        given = self._param_of_type(action, params, "bool")
        reason = next((v for p in action.params if p.type == "str" and (v := params.get(p.name))), "")
        payload = {"action": action.id, "request_id": request.request_id, "person": request.person,
                   "consent": given, "reason": reason[:300]}
        key = f"request.{request.request_id}"
        causes = [*caused_by, request.filed_event]
        if given:
            request.endorsement = "given"
            return self.emit("request_endorsed", actor, period, self.current_step, payload=payload,
                             state_change={f"{key}.endorsement": {"from": "awaiting", "to": "given"}},
                             caused_by=causes)
        request.endorsement, request.status, request.decided_period = "refused", "rejected", period
        request.rejected_steps = list(request.steps)
        return self.emit("request_endorsement_refused", actor, period, self.current_step, payload=payload,
                         state_change={f"{key}.endorsement": {"from": "awaiting", "to": "refused"},
                                       key: {"from": "pending", "to": "rejected"}},
                         caused_by=causes)

    def _check_decision(self, action: Action, request_type: str, params: dict[str, Any], listed: list[int]) -> None:
        """An LLM decider may decide only requests offered at the slot open now (that is the
        capacity, first come first served), each once, with an allowed outcome, and approve only
        some steps of a request when the policy allows partial decisions."""
        word = self.t.terms.get("request", "request")
        slot = self.open_slots.get(request_type)
        request = self.requests[self._param_of_type(action, params, "request")]
        rt = self.request_types[request_type]
        when = self.t.calendar.period_label if rt.processed == "period_end" else self.step_label
        if request.request_type != request_type:
            raise Refused("bad parameters: request type", f"{request.request_id} is not a {rt.label}")
        if slot is None:
            raise Refused("precondition: decision_slot", f"{word}s are decided only when their queue is processed")
        if request.request_id in slot["decided"] or request.status != "pending":
            raise Refused("precondition: awaiting_decision", f"{word} {request.request_id} is already decided")
        if request.request_id not in slot["offered"]:
            raise Refused("capacity", f"only {slot['capacity']} {word}s can be decided this {when}, first come "
                                      f"first served; {request.request_id} is not among them")
        outcome = self._param_of_type(action, params, "outcome")
        if listed and outcome == "approved":
            if not set(listed) <= set(request.steps):
                raise Refused("bad parameters: steps",
                              f"{request.request_id} covers only {self.step_label}s {request.steps}")
            if set(listed) != set(request.steps) and not self.value(rt.partial_at_decide_param):
                raise Refused("precondition: partial_at_decide",
                              f"each {word} is approved or rejected whole under this policy")

    def decide_request(self, request_id: str, outcome: Literal["approved", "rejected"], actor: str,
                       period: int, rule: str, caused_by: list[str] | None = None,
                       approved_steps: list[int] | None = None, reason: str = "") -> Event:
        """Sets a pending request's outcome (all its steps, or `approved_steps` only). Called by the
        queue processor rule or, from slice L9b, an LLM decider; the caller enforces capacity and order."""
        request = self.requests[request_id]
        if request.status != "pending":
            raise ValueError(f"request {request_id} is already {request.status}")
        request.status, request.decided_period = outcome, period
        approved = sorted(request.steps if approved_steps is None else approved_steps) if outcome == "approved" else []
        request.approved_steps = approved
        request.rejected_steps = [s for s in request.steps if s not in approved]
        return self.emit("request_decided", actor, period, self.current_step,
                         payload={"request_id": request_id, "decision": outcome, "rule": rule,
                                  "approved_steps": request.approved_steps, "rejected_steps": request.rejected_steps,
                                  "waited_periods": period - request.filed_period,
                                  **({"reason": reason} if reason else {})},
                         state_change={f"request.{request_id}": {"from": "pending", "to": outcome}},
                         caused_by=[*(caused_by or []), request.filed_event])

    # --- the queue processor rule -------------------------------------------------------------

    def process_queue(self, request_type: str, period: int, step: int | None = None) -> Event:
        """First come, first served within this slot's capacity. Each processed request is decided
        by the policy's decision rule; the rest wait, recorded as `queue_over_capacity`."""
        rt = self.request_types[request_type]
        if rt.decided_by != "rule":
            raise ValueError(f"queue '{request_type}' is decided by an LLM person: use open_decisions")
        capacity, causes, processed, held = self._queue_slot(request_type, period, step)
        rule = self.value(rt.decision_rule_param)
        partial = self.value(rt.partial_at_decide_param)
        actor = self.person_with_role(rt.handled_by)
        decisions = []
        for request in processed:
            good = [s for s in request.steps if self._qualifies(rule, request, s)]
            if len(good) == len(request.steps):
                decided = self.decide_request(request.request_id, "approved", actor, period, rule, causes)
            elif good and partial:
                decided = self.decide_request(request.request_id, "approved", actor, period, rule, causes, good)
            else:
                decided = self.decide_request(request.request_id, "rejected", actor, period, rule, causes)
            decisions.append(decided.event_id)
        event = self.emit("queue_processed", actor, period, step,
                          payload={"request_type": request_type, "capacity": capacity,
                                   "processed": [r.request_id for r in processed],
                                   "pending": [r.request_id for r in held]},
                          caused_by=[*causes, *decisions])
        if held:
            self.emit("queue_over_capacity", actor, period, step,
                      payload={"request_type": request_type, "capacity": capacity,
                               "held": [r.request_id for r in held]},
                      caused_by=[event.event_id, *(r.filed_event for r in held)])
        return event

    def _queue_slot(self, request_type: str, period: int, step: int | None):
        """This slot's capacity (and the crunch that set it), and its queue split first come,
        first served into the requests it can take and those that wait."""
        slot = (request_type, period, step)
        if slot in self.processed_slots:
            raise ValueError(f"queue '{request_type}' was already processed in this slot {slot[1:]}")
        self.processed_slots.add(slot)
        capacity, causes = self.value(self.request_types[request_type].capacity_param), []
        if (request_type, period) in self.capacity_override:
            capacity, crunch = self.capacity_override[(request_type, period)]
            causes = [crunch]
        pending = [r for r in self.requests.values() if r.request_type == request_type and r.status == "pending"
                   and r.endorsement in (None, "given")]  # a request awaiting consent isn't queued yet
        return capacity, causes, pending[:capacity], pending[capacity:]

    def open_decisions(self, request_type: str, period: int, step: int | None = None) -> Event:
        """An LLM-decided queue's slot: offers the requests within capacity (first come, first
        served) to the handled_by person, who decides them while the slot is open."""
        rt = self.request_types[request_type]
        if rt.decided_by != "llm":
            raise ValueError(f"queue '{request_type}' is decided by rule: use process_queue")
        capacity, causes, offered, held = self._queue_slot(request_type, period, step)
        event = self.emit("decision_awaiting", self.person_with_role(rt.handled_by), period, step,
                          payload={"request_type": request_type, "capacity": capacity,
                                   "offered": [r.request_id for r in offered], "held": [r.request_id for r in held],
                                   "outcomes": list(REQUEST_OUTCOMES),
                                   "partial": bool(self.value(rt.partial_at_decide_param))},
                          caused_by=[*causes, *(r.filed_event for r in offered)])
        self.open_slots[request_type] = {"event": event.event_id, "capacity": capacity, "period": period,
                                         "step": step, "offered": [r.request_id for r in offered],
                                         "held": [r.request_id for r in held], "decided": []}
        return event

    def close_decisions(self, request_type: str, decisions: list[str] | None = None) -> Event:
        """Ends the slot. Offered requests nobody decided (no action, or a failed call) stay
        pending, recorded as `decision_not_made`; those beyond capacity as `queue_over_capacity`."""
        slot = self.open_slots.pop(request_type)
        rt = self.request_types[request_type]
        actor, period, step = self.person_with_role(rt.handled_by), slot["period"], slot["step"]
        decided = [e.event_id for e in self.events if e.type == "request_decided"
                   and e.payload["request_id"] in slot["decided"] and slot["event"] in e.caused_by]
        undecided = [r for r in slot["offered"] if r not in slot["decided"]]
        event = self.emit("queue_processed", actor, period, step,
                          payload={"request_type": request_type, "capacity": slot["capacity"],
                                   "processed": slot["decided"], "pending": [*undecided, *slot["held"]],
                                   "decided_by": "llm"},
                          caused_by=[slot["event"], *decided])
        if undecided:
            self.emit("decision_not_made", actor, period, step,
                      payload={"request_type": request_type, "held": undecided},
                      caused_by=[event.event_id, *(decisions or []),
                                 *(self.requests[r].filed_event for r in undecided)])
        if slot["held"]:
            self.emit("queue_over_capacity", actor, period, step,
                      payload={"request_type": request_type, "capacity": slot["capacity"], "held": slot["held"]},
                      caused_by=[event.event_id, *(self.requests[r].filed_event for r in slot["held"])])
        return event

    def _qualifies(self, rule: str, request: Request, step: int) -> bool:
        duty = self.request_types[request.request_type].covers
        if rule == "approve_if_covered_missed":
            return self.records.get((duty, request.person, step)) == "missed"
        if rule == "approve_if_filed_before_occurrence":
            return step not in request.recorded_at_filing
        if rule == "approve_all":
            return True
        raise ValueError(f"unknown decision rule '{rule}'")

    def pending_causes(self, request_ids: list[str]) -> list[str]:
        """For each pending request: its filing, and the latest queue event that held it."""
        causes = []
        for request_id in request_ids:
            causes.append(self.requests[request_id].filed_event)
            held = [e for e in self.events if e.type in ("queue_over_capacity", "decision_not_made")
                    and request_id in e.payload["held"]]
            if held:
                causes.append(held[-1].event_id)
        return causes

    # --- disruptions ----------------------------------------------------------------------------

    def start_period(self, period: int) -> list[Event]:
        """Capacity disruptions for this period: they change that period's queue processing."""
        events = []
        for d in self.disruptions:
            kind = self.disruption_kinds[d.kind]
            if kind.kind != "capacity" or d.period != period:
                continue
            base = self.value(self.request_types[kind.request_type].capacity_param)
            event = self.emit("capacity_changed", "environment", period,
                              payload={"disruption": d.kind, "description": d.description,
                                       "request_type": kind.request_type, "capacity": d.capacity},
                              state_change={f"capacity.{kind.request_type}.{period}": {"from": base, "to": d.capacity}})
            self.capacity_override[(kind.request_type, period)] = (d.capacity, event.event_id)
            events.append(event)
        return events

    def start_step(self, step: int) -> list[Event]:
        """Obstacles and cancellations listed for this step. Obstacles are applied when the step
        is recorded; the term loop uses the returned events to trigger the people hit."""
        period = self.period_of(step)
        position = (step - 1) % self.t.calendar.steps_per_period + 1
        events = []
        for d in self.disruptions:
            kind = self.disruption_kinds[d.kind]
            if d.period != period or position not in d.steps:
                continue
            if kind.kind == "obstacle":
                event = self.emit("obstacle", "environment", period, step,
                                  payload={"disruption": d.kind, "description": d.description, "duty": kind.duty,
                                           "delay": d.delay, "people": d.people})
                self.obstacles_by_step.setdefault(step, []).append(
                    Obstacle(event_id=event.event_id, duty=kind.duty, people=d.people, delay=d.delay))
                events.append(event)
            elif kind.kind == "cancellation" and step not in self.recorded_steps[kind.duty] | self.cancelled[kind.duty]:
                self.cancelled[kind.duty].add(step)
                events.append(self.emit(
                    "occurrence_cancelled", "environment", period, step,
                    payload={"disruption": d.kind, "description": d.description, "duty": kind.duty},
                    state_change={f"occurrence.{kind.duty}.{step}": {"from": "scheduled", "to": "cancelled"}}))
        return events

    # --- the checker rule -----------------------------------------------------------------------

    def run_checks(self, period: int) -> list[Event]:
        """Checks due this period, for everyone the count applies to. A single-threshold check runs
        once, in its period, and records passed or failed. A ladder runs every period and records
        each step a person newly reaches, in ladder order (a jump of several steps records each);
        its `passed` is false only at the last step. Each records both figures (as is, and if
        pending requests were approved), its count's missed records and the pending requests."""
        events = []
        for check in self.t.checks:
            duty = self.duties[self.counts[check.count].duty]
            if check.ladder is None:
                if self.value(check.at_param) != period:
                    continue
                threshold = self.value(check.threshold_param)
                for person in self.people_owing(duty):
                    now = self.count(check.count, person)
                    passed = passes(now.value, check.comparison, threshold)
                    events.append(self._check_event(check, duty, person, period, now, threshold, passed,
                                                    {}, {"from": None, "to": "passed" if passed else "failed"}))
                continue
            for person in self.people_owing(duty):
                now = self.count(check.count, person)
                steps = check.ladder
                reached = [i for i, step in enumerate(steps)
                           if not passes(now.value, check.comparison, self.value(step.threshold_param))]
                top = max(reached) + 1 if reached else 0
                before = self.ladder_reached.get((check.id, person), 0)
                for i in range(before, top):
                    step = steps[i]
                    extra = {"outcome": step.outcome, "ladder_step": i + 1, "ladder_steps": len(steps),
                             "notifies": step.notifies}
                    change = {"from": steps[i - 1].outcome if i else None, "to": step.outcome}
                    events.append(self._check_event(check, duty, person, period, now,
                                                    self.value(step.threshold_param), i < len(steps) - 1,
                                                    extra, change))
                self.ladder_reached[(check.id, person)] = max(before, top)
        return events

    def _check_event(self, check, duty, person, period, now, threshold, passed, extra, change) -> Event:
        if_approved = self.count(check.count, person, assume_pending_approved=True)
        # Missed records link here directly unless a request covers them: those link through the
        # request (pending) or don't count (approved), so each missed occurrence reaches the
        # check by one path.
        covered = {s for r in now.pending for s in self.requests[r].steps}
        covered |= {s for r in now.approved for s in self.requests[r].approved_steps}
        missed = [self.record_event[(duty.id, person, s)] for s in sorted(self.recorded_steps[duty.id])
                  if self.records.get((duty.id, person, s)) == "missed" and s not in covered]
        return self.emit(
            "check_evaluated", self.person_with_role(check.run_by), period,
            payload={"check": check.id, "person": person, "count": now.model_dump(),
                     "count_if_pending_approved": if_approved.model_dump(),
                     "comparison": check.comparison, "threshold": threshold,
                     "pending_requests": now.pending, "passed": passed, **extra},
            state_change={f"check.{check.id}.{person}": change},
            caused_by=[*missed, *self.pending_causes(now.pending)])

    # --- the recorder rule --------------------------------------------------------------------

    def record_step(self, step: int, obstacles: list[Obstacle] | None = None) -> list[Event]:
        """Records met or missed for everyone who owes each duty at this step, applying their plan
        and any obstacle (a delay above the person's obstacle attribute means missed): those that
        `start_step` applied for this step, plus any passed in."""
        period = self.period_of(step)
        obstacles = [*self.obstacles_by_step.get(step, []), *(obstacles or [])]
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
                    for o in obstacles:
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
        excused: set[int] = set()
        if "approved_request" in c.exclude:
            excused = {s for r in own if r.status == "approved" for s in r.approved_steps}
            if assume_pending_approved:
                excused |= {s for r in own if r.status == "pending" for s in r.steps}
        cancelled = self.cancelled[c.duty] if "cancelled" in c.exclude else set()
        due = sorted(s for s in self.recorded_steps[c.duty] | cancelled
                     if s not in cancelled and s not in excused and (c.duty, person, s) in self.records)
        met = sum(1 for s in due if self.records[(c.duty, person, s)] == "met")
        missed = len(due) - met
        value = count_value(c.kind, met, missed)
        return CountResult(count=count_id, person=person, kind=c.kind, met=met, due=len(due), missed=missed,
                           value=value, pending=[r.request_id for r in own if r.status == "pending"],
                           approved=[r.request_id for r in own if r.status == "approved"],
                           rejected=[r.request_id for r in own if r.status == "rejected"])

    def calculate(self, count_id: str, person: str, period: int, assume_pending_approved: bool = False) -> Event:
        result = self.count(count_id, person, assume_pending_approved)
        return self.emit("count_calculated", "engine", period,
                         payload={"assume_pending_approved": assume_pending_approved, **result.model_dump()},
                         caused_by=[self.requests[r].filed_event for r in self.count(count_id, person).pending])
