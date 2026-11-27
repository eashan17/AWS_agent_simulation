"""Why each harm happened (slice M9): a `cause_class` for every harm finding, by rules over the
run's records, no AI call.

The rules run in this order, and the first that holds is the class. Events are looked up by
(person, step) for every step behind the harm: the steps of its chain and the person's misses
counted at the check.

1. `no_reply`: the model call for that person failed or timed out at one of those steps (an
   infrastructure problem, not an AI mistake; the daily call cap is not counted).
2. `ai_mistake`: the person's false claim of cause, or an untrue correction, was refused there.
3. `forced`: the misses obstacles caused (a delay over their slack) are enough on their own to fail
   the check, even had they met every other occurrence.
4. `process`: the harm needs a request: one still pending at the check (every `pending_at_check`
   is process), one refused past the filing deadline, or one rejected for no documentation. Had
   those requests' occurrences been excused, the person would have passed.
5. `trade_off`: it comes from clashes (meeting an obligation cost the duty, or meeting the duty
   cost the obligation), under the policy's reading of what is exceptional. Every
   `obligation_lost` is a trade_off. The finding carries the assumptions that set it: how often
   the clash recurs and the person's limit, from the blueprint.
6. `chosen`: what remains, skips when nothing affected the person.

Misses are counted with the engine's own `count_records`, so a "what if" here can't drift from
the checks. No domain word lives here: every label comes from the template.
"""

from typing import Any

from rulestorm.core.engine import count_records, count_value, excused_reading, passes
from rulestorm.core.model import Template
from rulestorm.ledger import _excused, _filer, final_records

CLASSES = ("no_reply", "ai_mistake", "forced", "process", "trade_off", "chosen")
NOT_THE_RULE = ("no_reply", "ai_mistake", "forced")  # a break of these tells nothing about the rule
UNTRUE_CORRECTION = "precondition: matches_what_happened"
PROCESS_REFUSALS = ("precondition: within_deadline",)
NO_DOCUMENTATION = "no documentation"


def is_ai_mistake(event: dict[str, Any]) -> bool:
    """A refused false claim of cause, or a refused untrue correction."""
    reason = event["payload"].get("reason") or ""
    return event["type"] == "action_rejected" and (reason.startswith("claim") or reason == UNTRUE_CORRECTION)


def _no_reply(event: dict[str, Any]) -> bool:
    from rulestorm.agents import is_cap_error  # lazily: agents pulls in the model client

    error = event["payload"].get("error") if event["type"] == "decision" else None
    return bool(error) and not is_cap_error(error)


def _step_list(params: dict[str, Any]) -> list[int]:
    return next((v for v in params.values() if isinstance(v, list) and all(isinstance(s, int) for s in v)), [])


class _Run:
    """What the rules read, worked out once per run."""

    def __init__(self, template: Template, values: dict[str, Any], events: list[dict[str, Any]]) -> None:
        self.t, self.values, self.events = template, values, events
        self.by_id = {e["event_id"]: e for e in events}
        self.excused = _excused(events)
        self.filer = _filer(events)
        self.filed = {e["payload"]["request_id"]: e for e in events if e["type"] == "request_filed"}
        self.recorded = {(e["payload"]["duty"], e["payload"]["person"], e["step"]): e
                         for e in events if e["type"] == "duty_recorded"}

    def cause_of(self, duty: str, person: str, step: int) -> dict[str, Any] | None:
        """The disruption event that kept them away at that step, if any."""
        payload = (self.recorded.get((duty, person, step)) or {}).get("payload", {})
        cause = payload.get("cause") or payload.get("obstacle")  # runs before M8a name only the obstacle
        return self.by_id.get(cause) if cause else None

    def process_steps(self, person: str, pending: list[str]) -> set[int]:
        """Steps a request covers that the process left unexcused: pending at the check, refused past
        the deadline, or rejected for no documentation."""
        steps = {s for r in pending if r in self.filed for s in self.filed[r]["payload"]["steps"]}
        for e in self.events:
            p = e["payload"]
            if e["type"] == "action_rejected" and e["actor"] == person and p.get("reason") in PROCESS_REFUSALS:
                steps |= set(_step_list(p.get("params") or {}))
            if (e["type"] == "request_decided" and self.filer.get(p["request_id"]) == person
                    and p["decision"] == "rejected" and NO_DOCUMENTATION in (p.get("reason") or "")):
                steps |= set(self.filed[p["request_id"]]["payload"]["steps"]) - set(p.get("approved_steps") or [])
        return steps


def classify(template: Template, values: dict[str, Any] | None, events: list[dict[str, Any]],
             findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The findings, each harm with `cause_class`, `cause_detail` and (trade_off) `trade_off`.
    A finding that isn't harm is returned as it is. Without the blueprint's values, the counting
    rules can't run: a harm that isn't no_reply or ai_mistake gets `cause_class` None."""
    run = _Run(template, values or {}, events)
    return [{**f, **_classify(run, f)} if f.get("harm") else f for f in findings]


def _classify(whole: _Run, f: dict[str, Any]) -> dict[str, Any]:
    # The records as they stood at the check: a request approved, or a record corrected, after it
    # changed nothing the check saw.
    at = whole.by_id.get(f.get("check_event_id") or f.get("obligation_event_id") or "")
    run = _Run(whole.t, whole.values, [e for e in whole.events if e["seq"] <= at["seq"]]) if at else whole
    t, person = run.t, f["person"]
    spp = t.calendar.steps_per_period
    check = next((c for c in t.checks if c.id == f.get("check")), None)
    count = next((c for c in t.counts if check and c.id == check.count), None)
    duty = count.duty if count else (t.duties[0].id if t.duties else None)
    last = f["period"] * spp
    own = {s: o for (who, s), o in final_records(run.events, duty).items() if who == person and s <= last} if duty else {}
    missed = {s for s, o in own.items() if o == "missed"}
    steps = missed | {run.by_id[i]["step"] for i in f.get("chain") or [] if i in run.by_id and run.by_id[i]["step"]}
    if f.get("obligation_event_id") in run.by_id:
        steps.add(run.by_id[f["obligation_event_id"]]["step"])

    mine = [e for e in run.events if e["actor"] == person and e["step"] in steps]
    replies = sorted({e["step"] for e in mine if _no_reply(e)})
    if replies:
        return _out("no_reply", f"the model gave no reply for {person} at {_steps(t, replies)}")
    mistakes = [e for e in mine if is_ai_mistake(e)]
    if mistakes:
        what = " and ".join(dict.fromkeys("an untrue correction" if e["payload"]["reason"] == UNTRUE_CORRECTION
                                          else "a false claim of cause" for e in mistakes))
        return _out("ai_mistake", f"{what} by {person} was refused at "
                                  f"{_steps(t, sorted({e['step'] for e in mistakes}))}")

    if f["kind"] == "obligation_lost":
        kind = run.by_id[f["obligation_event_id"]]["payload"].get("disruption") if f.get("obligation_event_id") in run.by_id else None
        return _out("trade_off", f"meeting the duty during clashes cost {person} the {f.get('obligation')}: "
                                 f"{f.get('lost')}", _trade_off(run, person, [kind] if kind else []))
    if f["kind"] == "pending_at_check":
        n = len(f.get("pending_requests") or [])
        return _out("process", f"{n} {t.terms.get('request', 'request')}{'s' if n != 1 else ''} still waiting at the "
                               f"{f.get('check_label') or 'check'}")
    if check is None or count is None or not run.values:
        return {"cause_class": None, "cause_detail": "the blueprint's values are needed to count the misses"}

    obstacle, clash, kinds = set(), set(), []
    for s in missed:
        cause = run.cause_of(duty, person, s)
        if cause is None or (person, s) in run.excused:
            continue
        if cause["payload"].get("conflict"):
            clash.add(s)
            kinds.append(cause["payload"].get("disruption"))
        else:
            obstacle.add(s)
    process = run.process_steps(person, f.get("pending_requests") or []) & missed
    reading = excused_reading(t, count, run.values)
    threshold = (run.values[check.threshold_param] if check.ladder is None
                 else run.values[check.ladder[-1].threshold_param])
    excused = {s for (who, s) in run.excused if who == person}

    def fails(kept: set[int], also_excused: set[int] = frozenset()) -> bool:
        """Would they still fail with only `kept` missed (every other occurrence met)?"""
        records = {s: ("missed" if s in kept else "met") for s in own}
        tally = count_records("tally", records, set(), excused | set(also_excused), reading)
        return not passes(count_value(count.kind, tally.met, tally.missed), check.comparison, threshold)

    label = check.label
    if obstacle and fails(obstacle):
        return _out("forced", f"{_n(len(obstacle), 'miss', 'misses')} from obstacles over {person}'s slack fail the {label} on "
                              f"their own ({_steps(t, sorted(obstacle))})")
    if process and not fails(missed, process):
        return _out("process", f"excusing {_steps(t, sorted(process))}, which a request covered but the process "
                               f"left unexcused, would pass the {label}")
    chosen = missed - obstacle - clash - process - excused
    if clash and fails(missed - chosen):
        return _out("trade_off", f"{_n(len(clash), 'miss', 'misses')} for clashes the policy doesn't excuse fail the {label}"
                                 + (f", with {_n(len(chosen), 'skip', 'skips')}" if chosen else ""),
                    _trade_off(run, person, list(dict.fromkeys(kinds))))
    return _out("chosen", f"{_n(len(chosen), 'skip', 'skips')} when nothing affected {person} {'was' if len(chosen) == 1 else 'were'} needed to fail the {label}")


def _out(cause_class: str, detail: str, trade_off: dict | None = None) -> dict[str, Any]:
    return {"cause_class": cause_class, "cause_detail": detail, **({"trade_off": trade_off} if trade_off else {})}


def _n(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def _steps(t: Template, steps: list[int]) -> str:
    word = t.calendar.step_label
    return f"{word} {steps[0]}" if len(steps) == 1 else f"{word}s {', '.join(map(str, steps))}"


def _trade_off(run: _Run, person: str, kinds: list[str]) -> dict[str, Any]:
    """The assumptions that set a trade-off: how often each clash recurs for the person (the
    blueprint's disruption entries) and their limit for its obligation."""
    t, values = run.t, run.values
    entries_param = next((p.name for p in t.parameters if p.type == "disruptions"), None)
    entries = values.get(entries_param) or [] if entries_param else []
    clashes = []
    for kind_id in kinds:
        kind = next((k for k in t.disruptions if k.id == kind_id), None)
        if kind is None:
            continue
        limit = None
        if kind.obligation:
            param = next((p for p in t.parameters if p.type == "attribute"
                          and p.attribute == kind.obligation.limit_attribute), None)
            limits = (values.get(param.name) or param.default or {}) if param else {}
            limit = limits.get(person)
        recurs = [{k: e.get(k) for k in ("period", "until_period", "every", "steps") if e.get(k) is not None}
                  for e in entries if e.get("kind") == kind_id and person in (e.get("people") or [])]
        clashes.append({"kind": kind_id, "label": kind.label, "routine": kind.routine,
                        "obligation": kind.obligation.label if kind.obligation else None,
                        "limit": limit, "recurs": recurs})
    return {"clashes": clashes}
