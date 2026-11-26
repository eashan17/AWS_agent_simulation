"""How the rules work, written out from the template and the approved values (26 Nov, demo fix).

Every person's prompt carries these lines, so the people living a term know the rules the engine
applies to them, not only the policy's own settings: when each check runs and whether its result
is final, how many misses fail it, which occurrences count, and how requests are queued before a
check. Before this, a person was told only "eligibility is checked in week 6"; the stress test's
AI was told the rest (explore.py). Both now take the figures from here, worked out with the
engine's own counting (`count_value`, `passes`), so the words can't drift from what the engine
does. No domain word lives here: every label comes from the template.
"""

from typing import Any

from pydantic import BaseModel

from rulestorm.core.engine import count_value, passes
from rulestorm.core.model import Template


class MissesToFail(BaseModel):
    """How many misses make a person fail one check (or reach one ladder step)."""

    check: str
    outcome: str  # the template's word for failing, or the ladder step's outcome
    period: int | None  # the period a single-threshold check runs in; None for a ladder (every period)
    due: int  # occurrences counted by then (a ladder: the whole term)
    threshold: float
    misses: int | None  # None: no number of misses fails it


def _first_failing(kind: str, comparison: str, threshold: float, due: int) -> int | None:
    for missed in range(due + 1):
        if not passes(count_value(kind, due - missed, missed), comparison, threshold):
            return missed
    return None


def misses_to_fail(template: Template, values: dict[str, Any]) -> list[MissesToFail]:
    """For each check: the fewest misses that fail it, assuming no cancelled occurrences.
    Worked out by the engine's own counting (`count_value`, `passes`), so it can't drift from it."""
    t, cal = template, template.calendar
    counts = {c.id: c for c in t.counts}
    failed = t.terms.get("check_failed", "failed")
    out = []
    for check in t.checks:
        kind = counts[check.count].kind
        if check.ladder is None:
            period = values[check.at_param]
            due = period * cal.steps_per_period
            threshold = values[check.threshold_param]
            out.append(MissesToFail(check=check.id, outcome=failed, period=period, due=due, threshold=threshold,
                                    misses=_first_failing(kind, check.comparison, threshold, due)))
        else:
            due = cal.periods * cal.steps_per_period
            for step in check.ladder:
                threshold = values[step.threshold_param]
                out.append(MissesToFail(check=check.id, outcome=step.outcome, period=None, due=due,
                                        threshold=threshold,
                                        misses=_first_failing(kind, check.comparison, threshold, due)))
    return out


def _a(word: str) -> str:
    return f"{'an' if word[:1].lower() in 'aeiou' else 'a'} {word}"


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def rule_lines(template: Template, values: dict[str, Any]) -> list[str]:
    """The "How the rules work" block of every person's prompt: one line per fact, from the
    template's checks, counts and request types and the blueprint's values. A rule whose value
    the blueprint lacks is left out rather than guessed."""
    t, cal = template, template.calendar
    period, step = cal.period_label, cal.step_label
    counts = {c.id: c for c in t.counts}
    roles = {r.id: r for r in t.roles}
    request = t.terms.get("request", "request")
    missed = t.terms.get("missed_plural", "missed occurrences")
    missed_one = missed[:-1] if missed.endswith("s") else missed
    figures = {}
    try:
        for m in misses_to_fail(t, values):
            figures.setdefault(m.check, []).append(m)
    except KeyError:
        figures = {}
    lines = []
    for check in t.checks:
        count = counts[check.count]
        owes = roles[next(d.owed_by for d in t.duties if d.id == count.duty)].label.lower()
        unit = "%" if count.kind == "rate" else ""
        found = figures.get(check.id, [])
        if check.ladder is None:
            if not found:
                continue
            m = found[0]
            rule = f"{count.label} {check.comparison} {m.threshold:g}{unit}"
            lines.append(f"- {check.label.capitalize()} ({rule}) is checked once, at the end of {period} {m.period}, "
                         f"after {step} {m.due} is recorded. The result is final: nothing that happens "
                         f"after the check changes it, including {_a(request)} approved later.")
            if m.misses is not None:
                lines.append(f"- By then {m.due} {step}s count: {_plural(m.misses, missed_one, missed)} make {_a(owes)} "
                             f"{m.outcome} (if no {step} is cancelled).")
        else:
            reached = "; ".join(f"at {_plural(m.misses, missed_one, missed)}, '{m.outcome}'"
                                for m in found if m.misses is not None)
            if reached:
                lines.append(f"- {check.label.capitalize()} are checked at the end of every {period}, counting the "
                             f"whole term: {reached}. A step once reached stays.")
    for count in t.counts:
        if "approved_request" in count.exclude:
            lines.append(f"- An approved {request} excuses the {step}s it covers; a pending or rejected one "
                         f"still counts them as {missed}.")
        if "cancelled" in count.exclude:
            lines.append(f"- A cancelled {step} doesn't count either way.")
    for rt in t.request_types:
        capacity = values.get(rt.capacity_param)
        if capacity is None:
            continue
        handler = roles[rt.handled_by].label
        if rt.processed == "period_end":
            when, slot = f"at the end of each {period}", period
        else:
            when, slot = f"each {step}, before that {step} is recorded", step
        lines.append(f"- The {handler.lower()} decides {rt.label}s first come, first served, at most {capacity} "
                     f"per {slot}, {when}; the rest wait for the next {slot}.")
        if t.checks:
            lines.append(f"- {rt.label.capitalize()}s are decided before the check in the same {period}, so one "
                         f"filed in time and decided counts at the check; one still waiting at the check "
                         f"counts as {missed}.")
    return lines
