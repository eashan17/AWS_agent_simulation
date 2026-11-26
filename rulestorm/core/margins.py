"""How many misses fail each check, and each person's own state (slice M7c).

`misses_to_fail` (moved here from rulebook.py on 27 Nov: it is general) works out, from the
template and the blueprint's values alone, the fewest misses that fail each check. `person_state`
gives one person their own record at a step, recomputed from the engine's records and never kept
apart from them: per count, what they missed, what is excused or pending, and how many misses they
have left before each check (every ladder step too); per obligation that can hit them, how many
they missed, their limit, how many are left and whether it is lost.

The brief's agent schema had a person's memory, resources and current strategy as state; the plan
of 24 Nov kept 3 memory notes and a strategy line, and the numbers reached people as rule
sentences. In the M7b runs nobody used the misses they had left. The state is what they now decide
from; the rules say how things work, the state says where the person stands.

No domain word lives here: every label comes from the template.
"""

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from rulestorm.core.model import Template

if TYPE_CHECKING:
    from rulestorm.core.engine import Engine


class MissesToFail(BaseModel):
    """How many misses make a person fail one check (or reach one ladder step)."""

    check: str
    outcome: str  # the template's word for failing, or the ladder step's outcome
    period: int | None  # the period a single-threshold check runs in; None for a ladder (every period)
    due: int  # occurrences counted by then (a ladder: the whole term)
    threshold: float
    misses: int | None  # None: no number of misses fails it


def _first_failing(kind: str, comparison: str, threshold: float, due: int) -> int | None:
    from rulestorm.core.engine import count_value, passes

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


# --- a person's own state (slice M7c) ----------------------------------------------------------


class CheckMargin(BaseModel):
    check: str
    label: str = Field(description="the check's label, or the ladder step's outcome")
    outcome: str = Field(description="what failing it means, in the template's words")
    misses_left: int | None = Field(description="misses they can still take and pass; 0: the next one fails it; "
                                                "None: no number of misses fails it")
    failing: bool = Field(False, description="already past it, even if they meet every occurrence left")
    done: str | None = Field(None, description="the check already ran for good: its result")


class CountState(BaseModel):
    count: str
    label: str
    text: str = Field(description="the count as the engine shows it, e.g. 4/6 = 66.7%")
    missed: int = Field(description="occurrences recorded missed, excused or not")
    excused: int = Field(description="missed occurrences an approved request covers")
    pending: int = Field(description="missed occurrences a pending request covers (they count as missed)")
    checks: list[CheckMargin]
    # Slice M8a: with a filing deadline, each uncovered miss still open to a request -> the last
    # step a request for it can be filed in.
    can_file: dict[int, int] = Field(default_factory=dict)


class ObligationState(BaseModel):
    kind: str = Field(description="the clash's disruption kind")
    obligation: str
    missed: int
    limit: int
    left: int = Field(description="how many more they can miss before it is lost")
    lost: bool
    lost_label: str


class PersonState(BaseModel):
    person: str
    step: int
    counts: list[CountState] = Field(default_factory=list)
    obligations: list[ObligationState] = Field(default_factory=list)

    def lines(self, template: Template) -> list[str]:
        """The state in the template's words, one line per count and per obligation."""
        missed_word = template.terms.get("missed_plural", "misses")
        out = []
        for c in self.counts:
            covered = f" ({c.excused} excused, {c.pending} pending)" if c.excused or c.pending else ""
            if c.label == missed_word:  # a tally of the misses themselves: what counts, then all of them
                bits = ([f"{c.label} {c.text}"] if c.text == str(c.missed)
                        else [f"{c.label} {c.text} counted", f"{c.missed} in all{covered}"])
            else:
                bits = [f"{c.label} {c.text}", f"{missed_word} {c.missed}{covered}"]
            if c.can_file:
                step_word = template.calendar.step_label
                bits.append(f"can still file for " + ", ".join(f"{step_word} {s} (until {step_word} {last})"
                                                              for s, last in sorted(c.can_file.items())))
            for m in c.checks:
                if m.done:
                    bits.append(f"{m.label}: {m.done}")
                elif m.failing:
                    bits.append(f"already {m.outcome} at {m.label}")
                elif m.misses_left is not None:
                    bits.append(f"{m.misses_left} left before {m.label}")
            out.append("; ".join(bits))
        for o in self.obligations:
            out.append(f"{o.obligation}: {o.lost_label}" if o.lost
                       else f"{o.obligation} missed {o.missed} of {o.limit}, {o.left} left")
        return out


def person_state(engine: "Engine", person: str, step: int) -> PersonState:
    """The person's own state before `step` is recorded, from the engine's records."""
    e, t = engine, engine.t
    spp = t.calendar.steps_per_period
    period = e.period_of(min(step, e.total_steps))
    counts = []
    for c in t.counts:
        duty = e.duties[c.duty]
        if not e.owes(person, duty):
            continue
        now = e.count(c.id, person)
        own = [r for r in e.requests.values() if r.person == person and e.request_types[r.request_type].covers == c.duty]
        missed_steps = {s for s in e.recorded_steps[c.duty] if e.records.get((c.duty, person, s)) == "missed"}
        excused = {s for r in own if r.status == "approved" for s in r.approved_steps} & missed_steps
        pending = {s for r in own if r.status == "pending" for s in r.steps} & missed_steps - excused
        cancelled = e.cancelled[c.duty] if "cancelled" in c.exclude else set()
        checks = []
        for check in t.checks:
            if check.count != c.id:
                continue
            if check.ladder is None:
                at = e.value(check.at_param)
                horizon = at * spp
                done = None
                if period > at or step > horizon:
                    result = _last_check(e, check.id, person)
                    done = result or None
                checks.append(_margin(e, c, now, check.id, check.label, t.terms.get("check_failed", "failed"),
                                      check.comparison, e.value(check.threshold_param), horizon, cancelled, step, done))
            else:
                reached = e.ladder_reached.get((check.id, person), 0)
                for i, ladder_step in enumerate(check.ladder):
                    done = "reached" if i < reached else None
                    checks.append(_margin(e, c, now, check.id, ladder_step.outcome, ladder_step.outcome,
                                          check.comparison, e.value(ladder_step.threshold_param), e.total_steps,
                                          cancelled, step, done))
        counts.append(CountState(count=c.id, label=c.label, text=now.text(), missed=len(missed_steps),
                                 excused=len(excused), pending=len(pending), checks=checks,
                                 can_file=_can_file(e, c.duty, missed_steps - excused - pending, step)))
    return PersonState(person=person, step=step, counts=counts, obligations=_obligations(e, person))


def _can_file(e: "Engine", duty_id: str, uncovered: set[int], step: int) -> dict[int, int]:
    """Slice M8a: with a filing deadline, the uncovered misses a request can still be filed for,
    each with the last step to file it (the end of the period the deadline runs to)."""
    rt = e.request_type_for(duty_id)
    deadline = int(e.reading(rt.deadline_param, 0) or 0) if rt else 0
    if not deadline:
        return {}
    spp = e.t.calendar.steps_per_period
    out = {}
    for s in sorted(uncovered):
        last = min((e.period_of(s) + deadline) * spp, e.total_steps)
        if last >= step:
            out[s] = last
    return out


def _margin(e: "Engine", count, now, check_id: str, label: str, outcome: str, comparison: str, threshold: float,
            horizon: int, cancelled: set[int], step: int, done: str | None) -> CheckMargin:
    """Misses left before this check: the occurrences counted now (`now.due`, as the engine counts
    them) plus every occurrence still to come up to the check, each assumed met."""
    to_come = sum(1 for s in range(step, horizon + 1)
                  if s not in cancelled and s not in e.recorded_steps[count.duty])
    fails_at = _first_failing(count.kind, comparison, threshold, now.due + to_come)
    if fails_at is None:
        return CheckMargin(check=check_id, label=label, outcome=outcome, misses_left=None, done=done)
    failing = now.missed >= fails_at
    return CheckMargin(check=check_id, label=label, outcome=outcome, failing=failing and done is None,
                       misses_left=max(fails_at - now.missed - 1, 0), done=done)


def _last_check(e: "Engine", check_id: str, person: str) -> str:
    for ev in reversed(e.events):
        if ev.type == "check_evaluated" and ev.payload["check"] == check_id and ev.payload["person"] == person:
            p = ev.payload
            return p.get("outcome") or e.t.terms.get("check_passed" if p["passed"] else "check_failed",
                                                     "passed" if p["passed"] else "failed")
    return ""


def _obligations(e: "Engine", person: str) -> list[ObligationState]:
    """Each obligation a clash in the blueprint can cost this person (it names them), in template order."""
    out = []
    for kind in e.t.disruptions:
        ob = kind.obligation
        if ob is None or not any(d.kind == kind.id and person in d.people for d in e.disruptions):
            continue
        limit = e.attributes.get((person, ob.limit_attribute))
        if limit is None:
            continue
        missed = e.obligation_missed.get((person, kind.id), 0)
        lost = (person, kind.id) in e.obligation_lost
        out.append(ObligationState(kind=kind.id, obligation=ob.label, missed=missed, limit=limit,
                                   left=max(limit - missed, 0), lost=lost, lost_label=ob.lost_label))
    return out
