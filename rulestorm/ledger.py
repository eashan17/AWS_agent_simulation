"""Who carried the rule (slice M3): a per-run ledger, by rules over the run's records, no AI call.

For every person who owes the template's duty:
- `checks`: the margin to every check, and to every step of an escalation ladder: how many more
  misses, with the same number counted, would fail it (0 or less: failed or reached). A single
  check reads the figure its own `check_evaluated` event recorded (or, before it ran, the records
  up to its period); a ladder rarely emits events, so it is counted from the final records.
- `absences`: their misses, split into excused (an approved request covers it), pending (a request
  still waiting covers it) and unexcused.
- `requests`: filed, refused by the engine at filing, rejected, approved, pending, and the
  longest wait in periods.
- `obligations`: obligations missed and lost (the events slice M7 adds; 0 until then).
- `integrity`: the AI's mistakes: actions the engine refused, false claims of cause (slice M4's
  `claim: …` reason) and decisions with no reply from the model.

Every figure is counted by the engine's own `count_records`, so it can't drift from the checks.
`search.closeness` is a thin wrapper over `margins` (its numbers are the ladder's first step, as
before). No template word lives here: every label comes from the template.
"""

from typing import Any

from pydantic import BaseModel, Field

from rulestorm.core.engine import count_records, count_value, excused_reading
from rulestorm.core.model import Template
from rulestorm.rulebook import _first_failing


class Margin(BaseModel):
    check: str
    label: str
    person: str
    outcome: str = Field(description="what failing it means (the template's word, or the ladder step)")
    ladder_step: int | None = Field(None, description="1-based ladder step; None for a single check")
    period: int | None = Field(None, description="the period a single check runs in")
    where: str
    met: int
    missed: int
    value: float | None
    comparison: str
    threshold: float
    spare: int | None = Field(description="misses to spare before failing it; 0 or less: failed or reached")


class Absences(BaseModel):
    total: int = 0
    excused: int = 0
    unexcused: int = 0
    pending: int = 0


class Requests(BaseModel):
    filed: int = 0
    refused: int = Field(0, description="filings the engine refused (permission or precondition)")
    rejected: int = Field(0, description="decided rejected, or consent refused")
    approved: int = 0
    pending: int = 0
    waited_max: int = Field(0, description="the longest wait from filing to decision, in periods")


class Obligations(BaseModel):
    missed: int = 0
    lost: int = 0


class Integrity(BaseModel):
    refused_actions: int = 0
    refused_by_reason: dict[str, int] = Field(default_factory=dict)
    false_claims: int = 0
    no_reply: int = Field(0, description="decisions where the model call failed or timed out")


class PersonLedger(BaseModel):
    person: str
    label: str
    checks: list[Margin]
    absences: Absences
    requests: Requests
    obligations: Obligations
    integrity: Integrity


class Ledger(BaseModel):
    run_id: str | None = None
    template: str
    people: list[PersonLedger]
    findings: list[dict[str, Any]] = Field(default_factory=list)


# --- reading the records -------------------------------------------------------------------------


def final_records(events: list[dict], duty: str) -> dict[tuple[str, int], str]:
    """(person, step) -> met or missed, from the state changes (corrections applied)."""
    records: dict[tuple[str, int], str] = {}
    for e in events:
        for key, change in (e.get("state_change") or {}).items():
            parts = key.split(".")
            if len(parts) == 4 and parts[0] == "record" and parts[1] == duty:
                records[(parts[2], int(parts[3]))] = change["to"]
    return records


def _filer(events: list[dict]) -> dict[str, str]:
    return {e["payload"]["request_id"]: e["payload"].get("person") or e["actor"]
            for e in events if e["type"] == "request_filed"}


def _excused(events: list[dict]) -> set[tuple[str, int]]:
    filer = _filer(events)
    return {(filer.get(e["payload"]["request_id"]), s) for e in events if e["type"] == "request_decided"
            for s in e["payload"].get("approved_steps") or []}


def tallies(template: Template, events: list[dict], duty: str, exclude_approved: bool,
            last_step: int | None, reading: str = "remove") -> dict[str, tuple[int, int]]:
    """Each person's (met, missed) for one duty from the final records, up to `last_step`, in the
    order the records first appear, counted by `count_records`: occurrences an approved request
    excuses are read as the policy says (left out, or counted as met)."""
    excused = _excused(events) if exclude_approved else set()
    by_person: dict[str, dict[int, str]] = {}
    for (person, step), outcome in final_records(events, duty).items():
        if last_step is not None and step > last_step:
            continue
        by_person.setdefault(person, {})[step] = outcome
    out = {}
    for person, own in by_person.items():
        f = count_records("tally", own, set(), {s for p, s in excused if p == person}, reading)
        out[person] = (f.met, f.missed)
    return out


# --- margins ------------------------------------------------------------------------------------


def margins(template: Template, values: dict[str, Any], events: list[dict]) -> list[Margin]:
    """The margin of every person to every check (each ladder step too), check by check, in the
    order the people's figures appear in the run."""
    t = template
    counts = {c.id: c for c in t.counts}
    out: list[Margin] = []
    for check in t.checks:
        count = counts[check.count]
        exclude = "approved_request" in count.exclude
        reading = excused_reading(t, count, values)
        if check.ladder is None:
            period = values[check.at_param]
            threshold = values[check.threshold_param]
            recorded = {e["payload"]["person"]: (e["payload"]["count"]["met"], e["payload"]["count"]["missed"])
                        for e in events if e["type"] == "check_evaluated" and e["payload"]["check"] == check.id}
            people = recorded or tallies(t, events, count.duty, exclude, period * t.calendar.steps_per_period, reading)
            outcome = t.terms.get("check_failed", "failed")
            for person, (met, missed) in people.items():
                out.append(_margin(check, count, person, met, missed, threshold, outcome, None, period,
                                   f"{t.calendar.period_label} {period}"))
            continue
        people = tallies(t, events, count.duty, exclude, None, reading)
        for person, (met, missed) in people.items():
            for i, step in enumerate(check.ladder):
                out.append(_margin(check, count, person, met, missed, values[step.threshold_param],
                                   step.outcome, i + 1, None, "the term"))
    return out


def _margin(check, count, person, met, missed, threshold, outcome, ladder_step, period, where) -> Margin:
    fails_at = _first_failing(count.kind, check.comparison, threshold, met + missed)
    return Margin(check=check.id, label=check.label, person=person, outcome=outcome, ladder_step=ladder_step,
                  period=period, where=where, met=met, missed=missed, value=count_value(count.kind, met, missed),
                  comparison=check.comparison, threshold=threshold,
                  spare=None if fails_at is None else fails_at - missed)


# --- the ledger ----------------------------------------------------------------------------------


def ledger(template: Template, values: dict[str, Any], events: list[dict],
           findings: list[dict] | None = None, run_id: str | None = None) -> Ledger:
    t = template
    owing = {d.owed_by for d in t.duties}
    subjects = [p for p in t.people if p.role in owing]
    by_person: dict[str, list[Margin]] = {}
    for m in margins(t, values, events):
        by_person.setdefault(m.person, []).append(m)
    duty = t.counts[0].duty if t.counts else t.duties[0].id
    records = final_records(events, duty)
    excused = _excused(events)
    filer = _filer(events)
    filing_actions = {a.id for a in t.actions for e in a.effects if e.kind == "file_request"}
    decided = {e["payload"]["request_id"]: e for e in events if e["type"] == "request_decided"}
    refused_consent = {e["payload"]["request_id"] for e in events if e["type"] == "request_endorsement_refused"}
    filed_at = {e["payload"]["request_id"]: e for e in events if e["type"] == "request_filed"}
    last_period = max((e["period"] for e in events), default=0)
    from rulestorm.agents import is_cap_error  # lazily: agents pulls in the model client

    people = []
    for person in subjects:
        pid = person.id
        own_requests = [r for r, who in filer.items() if who == pid]
        pending_steps = {s for r in own_requests if r not in decided and r not in refused_consent
                         for s in filed_at[r]["payload"]["steps"]}
        missed = [s for (who, s), outcome in records.items() if who == pid and outcome == "missed"]
        absences = Absences(total=len(missed))
        for s in missed:
            if (pid, s) in excused:
                absences.excused += 1
            elif s in pending_steps:
                absences.pending += 1
            else:
                absences.unexcused += 1
        requests = Requests(filed=len(own_requests))
        for r in own_requests:
            if r in refused_consent or (r in decided and decided[r]["payload"]["decision"] == "rejected"):
                requests.rejected += 1
            elif r in decided:
                requests.approved += 1
            else:
                requests.pending += 1
            if r in decided:
                wait = decided[r]["payload"].get("waited_periods")
                wait = decided[r]["period"] - filed_at[r]["period"] if wait is None else wait
            elif r in refused_consent:
                wait = 0
            else:
                wait = last_period - filed_at[r]["period"]
            requests.waited_max = max(requests.waited_max, wait)
        integrity = Integrity()
        for e in events:
            if e["actor"] != pid:
                continue
            if e["type"] == "action_rejected":
                reason = e["payload"]["reason"]
                integrity.refused_actions += 1
                integrity.refused_by_reason[reason] = integrity.refused_by_reason.get(reason, 0) + 1
                integrity.false_claims += reason.startswith("claim")
                requests.refused += e["payload"]["action"] in filing_actions
            elif e["type"] == "decision" and e["payload"].get("error") and not is_cap_error(e["payload"]["error"]):
                integrity.no_reply += 1
        obligations = Obligations(
            missed=sum(1 for e in events if e["type"] == "obligation_missed" and e["payload"].get("person") == pid),
            lost=sum(1 for e in events if e["type"] == "obligation_lost" and e["payload"].get("person") == pid))
        people.append(PersonLedger(person=pid, label=person.label or pid, checks=by_person.get(pid, []),
                                   absences=absences, requests=requests, obligations=obligations,
                                   integrity=integrity))
    from rulestorm.detect import with_harm

    return Ledger(run_id=run_id, template=t.ref, people=people,
                  findings=[{k: f.get(k) for k in ("finding_id", "kind", "person", "check", "harm", "spare")}
                            for f in map(with_harm, findings or [])])


def lines(template: Template, book: Ledger) -> list[str]:
    """One line per person, in the template's words."""
    t = template
    counts = {c.id: c for c in t.counts}
    checks = {c.id: c for c in t.checks}
    missed_word = t.terms.get("missed_plural", "misses")
    period_plural = t.calendar.period_label + "s"
    out = []
    for p in book.people:
        bits = []
        for check_id in dict.fromkeys(m.check for m in p.checks):
            ms = [m for m in p.checks if m.check == check_id]
            count = counts[checks[check_id].count]
            if checks[check_id].ladder is None:
                m = ms[0]
                figure = "n/a" if m.value is None else (f"{m.value:g}%" if count.kind == "rate" else f"{m.value:g}")
                bits.append(f"{figure} at {m.where} (needs {m.comparison} {m.threshold:g}), {m.spare} to spare")
            else:
                steps = ", ".join(f"{m.spare} to {m.outcome}" if m.spare and m.spare > 0 else f"reached {m.outcome}"
                                  for m in ms)
                bits.append(f"{ms[0].missed} {count.label} counted; {steps}")
        if not p.checks:
            bits.append("no figure counted")
        a, r = p.absences, p.requests
        bits.append(f"{missed_word} {a.total} (excused {a.excused}, unexcused {a.unexcused}, pending {a.pending})")
        bits.append(f"requests {r.filed} filed, {r.refused} refused, {r.rejected} rejected, "
                    f"waited {r.waited_max} {period_plural if r.waited_max != 1 else t.calendar.period_label}")
        if p.obligations.missed or p.obligations.lost:
            bits.append(f"obligations {p.obligations.missed} missed, {p.obligations.lost} lost")
        i = p.integrity
        if i.refused_actions or i.false_claims or i.no_reply:
            bits.append(f"refused actions {i.refused_actions}, false claims {i.false_claims}, no reply {i.no_reply}")
        out.append(f"{p.person}: " + "; ".join(bits))
    harm = [f for f in book.findings if f["harm"]]
    near = [f for f in book.findings if f["kind"] == "near_threshold"]
    out.append(f"findings: {len(harm)} harm, {len(near)} near misses"
               + "".join(f"\n  {f['finding_id']} {f['kind']} {f['person']}" for f in book.findings))
    return out


def run_ledger(store, run_id: str) -> tuple[Template, Ledger]:
    """A stored run's ledger, with its blueprint's values (defaults filled) and findings."""
    from rulestorm.core.model import load_template
    from rulestorm.policy import check_version
    from rulestorm.runner import findings_of

    run = store.get_run(run_id)
    if run is None:
        raise LookupError(f"run not found: {run_id}")
    template = load_template(run["template"].split("@")[0])
    record = store.get_blueprint(run["blueprint_id"])
    if record is None:
        raise LookupError(f"run {run_id}'s blueprint {run['blueprint_id']} is missing")
    values = check_version(template, record).blueprint.values
    return template, ledger(template, values, store.run_events(run_id), findings_of(store, run), run_id)
