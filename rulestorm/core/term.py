"""The term loop over a template's calendar, in the fixed phase order.

    period start: capacity disruptions, then pending-request triggers
    each step:    obstacles and cancellations -> triggered people decide -> consent for requests
                  filed now -> requests processed `each_step` -> the recorder rule records the duty
    period end:   requests processed `period_end` -> checks (if due; a ladder every period)

A queue decided by an LLM person is processed in its own short phase at its slot: the engine
offers the requests within capacity, only that queue's handled_by people are asked, and the
slot closes before the term moves on (anything they didn't decide stays pending).

Only LLM people decide, and only when one of the template's triggers names them. Every
decision records `caused_by=[its triggers]`, and every action it produces records
`caused_by=[decision]`. All contexts of one phase share the same snapshot and are sorted by
person ID, so results never depend on timing.
"""

from collections import defaultdict
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field

from rulestorm.core.engine import CountResult, Engine, Event
from rulestorm.core.margins import PersonState
from rulestorm.core.model import Template


class Proposal(BaseModel):
    action: str
    params: dict[str, Any] = Field(default_factory=dict)


REPLY_ROUNDS = 2  # per step: someone asks, someone answers
MAX_INTENDS = 2  # slice M5: actions a decision may say it plans at a later step


class Intention(BaseModel):
    """Slice M5: an action a person says they plan to take at a later step. Not a commitment."""

    action: str = Field(description="the action you plan to take then")
    step: int = Field(description="the later step you plan it for")


class DecisionContext(BaseModel):
    """What a triggered person sees."""

    person: str
    role: str
    period: int
    step: int
    triggers: list[Event]
    profile: dict[str, Any] | None = None  # from the blueprint's profiles parameter
    counts: dict[str, CountResult] = Field(default_factory=dict)  # people who owe a duty
    attributes: dict[str, int] = Field(default_factory=dict)
    pending_requests: list[str] = Field(default_factory=list)
    # Facts the person would know: what became of their last decision's actions, and their
    # missed occurrences that no request covers yet.
    last_outcomes: list[str] = Field(default_factory=list)
    uncovered_missed: list[int] = Field(default_factory=list)
    # An LLM decider at an open slot: the requests offered to them (within capacity, first come
    # first served), each {request_id, person, steps, reason, filed_period}, and how many.
    offered_requests: list[dict[str, Any]] = Field(default_factory=list)
    decision_capacity: int | None = None
    partial_decisions: bool = False
    # A consenting person: the requests waiting for their consent, in the same shape.
    awaiting_consent: list[dict[str, Any]] = Field(default_factory=list)
    # Every request the person filed, with what became of it: so they know which steps each one
    # covered (in a real run, people assumed a request for the last step also covered this one).
    own_requests: list[dict[str, Any]] = Field(default_factory=list)
    # 26 Nov: actions of the role that can't succeed now (a correction while every mark matches
    # what happened), left out of the prompt; and each queue's capacity this period where a
    # disruption changed it, so the people know the queue is short this period.
    unavailable_actions: list[str] = Field(default_factory=list)
    capacity_now: dict[str, int] = Field(default_factory=dict)
    # Slice M4: what affects the person this step (or that nothing does), from Engine.situation;
    # empty for people who owe no duty.
    situation: list[str] = Field(default_factory=list)
    # Slice M5: at a step the person named, what they said they would do then (one line each).
    reminders: list[str] = Field(default_factory=list)
    # Slice M7c: the person's own state (rulestorm/core/margins.py), for people who owe a duty.
    state: PersonState | None = None

    def action_limit(self) -> int:
        """Everyone may propose 3 actions; someone with more requests waiting for them (to consent
        to, or to decide) may propose one per request, so none is left out for lack of room."""
        return max(MIN_ACTIONS, len(self.offered_requests) + len(self.awaiting_consent))


class PhaseDecision(BaseModel):
    person: str
    proposals: list[Proposal] = Field(default_factory=list)
    reason: str = ""
    strategy: str = ""
    intends: list[Intention] = Field(default_factory=list)  # slice M5: up to MAX_INTENDS
    error: str | None = None  # set when the person's call failed: recorded as "no action"


# Given every triggered person's context for one phase, return their decisions.
Decider = Callable[[list[DecisionContext]], list[PhaseDecision]]

MIN_ACTIONS = 3  # what everyone may propose in one decision; a handler may need more (below)


class Term:
    def __init__(self, template: Template, values: dict[str, Any], decider: Decider) -> None:
        self.t = template
        self.decider = decider
        self.engine = Engine(template, values)
        profiles = next((p.name for p in template.parameters if p.type == "profiles"), None)
        self.profiles: dict[str, dict] = dict(values.get(profiles) or {}) if profiles else {}
        self.triggers: dict[str, list[str]] = defaultdict(list)
        self.near: set[tuple[str, str]] = set()  # (count, person) currently near the threshold
        self.last_decision: dict[str, str] = {}  # person -> event ID of their latest decision
        self.messaged: set[tuple[str, int]] = set()  # (person, step) a message has triggered
        # What each person was shown earlier in the current step: a reply round shows it again, so
        # a person answering a message still sees the disruption that hit this step (26 Nov).
        self.seen_this_step: dict[str, list[str]] = defaultdict(list)
        self.of_kind = {tr.kind: tr for tr in template.triggers}
        self.reasked: set[tuple[str, int]] = set()  # (person, step) asked again after a refused claim
        # Slice M5: step -> person -> what they said they would do then ({action, stated_at, decision});
        # the intention_due event of each (person, step) once it fires; the actions each person
        # carried out (accepted) in each step; and the trigger events a decision has answered.
        self.intended: dict[int, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
        self.due: dict[tuple[str, int], tuple[Event, list[dict[str, Any]]]] = {}
        self.carried_out: dict[tuple[str, int], set[str]] = defaultdict(set)
        self.answered: set[str] = set()

    # --- triggers -----------------------------------------------------------------------------

    def trigger(self, person: str, event: Event) -> None:
        """Only LLM people decide; rule roles run at their phase and are never asked."""
        if self.engine.roles[self.engine.role_of[person]].llm and event.event_id not in self.triggers[person]:
            self.triggers[person].append(event.event_id)

    def notify(self, kind: str, event: Event, person: str | None = None) -> None:
        trigger = self.of_kind.get(kind)
        if trigger is None:
            return
        if person:
            self.trigger(person, event)
        for role in trigger.notifies:
            for other in sorted(p for p, r in self.engine.role_of.items() if r == role):
                self.trigger(other, event)

    # --- the calendar -------------------------------------------------------------------------

    def run(self, on_period: Callable[[int], None] | None = None) -> Engine:
        for period in range(1, self.t.calendar.periods + 1):
            self.run_period(period)
            if on_period:
                on_period(period)
        self.engine.current_step = None
        return self.engine

    def run_period(self, period: int) -> None:
        e = self.engine
        e.start_period(period)
        pending_after = self.of_kind.get("request_pending")
        if pending_after is not None:
            for request in list(e.requests.values()):
                waited = period - request.filed_period
                if request.status == "pending" and waited >= (pending_after.periods or 1):
                    event = e.emit("request_pending", "engine", period,
                                   payload={"request_id": request.request_id, "person": request.person,
                                            "periods_pending": waited},
                                   caused_by=e.pending_causes([request.request_id]))
                    self.notify("request_pending", event, request.person)

        spp = self.t.calendar.steps_per_period
        for step in range((period - 1) * spp + 1, period * spp + 1):
            self.run_step(period, step)
        e.current_step = None

        for rt in self.t.request_types:
            if rt.processed == "period_end":
                self.process(rt.id, period, None, last_step=step)
        for event in e.run_checks(period):
            if "outcome" in event.payload:
                self.escalated(event)
            elif "ladder_step" not in event.payload:
                # A single-threshold check's result reaches the person checked (26 Nov), so they
                # know it was final and how it went; before, only ladder outcomes did.
                self.trigger(event.payload["person"], event)

    def run_step(self, period: int, step: int) -> None:
        e = self.engine
        e.current_step = step
        self.seen_this_step.clear()
        for event in e.start_step(step):
            if event.type == "obstacle":
                for person in event.payload["people"]:
                    self.notify("obstacle_hit", event, person)
        self.intentions_due(period, step)
        self.decision_phase(period, step)
        # Reply rounds (26 Nov): a message or advice sent now reaches its reader in this same step,
        # before it is recorded, as a real conversation would (before, advice given in the step
        # before a check arrived after it). Two rounds: a question, then its answer.
        for _ in range(REPLY_ROUNDS):
            readers = {p for p, ids in self.triggers.items()
                       if any(e.event(i).type in ("message_sent", "response_given") for i in ids)}
            if not readers:
                break
            self.decision_phase(period, step, only=readers)
        # Requests filed just now reach their consenting people before this step's queues and its
        # recording, so a request filed in advance can be consented to and decided in time.
        endorsers = {p for p, r in e.role_of.items() if r in {rt.endorsed_by for rt in self.t.request_types}}
        if endorsers & set(self.triggers):
            self.decision_phase(period, step, only=endorsers)
        for rt in self.t.request_types:
            if rt.processed == "each_step":
                self.process(rt.id, period, step)
        self.resolve_intentions(period, step)
        recorded = e.record_step(step)

        missed_by_duty: dict[str, list[Event]] = defaultdict(list)
        for event in recorded:
            person = event.payload["person"]
            if event.payload["outcome"] == "missed":
                missed_by_duty[event.payload["duty"]].append(event)
                self.notify("own_duty_missed", event, person)
            self.check_near_threshold(period, person, event)
        many = self.of_kind.get("many_missed")
        for duty, missed in missed_by_duty.items():
            if many is not None and len(missed) >= (many.min_people or 1):
                event = e.emit("many_missed", "engine", period, step,
                               payload={"duty": duty, "people": [m.payload["person"] for m in missed]},
                               caused_by=[m.event_id for m in missed])
                self.notify("many_missed", event)

    # --- intentions (slice M5) ----------------------------------------------------------------

    def intentions_due(self, period: int, step: int) -> None:
        """At a step someone named, one `intention_due` event per person (however many things they
        planned for it), which asks them again: at most once per person per step."""
        for person, items in sorted(self.intended.pop(step, {}).items()):
            if "intention_due" not in self.of_kind:
                continue
            event = self.engine.emit(
                "intention_due", "engine", period, step,
                payload={"person": person,
                         "intentions": [{"action": i["action"], "stated_at": i["stated_at"]} for i in items]},
                caused_by=list(dict.fromkeys(i["decision"] for i in items)))
            self.due[(person, step)] = (event, items)
            self.notify("intention_due", event, person)

    def resolve_intentions(self, period: int, step: int) -> None:
        """Met if the person carried out the action they named in this step (an accepted action),
        unmet if they were asked and didn't. Someone never asked is not counted either way."""
        for (person, at), (event, items) in sorted(self.due.items()):
            if at != step:
                continue
            del self.due[(person, at)]
            if event.event_id not in self.answered:
                continue
            decisions = [d.event_id for d in self.engine.events
                         if d.type == "decision" and d.actor == person and d.step == step]
            for item in items:
                self.engine.emit("intention_resolved", "engine", period, step,
                                 payload={"person": person, "action": item["action"],
                                          "stated_at": item["stated_at"],
                                          "met": item["action"] in self.carried_out[(person, step)]},
                                 caused_by=[event.event_id, *decisions])

    def state_intentions(self, person: str, step: int, decision_id: str,
                         intends: list[Intention]) -> tuple[list[dict], list[dict]]:
        """(the intentions kept, the ones refused with why). Kept: an action of the person's role
        at a later step of the term, at most MAX_INTENDS, no repeats."""
        e = self.engine
        kept, refused = [], []
        for i in intends:
            problem = None
            if i.action not in e.roles[e.role_of[person]].actions:
                problem = "not an action you may take"
            elif not step < i.step <= e.total_steps:
                problem = f"the {self.t.calendar.step_label} must be later than now and within the term"
            elif len(kept) >= MAX_INTENDS:
                problem = f"at most {MAX_INTENDS}"
            elif any(k["action"] == i.action and k["step"] == i.step for k in kept):
                problem = "a repeat"
            if problem:
                refused.append({**i.model_dump(), "problem": problem})
                continue
            kept.append(i.model_dump())
            self.intended[i.step][person].append({"action": i.action, "stated_at": step, "decision": decision_id})
        return kept, refused

    def process(self, request_type: str, period: int, step: int | None, last_step: int | None = None) -> None:
        """A rule decides at once; an LLM person decides in a phase of their own at the slot."""
        e = self.engine
        rt = e.request_types[request_type]
        if rt.decided_by == "rule":
            e.process_queue(request_type, period, step)
            return
        opened = e.open_decisions(request_type, period, step)
        handlers = sorted(p for p, r in e.role_of.items() if r == rt.handled_by)
        decisions: list[str] = []
        if opened.payload["offered"]:
            for person in handlers:
                self.notify("decision_awaiting", opened, person)
            decisions = self.decision_phase(period, step or last_step, only=set(handlers))
        e.close_decisions(request_type, decisions)

    def escalated(self, event: Event) -> None:
        """A ladder outcome reaches the person and the roles its step lists (and the trigger's)."""
        if "escalation_outcome" not in self.of_kind:
            return
        self.notify("escalation_outcome", event, event.payload["person"])
        for role in event.payload["notifies"]:
            for other in sorted(p for p, r in self.engine.role_of.items() if r == role):
                self.trigger(other, event)

    def awaiting_consent(self, event: Event) -> None:
        """A filed request that needs consent reaches every person of its endorsed_by role."""
        role = event.payload.get("awaiting_endorsement_by")
        if event.type != "request_filed" or role is None:
            return
        for person in sorted(p for p, r in self.engine.role_of.items() if r == role):
            self.notify("endorsement_awaiting", event, person)

    def check_near_threshold(self, period: int, person: str, latest: Event) -> None:
        """Fires once each time a person's count comes within `within` of a check's threshold."""
        near_by = self.of_kind.get("count_near_threshold")
        if near_by is None:
            return
        e = self.engine
        for check in self.t.checks:
            if check.threshold_param is None or self.engine.counts[check.count].duty != latest.payload["duty"]:
                continue
            threshold = e.value(check.threshold_param)
            value = e.count(check.count, person).value
            near = value is not None and abs(value - threshold) <= (near_by.within or 0)
            key = (check.count, person)
            if near and key not in self.near:
                event = e.emit("count_near_threshold", "engine", period, latest.step,
                               payload={"count": check.count, "person": person, "value": value,
                                        "threshold": threshold},
                               caused_by=[latest.event_id])
                self.notify("count_near_threshold", event, person)
            if near:
                self.near.add(key)
            else:
                self.near.discard(key)

    # --- decisions ----------------------------------------------------------------------------

    def decision_phase(self, period: int, step: int, only: set[str] | None = None) -> list[str]:
        """Everyone triggered decides (or, at an LLM decision slot, `only` its deciders; the
        others keep their triggers for the next phase). Returns the decision event IDs."""
        e = self.engine
        people = sorted(p for p in self.triggers if only is None or p in only)
        if not people:
            return []
        contexts = [self.context(person, period, step) for person in people]
        for person in people:
            self.seen_this_step[person] += [t for t in self.triggers[person] if t not in self.seen_this_step[person]]
            del self.triggers[person]
        decided = []
        refused_claims: dict[str, Event] = {}

        by_person = {d.person: d for d in self.decider(contexts)}
        for context in contexts:
            decision = by_person.get(context.person, PhaseDecision(person=context.person, error="no decision returned"))
            payload = {"proposals": [p.model_dump() for p in decision.proposals],
                       "reason": decision.reason, "strategy": decision.strategy,
                       "no_action": not decision.proposals, "error": decision.error}
            if context.state is not None:  # slice M7c: what the person decided from
                payload["state"] = context.state.model_dump()
            recorded = e.emit("decision", context.person, period, step, payload=payload,
                              caused_by=[t.event_id for t in context.triggers])
            if decision.intends:  # slice M5: only when stated, so older event logs stay as they were
                kept, refused = self.state_intentions(context.person, step, recorded.event_id, decision.intends)
                recorded.payload["intends"] = kept
                if refused:
                    recorded.payload["intends_refused"] = refused
            self.answered.update(t.event_id for t in context.triggers)
            decided.append(recorded.event_id)
            self.last_decision[context.person] = recorded.event_id
            for proposal in decision.proposals:
                done = e.propose(context.person, proposal.action, period, caused_by=[recorded.event_id],
                                 **proposal.params)
                if done.type != "action_rejected":
                    self.carried_out[(context.person, step)].add(proposal.action)
                self.message_received(done, period)
                self.awaiting_consent(done)
                if done.type == "action_rejected" and _refused_claim(done) and (context.person, step) not in self.reasked:
                    refused_claims.setdefault(context.person, done)
        # Slice M4: a refused claim of cause gets the person asked once more in the same step,
        # shown why, so a refused skip never silently turns into meeting the duty.
        if refused_claims:
            for person, event in refused_claims.items():
                self.reasked.add((person, step))
                self.trigger(person, event)
            decided += self.decision_phase(period, step, only=set(refused_claims))
        return decided

    def message_received(self, event: Event, period: int) -> None:
        """A message to a role, or a response to a person, triggers who it is for: in a reply
        round of the same step (run_step), at most once per person per step."""
        if "message_received" not in self.of_kind or event.type not in ("message_sent", "response_given"):
            return
        to = event.payload.get("to")
        if event.type == "message_sent":
            recipients = sorted(p for p, r in self.engine.role_of.items() if r == to)
        else:
            recipients = [to] if to in self.engine.role_of else []
        for person in recipients:
            key = (person, self.engine.current_step if self.engine.current_step is not None else -period)
            if person != event.actor and key not in self.messaged:
                self.messaged.add(key)
                self.notify("message_received", event, person)

    def context(self, person: str, period: int, step: int) -> DecisionContext:
        e = self.engine
        role = e.role_of[person]
        counts = {c.id: e.count(c.id, person) for c in self.t.counts if e.owes(person, e.duties[c.duty])}
        own = [r.request_id for r in e.requests.values() if r.person == person and r.status == "pending"]
        handles = {rt.id for rt in self.t.request_types if rt.handled_by == role}
        offered, capacity, partial = [], None, False
        for rt_id in sorted(handles & set(e.open_slots)):
            slot, rt = e.open_slots[rt_id], e.request_types[rt_id]
            capacity, partial = slot["capacity"], bool(e.value(rt.partial_at_decide_param))
            offered += [_request_view(e.requests[i]) for i in slot["offered"] if i not in slot["decided"]]
        consents = {rt.id for rt in self.t.request_types if rt.endorsed_by == role}
        awaiting = [_request_view(r) for r in e.requests.values()
                    if r.request_type in consents and r.status == "pending" and r.endorsement == "awaiting"]
        for view in [*offered, *awaiting]:
            covers = e.request_types[e.requests[view["request_id"]].request_type].covers
            view["facts"] = {s: e.cause_text(covers, view["person"], s) for s in view["steps"]}
        unavailable = sorted(a for a in self.t.roles[[r.id for r in self.t.roles].index(role)].actions
                             if any(f.kind == "correct_record" and not e.has_wrong_record(f.duty)
                                    for f in e.actions[a].effects))
        capacity_now = {rt: cap for (rt, p), (cap, _) in e.capacity_override.items() if p == period}
        return DecisionContext(
            person=person, role=role, period=period, step=step,
            triggers=[e.event(t) for t in [*(i for i in self.seen_this_step.get(person, [])
                                              if i not in self.triggers[person]), *self.triggers[person]]],
            profile=self.profiles.get(person),
            counts=counts,
            attributes={attr: v for (who, attr), v in e.attributes.items() if who == person},
            pending_requests=own if counts else [r.request_id for r in e.requests.values()
                                                 if r.status == "pending" and (r.request_type in handles or not handles)],
            last_outcomes=self.outcomes_of(person),
            uncovered_missed=self.uncovered_missed(person),
            offered_requests=offered, decision_capacity=capacity, partial_decisions=partial,
            awaiting_consent=awaiting,
            own_requests=[_own_view(r) for r in e.requests.values() if r.person == person],
            unavailable_actions=unavailable, capacity_now=capacity_now,
            situation=e.situation(person, step) if any(e.owes(person, d) for d in e.duties.values()) else [],
            reminders=self.reminders(person, step),
            state=e.person_state(person, step) if counts else None,
        )

    def reminders(self, person: str, step: int) -> list[str]:
        """Slice M5: at a step the person named, what they said they would do then."""
        due = self.due.get((person, step))
        if due is None:
            return []
        label = self.t.calendar.step_label
        return [f"{self.engine.actions[i['action']].label} ({i['action']}) at {label} {step}, "
                f"as you said at {label} {i['stated_at']}" for i in due[1]]

    def outcomes_of(self, person: str) -> list[str]:
        """What the engine did with each action of the person's latest decision."""
        decision_id = self.last_decision.get(person)
        if decision_id is None:
            return []
        word = self.t.terms.get("request", "request")
        outcomes = []
        for event in self.engine.events[int(decision_id.removeprefix("E-")):]:
            if decision_id not in event.caused_by:
                continue
            p = event.payload
            if event.type == "action_rejected":
                outcomes.append(f"refused: {p['action']} {p['params']} (reason: {p.get('detail') or p['reason']})")
            elif event.type == "request_filed":
                outcomes.append(f"done: {word} {p['request_id']} submitted for "
                                f"{self.t.calendar.step_label}s {p['steps']}, now pending")
            else:
                outcomes.append(f"done: {event.type} {p}")
        return outcomes

    def uncovered_missed(self, person: str) -> list[int]:
        e = self.engine
        missed = []
        for (duty, who, step), outcome in e.records.items():
            if who == person and outcome == "missed" and step not in e.cancelled[duty]:
                if not any(r.person == person and step in (r.steps if r.status == "pending" else r.approved_steps)
                           for r in e.requests.values()):
                    missed.append(step)
        return sorted(missed)


def _refused_claim(event: Event) -> bool:
    """A planned miss refused for its claimed cause: a false claim, or a cause not in the list."""
    reason = event.payload.get("reason", "")
    return reason.startswith("claim:") or reason == "bad parameters: cause"


def _own_view(r) -> dict[str, Any]:
    return {"request_id": r.request_id, "steps": r.steps, "status": r.status, "endorsement": r.endorsement,
            "approved_steps": r.approved_steps}


def _request_view(r) -> dict[str, Any]:
    return {"request_id": r.request_id, "person": r.person, "steps": r.steps, "reason": r.reason,
            "filed_period": r.filed_period}


def simulate(template: Template, values: dict[str, Any], decider: Decider,
             on_period: Callable[[int], None] | None = None) -> Engine:
    return Term(template, values, decider).run(on_period)


# --- the dry run (part of the template check) --------------------------------------------------


def dry_run_values(template: Template) -> dict[str, Any]:
    """Values made only from the parameter specs, for the dry run: never used in a real run."""
    llm_people = [p.id for p in template.people if next(r for r in template.roles if r.id == p.role).llm]
    values: dict[str, Any] = {}
    # Ladder thresholds as low as they can be and still in order (slice M8a), so the dry run
    # reaches (and exercises) every step.
    ladder = {s.threshold_param: (i, c.comparison in ("<", "<="))
              for c in template.checks for i, s in enumerate(c.ladder or [])}
    for p in template.parameters:
        if not p.in_fill and p.default is not None:  # a reading (slice M8a): its default
            values[p.name] = p.default
        elif p.type == "int" and p.name in ladder:
            i, rising = ladder[p.name]
            values[p.name] = min(p.min + i, p.max) if rising else max(p.max - i, p.min)
        elif p.type == "int":
            values[p.name] = (p.min + p.max) // 2
        elif p.type == "bool":
            values[p.name] = False
        elif p.type == "choice":
            values[p.name] = p.choices[0]
        elif p.type == "profiles":
            values[p.name] = {person: {"description": "dry run", "goals": ["dry run"]} for person in llm_people}
        elif p.type == "attribute":
            attribute = next(a for a in template.attributes if a.id == p.attribute)
            values[p.name] = {person.id: (attribute.min + attribute.max) // 2
                              for person in template.people if person.role == attribute.role}
        elif p.type == "disruptions":
            values[p.name] = _dry_run_disruptions(template)
    return values


def _dry_run_disruptions(template: Template) -> list[dict[str, Any]]:
    disruptions = []
    for i, d in enumerate(template.disruptions):
        period = min(i + 1, template.calendar.periods)
        if d.kind == "obstacle":
            duty = next(x for x in template.duties if x.id == d.duty)
            attribute = next((a for a in template.attributes if a.id == duty.obstacle_attribute), None)
            people = [p.id for p in template.people if p.role == duty.owed_by]
            disruptions.append({"kind": d.id, "period": period, "steps": [1], "people": people,
                                "delay": attribute.max if attribute else 1, "description": "dry run"})
        elif d.kind == "conflict":
            duty = next(x for x in template.duties if x.id == d.duty)
            people = [p.id for p in template.people if p.role == duty.owed_by]
            entry = {"kind": d.id, "period": period, "steps": [1], "people": people[:1], "description": "dry run"}
            if d.routine:  # slice M6: a routine clash recurs, so the dry run covers a range too
                entry.update(until_period=template.calendar.periods, every=2)
            disruptions.append(entry)
        elif d.kind == "capacity":
            disruptions.append({"kind": d.id, "period": period, "capacity": 0, "description": "dry run"})
        else:
            disruptions.append({"kind": d.id, "period": period,
                                "steps": [template.calendar.steps_per_period], "description": "dry run"})
    return disruptions


def scripted_decider(template: Template) -> Decider:
    """Tries every action the person's role allows, with parameters built from their types.
    Refusals are fine; the dry run checks the engine never breaks."""
    roles = {r.id: r for r in template.roles}
    actions = {a.id: a for a in template.actions}
    owers = [p.id for p in template.people if any(d.owed_by == p.role for d in template.duties)]

    def params_for(action, context: DecisionContext) -> dict[str, Any]:
        params = {}
        for spec in action.params:
            if spec.type == "step":
                params[spec.name] = context.step
            elif spec.type == "step_list":
                params[spec.name] = context.uncovered_missed[-1:] or [context.step]
            elif spec.type == "person":
                params[spec.name] = owers[0] if owers else context.person
            elif spec.type == "bool":
                params[spec.name] = True
            elif spec.type == "request":
                offered = [r["request_id"] for r in context.offered_requests]
                params[spec.name] = (offered or context.pending_requests or ["R1"])[0]
            elif spec.type == "outcome":
                params[spec.name] = "approved"
            elif spec.type == "str":
                params[spec.name] = "dry run"
        return params

    def decide(contexts: list[DecisionContext]) -> list[PhaseDecision]:
        return [PhaseDecision(person=c.person, reason="dry run",
                              proposals=[Proposal(action=a, params=params_for(actions[a], c))
                                         for a in roles[c.role].actions])
                for c in contexts]

    return decide


def dry_run(template: Template) -> list[str]:
    """Runs a full term with the scripted decider. Returns what broke (empty means ok)."""
    try:
        engine = simulate(template, dry_run_values(template), scripted_decider(template))
    except Exception as exc:  # noqa: BLE001 - any crash is a dry-run failure to report
        return [f"dry run failed: {type(exc).__name__}: {exc}"]
    errors = []
    for i, event in enumerate(engine.events, 1):
        if event.event_id != f"E-{i:04d}":
            errors.append(f"dry run: event {event.event_id} is out of sequence")
        for cause in event.caused_by:
            if int(cause.removeprefix("E-")) >= i:
                errors.append(f"dry run: {event.event_id} is caused by a later event {cause}")
    for duty in template.duties:
        unrecorded = [s for s in range(1, engine.total_steps + 1)
                      if s not in engine.recorded_steps[duty.id] | engine.cancelled[duty.id]]
        if unrecorded:
            errors.append(f"dry run: duty '{duty.id}' was never recorded at steps {unrecorded}")
    if template.checks and not any(e.type == "check_evaluated" for e in engine.events):
        errors.append("dry run: no check ran")
    if not any(e.type == "decision" for e in engine.events):
        errors.append("dry run: nobody was ever asked to decide")
    return errors[:5]
