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

import re
from typing import Any, Literal

from pydantic import BaseModel, Field

from rulestorm.core.model import REQUEST_OUTCOMES, Action, Count, Duty, Template

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
    """An obstacle or conflict disruption that hits one step: its event, who it hits, and the delay
    (a conflict has none: the person decides whether to miss the duty for it)."""

    event_id: str
    duty: str
    people: list[str]
    delay: int
    kind: str = ""
    conflict: bool = False


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
    reading: str = "remove"  # slice M1: how excused occurrences were counted (remove | count_as_met)

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


class Tally(BaseModel):
    met: int
    due: int
    missed: int
    value: float | None


def count_records(kind: str, records: dict[int, str], cancelled: set[int], excused: set[int],
                  reading: str = "remove") -> Tally:
    """The one way a check's figure is counted (slice M1), used by the engine, the evidence's
    recomputation and the search's closeness. `records` maps each recorded step to met or missed;
    `cancelled` steps leave the count; `excused` steps (covered by an approved request, or assumed
    approved) leave it under `remove` and count as met under `count_as_met`. Callers pass empty
    sets for whatever their count doesn't exclude."""
    if reading not in ("remove", "count_as_met"):
        raise ValueError(f"unknown excused reading {reading!r}")
    met = missed = 0
    for step, outcome in records.items():
        if step in cancelled or outcome not in ("met", "missed"):
            continue
        if step in excused:
            if reading == "remove":
                continue
            outcome = "met"
        if outcome == "met":
            met += 1
        else:
            missed += 1
    return Tally(met=met, due=met + missed, missed=missed, value=count_value(kind, met, missed))


def excused_reading(template: Template, count: Count, values: dict[str, Any]) -> str:
    """The count's excused reading from the blueprint's values, else its parameter's default."""
    if count.excused_param is None:
        return "remove"
    if count.excused_param in values:
        return values[count.excused_param]
    p = next((p for p in template.parameters if p.name == count.excused_param), None)
    return (p.default if p is not None and p.default is not None else "remove")


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
        # What actually happened at each recorded step (the recorder's mark); a correction must match it.
        self.truth: dict[tuple[str, str, int], Outcome] = {}
        # A missed record's cause: the disruption event behind it (None: the person's own choice),
        # and whether that cause excuses it (a non-routine disruption).
        self.record_cause: dict[tuple[str, str, int], tuple[str | None, bool]] = {}
        # Attribute changes made during a step apply from the next step: a person can't beat the
        # delay they have just been told about by "having left earlier".
        self.pending_attributes: dict[tuple[str, str], int] = {}
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
            if kind.kind == "conflict" and (not d.steps or not d.people):
                raise ValueError(f"conflict '{d.kind}' needs steps and people")
            if kind.kind in ("obstacle", "conflict"):
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
        params = self._normalise_steps(action, params)
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

    def _normalise_steps(self, action: Action, params: dict[str, Any]) -> dict[str, Any]:
        """A step written as text ("<period> 5 <step> 9", "9") becomes its number: the
        number after the step's own label, else a lone number. Anything else is left to be refused."""
        label = re.escape(self.step_label)

        def number(v: Any) -> Any:
            if not isinstance(v, str):
                return v
            found = re.findall(rf"{label}\s*#?\s*(\d+)", v, re.IGNORECASE)
            if found:
                return int(found[-1])
            return int(v.strip()) if v.strip().isdigit() else v

        out = dict(params)
        for spec in action.params:
            if spec.name in out and spec.type == "step":
                out[spec.name] = number(out[spec.name])
            elif spec.name in out and spec.type == "step_list" and isinstance(out[spec.name], list):
                out[spec.name] = [number(v) for v in out[spec.name]]
        return out

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
            if spec.type in ("str", "person", "cause") and not isinstance(value, str):
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
            if effect.kind == "plan_miss" and steps:
                self._check_claim(actor, action, params, steps[0])
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
            if effect.kind == "correct_record":
                key = (effect.duty, target, steps[0])
                after = "met" if self._param_of_type(action, params, "bool") else "missed"
                word = self.t.terms.get("duty_met" if after == "met" else "duty_missed", after)
                if self.records.get(key) == after:
                    raise Refused("precondition: record_differs",
                                  f"{self.step_label} {steps[0]} is already recorded {word}")
                if self.truth.get(key) != after:
                    raise Refused("precondition: matches_what_happened",
                                  f"{self.step_label} {steps[0]} was not {word}: a correction must match what happened")

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
            claim = self._param_of_type(action, params, "cause") if plan == "miss" else None
            event = self.emit("duty_planned", actor, period, step,
                              payload={"action": action.id, "duty": effect.duty, "plan": plan,
                                       **({"cause": self.claimed_cause(actor, step, claim)} if plan == "miss" else {})},
                              state_change={f"plan.{effect.duty}.{actor}.{step}": {"from": None, "to": plan}},
                              caused_by=caused_by)
            self.plans[(effect.duty, actor, step)] = (plan, event.event_id)
            return event
        if kind == "set_attribute":
            new = params.get(effect.attribute)
            if new is None:
                return None
            key = (actor, effect.attribute)
            later = self.current_step is not None
            event = self.emit("attribute_set", actor, period, self.current_step,
                              payload={"action": action.id, "attribute": effect.attribute,
                                       **({"from_step": self.current_step + 1} if later else {})},
                              state_change={f"{effect.attribute}.{actor}": {"from": self.attributes.get(key), "to": new}},
                              caused_by=caused_by)
            if later:
                self.pending_attributes[key] = new
            else:
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
        if self.request_types[request_type].decided_by == "rule":
            # A rule decides on the records, so a request waits until every step it covers has happened.
            duty = self.request_types[request_type].covers
            pending = [r for r in pending if all(s in self.recorded_steps[duty] or s in self.cancelled[duty]
                                                 for s in r.steps)]
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
        key = (duty, request.person, step)
        # A valid exception: a recorded miss that a non-routine disruption caused. Skipping when
        # nothing stopped you, or for something you could plan around, is not excused.
        valid = self.records.get(key) == "missed" and self.record_cause.get(key, (None, False))[1]
        if rule == "approve_if_covered_missed":
            return valid
        if rule == "approve_if_filed_before_occurrence":
            return step not in request.recorded_at_filing and valid
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
            if kind.kind in ("obstacle", "conflict"):
                conflict = kind.kind == "conflict"
                event = self.emit("obstacle", "environment", period, step,
                                  payload={"disruption": d.kind, "description": d.description, "duty": kind.duty,
                                           "delay": 0 if conflict else d.delay, "people": d.people,
                                           "conflict": conflict, "routine": bool(kind.routine)})
                self.obstacles_by_step.setdefault(step, []).append(
                    Obstacle(event_id=event.event_id, duty=kind.duty, people=d.people,
                             delay=0 if conflict else d.delay, kind=d.kind, conflict=conflict))
                events.append(event)
            elif kind.kind == "cancellation" and step not in self.recorded_steps[kind.duty] | self.cancelled[kind.duty]:
                self.cancelled[kind.duty].add(step)
                events.append(self.emit(
                    "occurrence_cancelled", "environment", period, step,
                    payload={"disruption": d.kind, "description": d.description, "duty": kind.duty},
                    state_change={f"occurrence.{kind.duty}.{step}": {"from": "scheduled", "to": "cancelled"}}))
        return events

    # --- what affects a person now, and the causes they may claim (slice M4) -----------------------

    def hitting(self, person: str, step: int) -> list[Obstacle]:
        """The obstacles and conflicts that hit this person at this step."""
        return [o for o in self.obstacles_by_step.get(step, []) if person in o.people]

    def valid_causes(self, person: str, step: int) -> list[str]:
        """What a person may give as the cause of missing this step: "none" (their own choice), or
        the event ID or kind of a disruption hitting them now. Nothing else; no free-text matching."""
        out = ["none"]
        for o in self.hitting(person, step):
            out += [o.event_id, o.kind]
        return list(dict.fromkeys(out))

    def situation(self, person: str, step: int) -> list[str]:
        """What affects the person at this step, in plain words, or that nothing does."""
        lines = []
        step_word = self.step_label
        for o in self.hitting(person, step):
            kind = self.disruption_kinds.get(o.kind)
            label = kind.label if kind else o.kind
            what = self.event(o.event_id).payload.get("description") or label
            routine = "routine, could be planned around" if kind is not None and kind.routine else "outside your control"
            if o.conflict:
                lines.append(f"{label} ({o.event_id}, kind {o.kind}): {what}; {routine}. You miss the {step_word} "
                             f"only if you choose to")
                continue
            duty = self.duties[o.duty]
            slack = self.attributes.get((person, duty.obstacle_attribute)) if duty.obstacle_attribute else None
            if slack is None:
                effect = "it keeps you from it"
            elif o.delay > slack:
                effect = f"a delay of {o.delay} is over your {slack}, so it keeps you from it"
            else:
                effect = f"a delay of {o.delay} is within your {slack}, so it doesn't stop you"
            lines.append(f"{label} ({o.event_id}, kind {o.kind}): {what}; {routine}; {effect}")
        for duty in self.t.duties:
            if step in self.cancelled[duty.id] and self.owes(person, duty):
                lines.append(f"this {step_word} is cancelled")
        return lines or [f"nothing outside your control affects you this {step_word}"]

    def situation_text(self, person: str, step: int) -> str:
        return "; ".join(self.situation(person, step))

    def claimed_cause(self, person: str, step: int, claim: str | None) -> str:
        """A checked claim as recorded on the plan: the disruption's event ID, or "none"."""
        if claim in (None, "none"):
            return "none"
        return next((o.event_id for o in self.hitting(person, step) if claim in (o.event_id, o.kind)), "none")

    def _check_claim(self, actor: str, action: Action, params: dict[str, Any], step: int) -> None:
        claim = self._param_of_type(action, params, "cause")
        if claim is None:
            return
        valid = self.valid_causes(actor, step)
        if claim in valid:
            return
        listed = ", ".join(valid)
        known = claim in self.disruption_kinds or any(claim == o.event_id for os_ in self.obstacles_by_step.values()
                                                      for o in os_)
        if known:
            raise Refused("claim: not_affecting_you",
                          f"{claim} is not affecting you in {self.step_label} {step}: "
                          f"{self.situation_text(actor, step)}. Valid causes now: {listed}")
        raise Refused("bad parameters: cause",
                      f"cause must be one of: {listed} (not {claim!r}); {self.situation_text(actor, step)}")

    # --- the checker rule -----------------------------------------------------------------------

    def run_checks(self, period: int) -> list[Event]:
        """Checks due this period, for everyone the count applies to. A single-threshold check runs
        once, in its period, and records passed or failed. A ladder runs every period and records
        each step a person newly reaches, in ladder order (a jump of several steps records each);
        its `passed` is false only at the last step. A ladder period with no new step records the
        person's standing only if a request for an occurrence already recorded is still pending.
        Each records both figures (as is, and if
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
                if top <= before and self._overdue(now.pending, duty):
                    # No new step, but a request for an occurrence already recorded is still
                    # waiting: record where they stand, so the wait is visible at the check. It has
                    # no `outcome`, so it notifies nobody.
                    standing = steps[before - 1].outcome if before else None
                    extra = {"standing": standing, "ladder_step": before, "ladder_steps": len(steps)}
                    threshold = self.value(steps[min(before, len(steps) - 1)].threshold_param)
                    events.append(self._check_event(check, duty, person, period, now, threshold,
                                                    before < len(steps), extra, None))
        return events

    def _overdue(self, request_ids: list[str], duty) -> bool:
        """Is any of these pending requests for an occurrence already recorded?"""
        return any(s in self.recorded_steps[duty.id] for r in request_ids for s in self.requests[r].steps)

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
            state_change={f"check.{check.id}.{person}": change} if change else {},
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
                hit_by = None  # an obstacle that made a person who meant to come miss it
                # Whatever kept them away: that obstacle, one they would have missed for anyway
                # (a delay over their slack), or a conflict they chose to miss the duty for.
                stopping = None
                for o in obstacles:
                    if o.duty != duty.id or person not in o.people:
                        continue
                    if o.conflict:
                        stopping = stopping or o
                        continue
                    if not duty.obstacle_attribute:
                        continue  # a duty with no slack attribute isn't delayed by obstacles
                    slack = self.attributes.get((person, duty.obstacle_attribute))
                    if slack is None:
                        raise KeyError(f"missing value '{duty.obstacle_attribute}' for {person}")
                    if o.delay > slack:
                        stopping = o
                        if outcome == "met":
                            outcome, hit_by = "missed", o
                        break
                key = (duty.id, person, step)
                self.records[key] = self.truth[key] = outcome
                cause, excusable = None, False
                if outcome == "missed" and stopping is not None:
                    cause = stopping.event_id
                    kind = self.disruption_kinds.get(stopping.kind)
                    excusable = not (kind is not None and kind.routine)
                    if cause not in causes:
                        causes = [cause, *causes]
                if outcome == "missed":
                    self.record_cause[key] = (cause, excusable)
                event = self.emit("duty_recorded", recorder, period, step,
                                  payload={"duty": duty.id, "person": person, "outcome": outcome,
                                           "plan": plan, "obstacle": hit_by.event_id if hit_by else None,
                                           **({"cause": cause, "excusable": excusable} if outcome == "missed" else {})},
                                  state_change={f"record.{duty.id}.{person}.{step}": {"from": None, "to": outcome}},
                                  caused_by=causes)
                self.record_event[key] = event.event_id
                recorded.append(event)
        for key, value in self.pending_attributes.items():
            self.attributes[key] = value
        self.pending_attributes.clear()
        return recorded

    def has_wrong_record(self, duty_id: str) -> bool:
        """Is any recorded mark of this duty different from what happened? Only then can a
        correction be accepted, so only then is a correcting action worth offering."""
        return any(self.records[k] != v for k, v in self.truth.items() if k[0] == duty_id)

    def cause_text(self, duty_id: str, person: str, step: int) -> str:
        """What a decider would know about one covered step: not yet happened, met, or missed and why."""
        key = (duty_id, person, step)
        met, missed = self.t.terms.get("duty_met", "met"), self.t.terms.get("duty_missed", "missed")
        if step in self.cancelled[duty_id]:
            return "cancelled"
        if key not in self.records:
            return "not yet happened"
        if self.records[key] == "met":
            return f"recorded {met}"
        cause, _ = self.record_cause.get(key, (None, False))
        if cause is None:
            return f"recorded {missed}; no disruption stopped them (their own choice)"
        e = self.event(cause)
        kind = self.disruption_kinds.get(e.payload.get("disruption", ""))
        routine = kind is not None and kind.routine
        what = e.payload.get("description") or (kind.label if kind else "a disruption")
        return (f"recorded {missed}; caused by {what} ({cause}, "
                f"{'routine, could be planned around' if routine else 'outside their control'})")

    # --- counts -----------------------------------------------------------------------------

    def count(self, count_id: str, person: str, assume_pending_approved: bool = False,
              reading: str | None = None) -> CountResult:
        """Always recomputed from the records. Pending requests count as missed unless assumed approved.
        Excused occurrences are read as the policy's reading says, unless `reading` overrides it."""
        c = self.counts[count_id]
        own = [r for r in self.requests.values() if r.person == person
               and self.request_types[r.request_type].covers == c.duty]
        excused: set[int] = set()
        if "approved_request" in c.exclude:
            excused = {s for r in own if r.status == "approved" for s in r.approved_steps}
            if assume_pending_approved:
                excused |= {s for r in own if r.status == "pending" for s in r.steps}
        cancelled = self.cancelled[c.duty] if "cancelled" in c.exclude else set()
        records = {s: self.records[(c.duty, person, s)] for s in self.recorded_steps[c.duty]
                   if (c.duty, person, s) in self.records}
        reading = reading or self.excused_reading(c)
        tally = count_records(c.kind, records, cancelled, excused, reading)
        return CountResult(count=count_id, person=person, kind=c.kind, met=tally.met, due=tally.due,
                           missed=tally.missed, value=tally.value,
                           pending=[r.request_id for r in own if r.status == "pending"],
                           approved=[r.request_id for r in own if r.status == "approved"],
                           rejected=[r.request_id for r in own if r.status == "rejected"], reading=reading)

    def excused_reading(self, count: Count) -> str:
        return excused_reading(self.t, count, self.values)

    def calculate(self, count_id: str, person: str, period: int, assume_pending_approved: bool = False,
                  reading: str | None = None) -> Event:
        result = self.count(count_id, person, assume_pending_approved, reading)
        return self.emit("count_calculated", "engine", period,
                         payload={"assume_pending_approved": assume_pending_approved, **result.model_dump()},
                         caused_by=[self.requests[r].filed_event for r in self.count(count_id, person).pending])
