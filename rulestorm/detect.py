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

Detection reads only the engine's general event types; titles come from the template's terms
(`finding_check_failed`, `finding_pending_at_check`), never from code.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field

from rulestorm.core.model import Template

Kind = Literal["check_failed", "pending_at_check"]
KINDS: tuple[Kind, ...] = ("check_failed", "pending_at_check")
DISRUPTION_TYPES = ("obstacle", "capacity_changed", "occurrence_cancelled")
# Used only when a template has no finding title in its terms.
_FALLBACK_TITLES = {"check_failed": "{check} failed", "pending_at_check": "{request} still pending at the {check}"}


class Finding(BaseModel):
    finding_id: str = Field(description="<run_id>-F<n>, unique across runs")
    run_id: str
    kind: Kind
    title: str
    person: str
    check: str = Field(description="the check's id in the template")
    check_label: str
    check_event_id: str
    period: int
    outcome: str = Field(description="the check's result in the template's words")
    count: dict[str, Any] = Field(description="the count at the check, as recorded")
    count_if_pending_approved: dict[str, Any]
    pending_requests: list[str]
    disruptions: list[str] = Field(description="the chain's disruption event IDs, in order")
    chain: list[str] = Field(description="event IDs in run order, ending at the check")


def detect(run_id: str, events: list[dict[str, Any]], template: Template) -> list[Finding]:
    """Every finding in a run's events, ordered by the check event, then kind."""
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
    return found


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
    if payload.get("outcome"):
        return payload["outcome"]
    key = "check_passed" if payload["passed"] else "check_failed"
    return template.terms.get(key, "passed" if payload["passed"] else "failed")
