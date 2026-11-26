"""Fixed cases (`cli engine check --case <file> --core`): a whole term played from a file, no model.

A case file names its template and values and says what people do, by person and step:

    "template": "<template id>",   "values": {...},   "focus_person": "<person>",
    "count": "<count id>"                      (for the "count" lines)
    "outcomes": {"<person>": {"missed": [<steps>]}}   planned misses; everyone else plans to meet
    "meets": {"<person>": [<steps>]}           explicit plans to meet the duty (slice M7a: during a clash
                                                with an obligation, no plan means they go to the obligation)
    "requests": [{"person", "steps", "reason",
                  "filed_at": <step>           (default: the first covered step if requests are
                                                filed in advance, else the step after the last one),
                  "consent": true | false      (request types that need consent),
                  "decision": "approved" | "rejected"   (request types an LLM person decides)}]
    "report": ["count", "queue", "permission", "ladder", "failed_check", "readings", "obligations", "state",
               "decisions"]
                                                ("decisions", slice M8a: what became of each of the
                                                case's requests: refused at filing, or its decision)
                                                ("state", slice M7c: the focus person's own state
                                                before each step a clash or delay hits them)
                                                the lines to print
    "claims": [{"person", "step", "cause", "then": "<action>"}]   ("claims": a planned miss with
                                                that claimed cause; if the engine refuses the claim,
                                                the person is asked again and takes `then`)
    "readings_at": <period>                    ("readings": the period whose end it counts at, after
                                                that period's queues; default the last)
    "permission_check": {"role", "actor", "action", "params"}
    "variants": [{"label", "values": {...}, ...}]   (slice M8a) the case played once per variant: its
                                                values over the case's, any other key replacing the
                                                case's; each line starts with the variant's label

It runs in the term loop's phase order: period start (capacity disruptions); each step
(obstacles and cancellations, then planned misses, filings and consents, then queues processed
each step, then recording); period end (queues, then checks). Consents and LLM decisions are the
case's scripted answers, given through the template's own actions, so the engine still checks them.
"""

from typing import Any

from rulestorm.core.engine import DEFAULT_OBLIGATION, CountResult, Engine, Event
from rulestorm.core.model import Template


def run_case(case: dict[str, Any], template: Template) -> list[str]:
    """Plays a fixed case through the general engine; returns the lines to print, each with its event ID."""
    if "variants" in case:
        lines = []
        for variant in case["variants"]:
            lines += [f"{variant['label']}: {line}" for line in play_case(case_variant(case, variant), template)[0]]
        return lines
    return play_case(case, template)[0]


def case_variant(case: dict[str, Any], variant: dict[str, Any]) -> dict[str, Any]:
    """One variant of a case (slice M8a): its values over the case's; its other keys replace the case's."""
    base = {k: v for k, v in case.items() if k != "variants"}
    extra = {k: v for k, v in variant.items() if k not in ("label", "values")}
    return {**base, **extra, "values": {**case["values"], **variant.get("values", {})}}


def play_case(case: dict[str, Any], template: Template) -> tuple[list[str], Engine]:
    """`run_case`, also returning the engine the case was played on (its events and records)."""
    e = Engine(template, case["values"])
    focus = case["focus_person"]
    missed = {person: set(o.get("missed", [])) for person, o in case.get("outcomes", {}).items()}
    action_of = {kind: a for a in template.actions for eff in a.effects for kind in [eff.kind]}
    plan_miss = action_of["plan_miss"]
    plan_meet = action_of.get("plan_meet")
    meets = {person: set(steps) for person, steps in case.get("meets", {}).items()}
    requests = [dict(r, filed_at=r.get("filed_at", _default_filing(e, r))) for r in case.get("requests", [])]
    by_id: dict[str, dict] = {}  # request ID -> its case entry
    filings: list[tuple[dict, Event]] = []  # each case request and its filing (or refusal) event
    count_lines: list[str] = []
    reading_lines: list[str] = []
    claim_lines: list[str] = []
    state_lines: list[str] = []
    last_queue: dict[str, Event] = {}
    spp, periods = template.calendar.steps_per_period, template.calendar.periods

    def file_due(step: int) -> None:
        for r in requests:
            if r["filed_at"] != step:
                continue
            file_action = next(a for a in template.actions for eff in a.effects
                               if eff.kind == "file_request" and e.request_types[eff.request_type].filed_by
                               == e.role_of[r["person"]])
            filed = e.propose(r["person"], file_action.id, e.period_of(min(step, e.total_steps)),
                              **{_param(file_action, "step_list"): r["steps"], _param(file_action, "str"): r["reason"]})
            filings.append((r, filed))
            if filed.type != "request_filed":
                continue
            request_id = filed.payload["request_id"]
            by_id[request_id] = r
            role = filed.payload["awaiting_endorsement_by"]
            if role is not None and "consent" in r:
                endorse = next(a for a in template.actions if any(x.kind == "endorse" for x in a.effects))
                e.propose(e.person_with_role(role), endorse.id, filed.period,
                          **{_param(endorse, "request"): request_id, _param(endorse, "bool"): r["consent"]})

    def process(period: int, step: int | None) -> None:
        for rt in template.request_types:
            if (rt.processed == "each_step") != (step is not None):
                continue
            if rt.decided_by == "rule":
                last_queue[rt.id] = e.process_queue(rt.id, period, step)
                continue
            opened = e.open_decisions(rt.id, period, step)
            decide = next(a for a in template.actions
                          if any(x.kind == "decide_request" and x.request_type == rt.id for x in a.effects))
            for request_id in opened.payload["offered"]:
                answer = by_id.get(request_id, {}).get("decision")
                if answer:
                    e.propose(e.person_with_role(rt.handled_by), decide.id, period,
                              **{_param(decide, "request"): request_id, _param(decide, "outcome"): answer})
            last_queue[rt.id] = e.close_decisions(rt.id)

    for period in range(1, periods + 1):
        e.start_period(period)
        for step in range((period - 1) * spp + 1, period * spp + 1):
            e.current_step = step
            e.start_step(step)
            if "state" in case.get("report", []):
                for hit in e.hitting(focus, step):
                    state = e.person_state(focus, step)
                    state_lines.append(f"{focus} state, {template.calendar.step_label} {step}: "
                                       f"{'; '.join(state.lines(template))}  [{hit.event_id}]")
            for person, steps in missed.items():
                if step in steps:
                    e.propose(person, plan_miss.id, period, **{_param(plan_miss, "step"): step})
            for person, steps in meets.items():
                if step in steps:
                    e.propose(person, plan_meet.id, period, **{_param(plan_meet, "step"): step})
            for claim in case.get("claims", []):
                if claim["step"] == step:
                    claim_lines.extend(_claim(e, template, plan_miss, claim, period))
            file_due(step)
            process(period, step)
            e.record_step(step)
            e.current_step = None
        if period == periods:
            file_due(e.total_steps + 1)  # requests for the very last steps, filed after them
            if "count" in case.get("report", []):
                count_lines = _count_lines(e, template, case["count"], focus, period)
        process(period, None)
        if "readings" in case.get("report", []) and period == case.get("readings_at", periods):
            reading_lines = _reading_lines(e, template, case["count"], focus, period)
        e.run_checks(period)

    lines: list[str] = []
    for item in case.get("report", []):
        if item == "count":
            lines += count_lines
        elif item == "queue":
            q = last_queue[case.get("request_type", template.request_types[0].id)]
            lines.append(f"queue FIFO: {','.join(q.payload['processed']) or 'none'} processed, "
                         f"{','.join(q.payload['pending']) or 'none'} pending (capacity {q.payload['capacity']})  "
                         f"[{q.event_id}]")
        elif item == "permission":
            check = case["permission_check"]
            refused = e.propose(check["actor"], check["action"], periods, **check["params"])
            lines.append(f"{check['role']} {check['action']}: "
                         + (f"rejected ({refused.payload['reason']})" if refused.type == "action_rejected" else "allowed")
                         + f"  [{refused.event_id}]")
        elif item == "ladder":
            labels = {c.id: c.label for c in template.counts}
            for ev in _checks_of(e, focus):
                if "outcome" in ev.payload:
                    count = ev.payload["count"]
                    lines.append(f"{focus} {labels[count['count']]}: {count['value']:g} → {ev.payload['outcome']}  "
                                 f"[{ev.event_id}]")
        elif item == "failed_check":
            lines += _failed_check_lines(e, template, focus)
        elif item == "readings":
            lines += reading_lines
        elif item == "claims":
            lines += claim_lines
        elif item == "obligations":
            lines += _obligation_lines(e, template, focus)
        elif item == "state":
            lines += state_lines or [f"state: nothing hit {focus}"]
        elif item == "decisions":
            lines += _decision_lines(e, template, filings)
        else:
            raise ValueError(f"unknown report item {item!r}")
    return lines, e


def _decision_lines(e: Engine, template: Template, filings: list[tuple[dict, Event]]) -> list[str]:
    """Slice M8a: each case request, refused at filing or decided (with the reason), with the event ID."""
    word, step_word = template.terms.get("request", "request"), template.calendar.step_label
    lines = []
    for r, filed in filings:
        head = f"{r['person']} {word} for {step_word} {', '.join(map(str, r['steps']))}"
        if filed.type != "request_filed":
            lines.append(f"{head}: refused ({filed.payload['reason']}: {filed.payload.get('detail', '')})  "
                         f"[{filed.event_id}]")
            continue
        request_id = filed.payload["request_id"]
        decided = next((ev for ev in e.events if ev.type == "request_decided" and ev.payload["request_id"] == request_id),
                       None)
        if decided is None:
            lines.append(f"{head}: {e.requests[request_id].status}  [{filed.event_id}]")
            continue
        why = decided.payload.get("reason")
        by = " by the engine" if decided.actor == "engine" else ""
        lines.append(f"{head}: {decided.payload['decision']}{by}" + (f" ({why})" if why else "")
                     + f"  [{decided.event_id}]")
    return lines


def _default_filing(e: Engine, request: dict[str, Any]) -> int:
    rt = next(rt for rt in e.t.request_types if rt.filed_by == e.role_of[request["person"]])
    return min(request["steps"]) if e.value(rt.timing_param) == "in_advance" else max(request["steps"]) + 1


def _param(action, type_: str) -> str:
    return next(p.name for p in action.params if p.type == type_)


def _count_lines(e: Engine, template: Template, count_id: str, focus: str, period: int) -> list[str]:
    now = e.calculate(count_id, focus, period)
    projected = e.calculate(count_id, focus, period, assume_pending_approved=True)
    word = template.terms.get("requests", "requests")
    pending = len(now.payload["pending"])
    return [f"{CountResult(**_result(now)).text()} ({pending} {word} pending)  [{now.event_id}]",
            f"{CountResult(**_result(projected)).text()} (if {pending} approved)  [{projected.event_id}]"]


def _claim(e: Engine, template: Template, plan_miss, claim: dict[str, Any], period: int) -> list[str]:
    """A planned miss with a claimed cause, as the engine judges it; a refused claim is asked again
    (slice M4), scripted here by the case's `then` action."""
    person, step, cause = claim["person"], claim["step"], claim["cause"]
    step_word = template.calendar.step_label
    params = {_param(plan_miss, "step"): step, _param(plan_miss, "cause"): cause}
    done = e.propose(person, plan_miss.id, period, **params)
    head = f"{person} {plan_miss.id}, {step_word} {step} (cause: {cause})"
    if done.type != "action_rejected":
        return [f"{head}: accepted, cause {done.payload['cause']}  [{done.event_id}]"]
    lines = [f"{head}: rejected ({done.payload['reason']}): {e.situation_text(person, step)}  [{done.event_id}]"]
    then = claim.get("then")
    if then:
        action = next(a for a in template.actions if a.id == then)
        again = e.propose(person, then, period, caused_by=[done.event_id], **{_param(action, "step"): step})
        outcome = then if again.type != "action_rejected" else f"{then} rejected ({again.payload['reason']})"
        lines.append(f"{person} asked again, {step_word} {step}: {outcome}  [{again.event_id}]")
    return lines


def _obligation_lines(e: Engine, template: Template, focus: str) -> list[str]:
    """Slice M7a: each clash with an obligation the person met the duty in (the obligation missed,
    or lost past the limit), and each one they had no plan for (they went to the obligation)."""
    step_word, terms = template.calendar.step_label, template.terms
    meets, missed = terms.get("duty_meets", "meets the duty"), terms.get("duty_missed", "missed")
    lines = []
    for ev in e.events:
        p = ev.payload
        if ev.type in ("obligation_missed", "obligation_lost") and p["person"] == focus:
            what = (f"{p['obligation']} missed ({p['missed']} of {p['limit']})" if ev.type == "obligation_missed"
                    else p["lost"])
            lines.append(f"{focus} {meets} during {p['obligation']}, {step_word} {ev.step}: {what}  [{ev.event_id}]")
        elif ev.type == "duty_recorded" and p["person"] == focus and p["plan"] == DEFAULT_OBLIGATION:
            kind = e.disruption_kinds[e.event(p["cause"]).payload["disruption"]]
            lines.append(f"{focus} no plan during {kind.obligation.label}, {step_word} {ev.step}: goes to "
                         f"{kind.obligation.label}, {missed} ({'routine' if kind.routine else 'not routine'})  "
                         f"[{ev.event_id}]")
    return lines or [f"obligations: none for {focus}"]


def _reading_lines(e: Engine, template: Template, count_id: str, focus: str, period: int) -> list[str]:
    """The same records counted under each excused reading the count's policy choice allows (slice M1)."""
    count = next(c for c in template.counts if c.id == count_id)
    if count.excused_param is None:
        raise ValueError(f"count '{count_id}' has no excused reading to compare")
    p = next(p for p in template.parameters if p.name == count.excused_param)
    lines = []
    for reading in p.choices:
        ev = e.calculate(count_id, focus, period, reading=reading)
        r = ev.payload
        figure = (f"{r['met']} / {r['due']} = {r['value']:.1f}%" if r["kind"] == "rate" and r["value"] is not None
                  else f"{r['missed']}")
        words = (p.sentences or {}).get(reading, reading)
        lines.append(f"{count.label} {figure} ({words})  [{ev.event_id}]")
    return lines


def _checks_of(e: Engine, person: str) -> list[Event]:
    return [ev for ev in e.events if ev.type == "check_evaluated" and ev.payload["person"] == person]


def _failed_check_lines(e: Engine, template: Template, focus: str) -> list[str]:
    """The person's first failed check and its chain, as slice 8's detector finds it: the events
    behind it along their own path, from the disruption to the check."""
    from rulestorm.detect import detect

    found = next((f for f in detect("case", [ev.model_dump() for ev in e.events], template)
                  if f.kind == "check_failed" and f.person == focus), None)
    if found is None:
        return [f"check failed: none for {focus}"]
    return [f"check failed: {found.check_label} for {focus} ({found.outcome})  [{found.check_event_id}]",
            "chain: " + " → ".join(f"{i} {e.event(i).type}" for i in found.chain)]


def _result(event: Event) -> dict[str, Any]:
    return {k: event.payload[k] for k in CountResult.model_fields}
