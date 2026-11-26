"""The evidence behind a finding (slice 9, the hero view): its chain as ordered steps.

Each step is one event of the chain, in run order, with its state change, a plain sentence and a
label that says what kind of evidence it is:
- `recorded fact`: something that happened or was done (a disruption, a record, a plan, a filing);
- `calculated`: what a rule worked out (a queue, a count, a check);
- `AI interpretation`: an AI person's decision, with the reason they gave in their own words.

The sentences are general patterns; every word about the setting (the step and period names, what
a met or missed duty is called, the request, count and check names, the outcomes) comes from the
template's terms and labels, so the same code words a curfew chain as well as an attendance one.

The check step carries a `calculation`: the count recomputed from the run's own events up to the
check, as it stood and as it would be if the pending requests were approved, with whether that
matches the figures the check recorded.
"""

from functools import lru_cache
from typing import Any, Literal

from pydantic import BaseModel, Field

from rulestorm.core.engine import count_records
from rulestorm.core.model import Template, load_template

Label = Literal["recorded fact", "calculated", "AI interpretation"]
CALCULATED = {"queue_processed", "queue_over_capacity", "decision_awaiting", "decision_not_made",
              "check_evaluated", "count_calculated", "count_near_threshold", "many_missed"}


class Figure(BaseModel):
    met: int
    due: int
    missed: int
    value: float | None
    text: str


class Calculation(BaseModel):
    count: str = Field(description="the count's label")
    kind: str
    recorded: Figure = Field(description="as it stood at the check")
    if_pending_approved: Figure
    pending_requests: list[str]
    comparison: str
    threshold: float
    outcome: str
    matches_recorded: bool = Field(description="the recomputed figures equal the ones the check recorded")


class Step(BaseModel):
    event_id: str
    period: int
    step: int | None
    type: str
    actor: str
    label: Label
    text: str = Field(description="what happened, in the template's terms")
    state_change: dict[str, Any]
    interpretation: str | None = Field(None, description="an AI person's own stated reason")
    calculation: Calculation | None = None


class Evidence(BaseModel):
    finding_id: str
    run_id: str
    kind: str
    title: str
    person: str
    steps: list[Step]


@lru_cache
def template_named(template_id: str) -> Template:
    """Templates are files that don't change while the server runs; checking one takes a dry run."""
    return load_template(template_id)


def evidence(finding: dict[str, Any], events: list[dict[str, Any]], template: Template) -> Evidence:
    by_id = {e["event_id"]: e for e in events}
    words = _Words(template)
    steps = []
    for event_id in finding["chain"]:
        e = by_id[event_id]
        label = _label(e)
        step = Step(event_id=event_id, period=e["period"], step=e.get("step"), type=e["type"], actor=e["actor"],
                    label=label, text=words.sentence(e), state_change=e.get("state_change") or {})
        if label == "AI interpretation":
            step.interpretation = e["payload"].get("reason") or None
        if e["type"] == "check_evaluated":
            step.calculation = calculation(e, events, template, words)
        steps.append(step)
    return Evidence(finding_id=finding["finding_id"], run_id=finding["run_id"], kind=finding["kind"],
                    title=finding["title"], person=finding["person"], steps=steps)


def calculation(check: dict[str, Any], events: list[dict[str, Any]], template: Template, words=None) -> Calculation:
    """The check's count, recomputed from the events before it, as the engine counts: met ÷ due for
    a rate or the number missed for a tally; a pending request counts as missed unless assumed
    approved; cancelled occurrences are left out where the count says so, and excused ones are
    read as the check recorded (left out, or counted as met), through the engine's `count_records`."""
    words = words or _Words(template)
    p = check["payload"]
    count = next(c for c in template.counts if c.id == p["count"]["count"])
    person = p["person"]
    covering = {r.id for r in template.request_types if r.covers == count.duty}
    records: dict[int, str] = {}
    cancelled: set[int] = set()
    requests: dict[str, dict[str, Any]] = {}
    for e in events:
        if e["seq"] >= check["seq"]:
            break
        q = e["payload"]
        if e["type"] in ("duty_recorded", "record_corrected") and q.get("person") == person and q.get("duty") == count.duty:
            for change in e["state_change"].values():
                records[e["step"]] = change["to"]
        elif e["type"] == "occurrence_cancelled" and q.get("duty") == count.duty:
            cancelled.add(e["step"])
        elif e["type"] == "request_filed" and q["person"] == person and q["request_type"] in covering:
            requests[q["request_id"]] = {"status": "pending", "steps": q["steps"], "approved": []}
        elif e["type"] == "request_decided" and q["request_id"] in requests:
            requests[q["request_id"]].update(status=q["decision"], approved=q.get("approved_steps") or [])
        elif e["type"] == "request_endorsement_refused" and q["request_id"] in requests:
            requests[q["request_id"]]["status"] = "rejected"
    pending = [r for r, v in requests.items() if v["status"] == "pending"]
    reading = p["count"].get("reading", "remove")  # recorded by the engine at the check (slice M1)

    def figure(assume_approved: bool) -> Figure:
        excused: set[int] = set()
        if "approved_request" in count.exclude:
            excused = {s for v in requests.values() if v["status"] == "approved" for s in v["approved"]}
            if assume_approved:
                excused |= {s for r in pending for s in requests[r]["steps"]}
        left_out = cancelled if "cancelled" in count.exclude else set()
        f = count_records(count.kind, records, left_out, excused, reading)
        return Figure(met=f.met, due=f.due, missed=f.missed, value=f.value,
                      text=words.figure(count, f.met, f.due, f.missed, f.value))

    now, approved = figure(False), figure(True)
    recorded, if_approved = p["count"], p["count_if_pending_approved"]
    matches = all((f.met, f.due, f.missed, f.value) == (r["met"], r["due"], r["missed"], r["value"])
                  for f, r in ((now, recorded), (approved, if_approved))) and pending == p["pending_requests"]
    return Calculation(count=count.label, kind=count.kind, recorded=now, if_pending_approved=approved,
                       pending_requests=pending, comparison=p["comparison"], threshold=p["threshold"],
                       outcome=words.outcome(p), matches_recorded=matches)


def _label(event: dict[str, Any]) -> Label:
    if event["type"] == "decision":
        return "AI interpretation"
    if event["type"] in CALCULATED or (event["type"] == "request_decided" and event["payload"].get("rule")):
        return "calculated"
    return "recorded fact"


class _Words:
    """General sentence patterns, filled in with the template's own words."""

    def __init__(self, t: Template) -> None:
        self.t = t
        terms = t.terms
        self.step_word = terms.get("step", "step")
        self.period_word = terms.get("period", "period")
        self.request = terms.get("request", "request")
        self.requests = terms.get("requests", "requests")
        self.met = terms.get("duty_met", "met")
        self.missed = terms.get("duty_missed", "missed")
        self.missed_plural = terms.get("missed_plural", "misses")
        self.actions = {a.id: a.label for a in t.actions}
        self.duties = {d.id: d.label for d in t.duties}
        attributes = {a.id: a.label for a in t.attributes}
        self.margin = {d.id: attributes.get(d.obstacle_attribute) for d in t.duties}
        self.checks = {c.id: c.label for c in t.checks}
        self.counts = {c.id: c for c in t.counts}
        self.spp = t.calendar.steps_per_period

    def when(self, step: int | None, period: int | None = None) -> str:
        if step is None:
            return f"{self.period_word} {period}" if period else ""
        return f"{self.step_word} {step} ({self.period_word} {(step - 1) // self.spp + 1})"

    def steps(self, steps: list[int]) -> str:
        word = self.step_word if len(steps) == 1 else f"{self.step_word}s"
        return f"{word} {', '.join(map(str, steps))}"

    def figure(self, count, met: int, due: int, missed: int, value: float | None) -> str:
        if count.kind == "rate":
            return f"{count.label} {met} / {due} = {value:g}%" if value is not None else f"{count.label}: nothing due yet"
        return f"{count.label}: {missed}"

    def outcome(self, p: dict[str, Any]) -> str:
        return (p.get("outcome") or p.get("standing")
                or self.t.terms.get("check_passed" if p["passed"] else "check_failed", "passed" if p["passed"] else "failed"))

    def sentence(self, e: dict[str, Any]) -> str:
        p, actor, when = e["payload"], e["actor"], self.when(e.get("step"), e["period"])
        kind = e["type"]
        if kind == "obstacle":
            what = p.get("description") or p["disruption"]
            if p.get("conflict"):  # a personal clash: no delay, the person chooses
                return (f"{what}: a {'routine' if p.get('routine') else 'non-routine'} clash with "
                        f"'{self.duties.get(p['duty'], p['duty'])}' for {', '.join(p['people'])}, {when}")
            return (f"{what}: a delay of {p['delay']} min on "
                    f"'{self.duties.get(p['duty'], p['duty'])}' for {', '.join(p['people'])}, {when}")
        if kind == "capacity_changed":
            return f"{p.get('description') or p['disruption']}: {self.requests} capacity set to {p['capacity']} this {self.period_word} ({when})"
        if kind == "occurrence_cancelled":
            return f"{when} cancelled" + (f" by {actor}" if actor != "environment" else "")
        if kind == "decision":
            chosen = [self.actions.get(x["action"], x["action"]) for x in p.get("proposals", [])]
            return f"{actor} decided, {when}: " + ("; ".join(chosen) if chosen else "no action")
        if kind == "duty_planned":
            return f"{actor} planned to be {self.met if p.get('plan') == 'meet' else self.missed}, {when}"
        if kind in ("duty_recorded", "record_corrected"):
            to = next(iter(e["state_change"].values()), {}).get("to", p.get("outcome"))
            word = self.met if to == "met" else self.missed
            if kind == "record_corrected":
                return f"{actor} corrected {p['person']}'s record to {word}, {when}"
            margin = self.margin.get(p["duty"])
            why = f", as the delay was over their {margin}" if p.get("obstacle") and margin else ""
            if to != "met" and "excusable" in p:
                why += (f" (cause {p['cause']}: {'a valid reason' if p['excusable'] else 'not a valid reason'})"
                        if p.get("cause") else " (their own choice: not a valid reason)")
            return f"{p['person']}: {word}, {when}{why}, recorded by {actor}"
        if kind == "request_filed":
            return f"{p['person']} filed {self.request} {p['request_id']} for {self.steps(p['steps'])} (filed {when})"
        if kind in ("request_endorsed", "request_endorsement_refused"):
            verb = "consented to" if kind == "request_endorsed" else "refused consent to"
            return f"{actor} {verb} {self.request} {p['request_id']}, {when}"
        if kind == "request_decided":
            by = f" under the rule '{p['rule']}'" if p.get("rule") else ""
            return f"{self.request} {p['request_id']} {p['decision']} by {actor}{by} after {p.get('waited_periods', 0)} {self.period_word}(s)"
        if kind == "queue_processed":
            return (f"{actor} processed {', '.join(p['processed']) or 'no ' + self.requests} "
                    f"(capacity {p['capacity']}), {when}")
        if kind == "queue_over_capacity":
            return f"{self.requests} held over capacity ({p['capacity']}): {', '.join(p['held'])}, {when}"
        if kind == "decision_awaiting":
            return f"{actor} asked to decide {', '.join(p['offered']) or 'nothing'} (capacity {p['capacity']}), {when}"
        if kind == "decision_not_made":
            return f"no decision was made on {', '.join(p['held'])}, so it stays pending ({when})"
        if kind == "check_evaluated":
            count = self.counts[p["count"]["count"]]
            c = p["count"]
            shown = self.figure(count, c["met"], c["due"], c["missed"], c["value"])
            waiting = (f"; {len(p['pending_requests'])} {self.request}(s) still pending: {', '.join(p['pending_requests'])}"
                       if p["pending_requests"] else "")
            return (f"{self.checks.get(p['check'], p['check'])} for {p['person']}, {when}: {shown} "
                    f"(needs {p['comparison']} {p['threshold']:g}) → {self.outcome(p)}{waiting}")
        if kind == "count_near_threshold":
            label = self.counts[p["count"]].label if p.get("count") in self.counts else p.get("count")
            return f"{p['person']}: {label} {p['value']:g} is near the threshold of {p['threshold']:g}, {when}"
        if kind == "count_calculated":
            count = self.counts[p["count"]]
            return f"{p['person']}: {self.figure(count, p['met'], p['due'], p['missed'], p['value'])}, {when}"
        if kind == "many_missed":
            return f"{', '.join(p.get('people', []))} were {self.missed}, {when}"
        if kind in ("message_sent", "response_given"):
            return f"{actor} to {p.get('to')}: {self.actions.get(p.get('action'), p.get('action'))}, {when}"
        if kind == "action_rejected":
            return f"{actor}: {self.actions.get(p.get('action'), p.get('action'))} refused ({p.get('detail') or p.get('reason')}), {when}"
        if kind == "attribute_set":
            return f"{actor} changed a setting, {when}"
        return f"{kind} by {actor}, {when}"
