"""Finding detection (slice 8): the problems in a finished run, found from its events alone.

Two kinds, as BRIEF must-have 7 defines them, on any template:
- `check_failed`: a person fails a check (the objective failed). For an escalation ladder that is
  its last step, the only one whose `passed` is false.
- `pending_at_check`: a person's request is still waiting when a check of them runs (a bottleneck).

Each finding stores its chain: the events behind the check along that person's own path, found by
following `caused_by` links back from the check, in run order, so it runs from the disruption (when
one hit them) to the check. A link that is about another person who owes the template's duty (their
records, plans, requests and decisions) is not followed, so one person's chain never borrows
another's (slice 5 gotcha). Events about nobody in particular, such as a capacity change or a queue
that held the request, stay in the chain.

Slice M2 adds a third kind and marks which findings are harm:
- `near_threshold`: a person passed, but with at most one miss to spare before the step that
  harms them (a single check's fail point, or a ladder's last step). Not harm: it shows where the
  rule nearly bit. It is numbered after every finding of the older kinds, so their IDs don't move.
- `harm` is true for `check_failed` and `pending_at_check`; it is worked out from the kind, so a
  finding stored before M2 gets it when read (`with_harm`).
A single check's margin is read from its own `check_evaluated` event. A ladder's last step is
usually never reached, so its margin comes from the ledger (slice M3), counted from the records at
the end of the term; that needs the blueprint's values (the last step's threshold), so without
them ladders give no near miss.

Slice M9: every harm also gets a `cause_class` (rulestorm/cause.py): why it happened, by rules
over the records (no_reply, ai_mistake, forced, process, trade_off, chosen), with a one-line
`cause_detail` and, for a trade_off, the clash's recurrence and the person's limit.

Detection reads only the engine's general event types; titles come from the template's terms
(`finding_check_failed`, `finding_pending_at_check`, `finding_near_threshold`), never from code.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from rulestorm.core.model import Template
from rulestorm.ledger import margins
from rulestorm.rulebook import _first_failing

Kind = Literal["check_failed", "pending_at_check", "near_threshold", "obligation_lost"]
KINDS: tuple[Kind, ...] = ("check_failed", "pending_at_check", "near_threshold", "obligation_lost")
HARM_KINDS: tuple[str, ...] = ("check_failed", "pending_at_check", "obligation_lost")
NEAR_SPARE = 1  # a pass with at most this many misses to spare is a near miss
DISRUPTION_TYPES = ("obstacle", "capacity_changed", "occurrence_cancelled")
# Used only when a template has no finding title in its terms.
_FALLBACK_TITLES = {"check_failed": "{check} failed", "pending_at_check": "{request} still pending at the {check}",
                    "near_threshold": "{check} passed with one miss to spare",
                    "obligation_lost": "Keeping the rule cost a person their obligation"}


class Finding(BaseModel):
    finding_id: str = Field(description="<run_id>-F<n>, unique across runs")
    run_id: str
    kind: Kind
    title: str
    person: str
    # The check fields are None on an obligation_lost finding (slice M7b): no check is involved.
    check: str | None = Field(None, description="the check's id in the template")
    check_label: str | None = None
    check_event_id: str | None = None
    period: int
    outcome: str | None = Field(None, description="the check's result in the template's words")
    count: dict[str, Any] | None = Field(None, description="the count at the check, as recorded")
    count_if_pending_approved: dict[str, Any] | None = None
    pending_requests: list[str] = Field(default_factory=list)
    disruptions: list[str] = Field(description="the chain's disruption event IDs, in order")
    chain: list[str] = Field(description="event IDs in run order, ending at the check")
    harm: bool = Field(False, description="did the rule harm the person (set from the kind)")
    spare: int | None = Field(None, description="near_threshold: misses to spare before the harmful step")
    # obligation_lost (slice M7b): the loss event the chain ends at, and what was lost.
    obligation_event_id: str | None = None
    obligation: str | None = Field(None, description="obligation_lost: what was missed, e.g. a shift")
    lost: str | None = Field(None, description="obligation_lost: what happened past the limit")
    # Slice M9: why the harm happened (None on a finding that isn't harm).
    cause_class: Literal["no_reply", "ai_mistake", "forced", "process", "trade_off", "chosen"] | None = None
    cause_detail: str | None = None
    trade_off: dict[str, Any] | None = Field(None, description="trade_off: each clash's recurrence and the "
                                                               "person's limit, from the blueprint")
    cause_shares: dict[str, int] | None = Field(None, description="the harm's unexcused misses at the check, "
                                                                  "by cause class (a mixed cause shows here)")

    @model_validator(mode="after")
    def _harm_from_kind(self) -> "Finding":
        self.harm = self.kind in HARM_KINDS
        return self


def with_harm(finding: dict[str, Any]) -> dict[str, Any]:
    """A stored finding with its `harm` flag (findings saved before slice M2 have none)."""
    return {**finding, "harm": finding.get("kind") in HARM_KINDS}


def detect(run_id: str, events: list[dict[str, Any]], template: Template,
           values: dict[str, Any] | None = None) -> list[Finding]:
    """Every finding in a run's events: the older kinds ordered by the check event, then kind;
    then the near misses. `values` (the blueprint's) lets ladders give near misses too."""
    by_id = {e["event_id"]: e for e in events}
    owners = {e["payload"]["request_id"]: e["payload"]["person"]
              for e in events if e["type"] == "request_filed"}
    subjects = _subjects(template)
    checks = {c.id: c for c in template.checks}
    seen: set[tuple[Kind, str, str]] = set()  # (kind, person, check): one finding each, the first
    found: list[Finding] = []
    for event in events:
        if event["type"] != "check_evaluated":
            continue
        p = event["payload"]
        kinds = [k for k, hit in (("check_failed", not p["passed"]), ("pending_at_check", bool(p["pending_requests"])))
                 if hit and (k, p["person"], p["check"]) not in seen]
        if not kinds:
            continue
        chain = own_chain(by_id, event["event_id"], p["person"], subjects, owners)
        check = checks.get(p["check"])
        for kind in kinds:
            seen.add((kind, p["person"], p["check"]))
            found.append(Finding(
                finding_id=f"{run_id}-F{len(found) + 1}", run_id=run_id, kind=kind,
                title=title(template, kind), person=p["person"], check=p["check"],
                check_label=check.label if check else p["check"], check_event_id=event["event_id"],
                period=event["period"], outcome=_outcome(template, p),
                count=p["count"], count_if_pending_approved=p["count_if_pending_approved"],
                pending_requests=list(p["pending_requests"]),
                disruptions=[i for i in chain if by_id[i]["type"] in DISRUPTION_TYPES], chain=chain))
    failed = {(f.person, f.check) for f in found if f.kind == "check_failed"}
    for event, spare in _near_misses(events, template, values):
        p = event["payload"]
        if (p["person"], p["check"]) in failed:
            continue
        chain = own_chain(by_id, event["event_id"], p["person"], subjects, owners)
        check = checks.get(p["check"])
        found.append(Finding(
            finding_id=f"{run_id}-F{len(found) + 1}", run_id=run_id, kind="near_threshold",
            title=title(template, "near_threshold"), person=p["person"], check=p["check"],
            check_label=check.label if check else p["check"], check_event_id=event["event_id"],
            period=event["period"], outcome=_outcome(template, p),
            count=p["count"], count_if_pending_approved=p["count_if_pending_approved"],
            pending_requests=list(p["pending_requests"]),
            disruptions=[i for i in chain if by_id[i]["type"] in DISRUPTION_TYPES], chain=chain, spare=spare))
    # Slice M7b: the rule kept someone compliant at the cost of their obligation. Numbered after the
    # older kinds, so their finding IDs don't move.
    for event in events:
        if event["type"] != "obligation_lost":
            continue
        p = event["payload"]
        chain = own_chain(by_id, event["event_id"], p["person"], subjects, owners)
        found.append(Finding(
            finding_id=f"{run_id}-F{len(found) + 1}", run_id=run_id, kind="obligation_lost",
            title=title(template, "obligation_lost"), person=p["person"], period=event["period"],
            disruptions=[i for i in chain if by_id[i]["type"] in DISRUPTION_TYPES], chain=chain,
            obligation_event_id=event["event_id"], obligation=p["obligation"], lost=p["lost"]))
    from rulestorm.cause import classify  # slice M9

    return [Finding(**f) for f in classify(template, values, events, [f.model_dump() for f in found])]


def with_cause(findings: list[dict[str, Any]], template: Template, values: dict[str, Any] | None,
               events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Stored findings with `harm` and, on each harm, its cause class (slice M9); a finding saved
    before M9 gets it when read, worked out from the run's events."""
    from rulestorm.cause import classify

    marked = [with_harm(f) for f in findings]
    if all("cause_class" in f and ("cause_shares" in f or f["kind"] == "obligation_lost") for f in marked if f["harm"]):
        return marked
    return classify(template, values, events, marked)


def _near_misses(events: list[dict[str, Any]], template: Template,
                 values: dict[str, Any] | None) -> list[tuple[dict[str, Any], int]]:
    """(the check event to anchor on, misses to spare) for each person who passed a check with at
    most NEAR_SPARE misses to spare before the step that harms them, in run order."""
    out: list[tuple[dict[str, Any], int]] = []
    counts = {c.id: c for c in template.counts}
    for check in template.checks:
        count = counts[check.count]
        mine = [e for e in events if e["type"] == "check_evaluated" and e["payload"]["check"] == check.id]
        if check.ladder is None:
            for e in mine:
                p = e["payload"]
                if not p["passed"]:
                    continue
                spare = _spare(count.kind, check.comparison, p["threshold"], p["count"]["met"], p["count"]["missed"])
                if spare is not None and 0 < spare <= NEAR_SPARE:
                    out.append((e, spare))
            continue
        if values is None or check.ladder[-1].threshold_param not in values:
            continue
        last: dict[str, dict[str, Any]] = {}  # person -> their last event of this ladder (the anchor)
        for e in mine:
            last[e["payload"]["person"]] = e
        final = {m.person: m for m in margins(template, values, events)
                 if m.check == check.id and m.ladder_step == len(check.ladder)}
        for person, e in last.items():
            m = final.get(person)
            if m is not None and m.spare is not None and 0 < m.spare <= NEAR_SPARE:
                out.append((e, m.spare))
    return sorted(out, key=lambda x: x[0]["seq"])


def _spare(kind: str, comparison: str, threshold: float, met: int, missed: int) -> int | None:
    """Misses to spare before failing (0 or less: failed), with the same number counted."""
    fails_at = _first_failing(kind, comparison, threshold, met + missed)
    return None if fails_at is None else fails_at - missed


def own_chain(by_id: dict[str, dict[str, Any]], start: str, person: str, subjects: set[str],
              owners: dict[str, str]) -> list[str]:
    """The events behind `start` along `person`'s own path, in run order (`start` last)."""
    chain, todo = {start}, list(by_id[start]["caused_by"])
    while todo:
        event_id = todo.pop()
        event = by_id.get(event_id)
        if event is None or event_id in chain or _about_someone_else(event, person, subjects, owners):
            continue
        chain.add(event_id)
        todo += event["caused_by"]
    return sorted(chain, key=lambda i: by_id[i]["seq"])


def title(template: Template, kind: Kind) -> str:
    term = template.terms.get(f"finding_{kind}")
    if term:
        return term
    check = template.checks[0].label if template.checks else "check"
    request = template.terms.get("request", "request")
    return _FALLBACK_TITLES[kind].format(check=check, request=request)


def _subjects(template: Template) -> set[str]:
    """The people who owe a duty: the ones a chain must not mix up."""
    owing = {d.owed_by for d in template.duties}
    return {p.id for p in template.people if p.role in owing}


def _about_someone_else(event: dict[str, Any], person: str, subjects: set[str], owners: dict[str, str]) -> bool:
    p = event["payload"]
    others = subjects - {person}
    if event["actor"] in others or p.get("person") in others:
        return True
    if isinstance(p.get("people"), list) and person not in p["people"]:
        return True
    return owners.get(p.get("request_id"), person) != person


def _outcome(template: Template, payload: dict[str, Any]) -> str:
    if payload.get("outcome") or payload.get("standing"):  # a ladder step reached, or where they stand
        return payload.get("outcome") or payload["standing"]
    key = "check_passed" if payload["passed"] else "check_failed"
    return template.terms.get(key, "passed" if payload["passed"] else "failed")
