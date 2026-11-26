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

from rulestorm.core.engine import excused_reading
# Moved to core on 27 Nov (slice M7c: the person state needs them); imported here for older callers.
from rulestorm.core.margins import MissesToFail, _first_failing, misses_to_fail  # noqa: F401
from rulestorm.core.model import Template


def _a(word: str) -> str:
    return f"{'an' if word[:1].lower() in 'aeiou' else 'a'} {word}"


def _count(n: int, one: str, many: str) -> str:
    """`1 absence makes`, `3 absences make`: the number, its noun and the verb that agrees."""
    return f"{n} {one} makes" if n == 1 else f"{n} {many} make"


def _labels(kinds, article: bool = False) -> str:
    names = [_a(k.label) if article else k.label for k in kinds]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " or " + names[-1]


def _short(label: str) -> str:
    """An attribute's label without its explanation in brackets: "travel buffer"."""
    return label.split(" (")[0]


def _reading(t: Template, values: dict[str, Any], name: str | None, fallback: Any) -> Any:
    """A reading's value (slice M8a): the blueprint's, else its parameter's default."""
    if name is None:
        return fallback
    param = next((p for p in t.parameters if p.name == name), None)
    return values.get(name, param.default if param is not None and param.default is not None else fallback)


def _stakes(t: Template, values: dict[str, Any], person: str | None, clashes) -> list[str]:
    """One line per clash with an obligation, in the template's fixed order (meet the duty: miss the
    obligation; past the limit: lose it; do nothing: go to it). The person's limit and how many they
    have left are in their state (slice M7c), not here. Left out for someone with no limit."""
    if person is None:
        return []
    lines = []
    for kind in clashes:
        if kind.obligation is None:
            continue
        param = next((p for p in t.parameters if p.type == "attribute" and p.attribute == kind.obligation.limit_attribute),
                     None)
        limits = (values.get(param.name) or param.default or {}) if param else {}
        limit = limits.get(person)
        if limit is None:
            continue
        lines.append(f"- {kind.label.capitalize()}: {kind.obligation.stakes}")
    return lines


def rule_lines(template: Template, values: dict[str, Any], person: str | None = None) -> list[str]:
    """The "How the rules work" block of every person's prompt: one short line per rule the engine
    applies, from the template's structure (checks, duties, disruption kinds, counts, request
    types, actions) and the blueprint's values. A rule whose value the blueprint lacks is left out
    rather than guessed, so the block holds for any template and any values. Kept short on
    purpose: it goes into every decision's prompt. With `person`, a clash that carries an
    obligation states both stakes with that person's own limit (slice M7b)."""
    t, cal = template, template.calendar
    period, step = cal.period_label, cal.step_label
    counts = {c.id: c for c in t.counts}
    roles = {r.id: r for r in t.roles}
    attributes = {a.id: a for a in t.attributes}
    request = t.terms.get("request", "request")
    missed = t.terms.get("missed_plural", "missed occurrences")
    missed_one = missed[:-1] if missed.endswith("s") else missed
    missed_word = t.terms.get("duty_missed", "missed")
    figures: dict[str, list[MissesToFail]] = {}
    try:
        for m in misses_to_fail(t, values):
            figures.setdefault(m.check, []).append(m)
    except KeyError:
        figures = {}

    def owes_label(duty_id: str) -> str:
        return roles[next(d.owed_by for d in t.duties if d.id == duty_id)].label.lower()

    lines: list[str] = []
    last_steps: list[int] = []  # the last step before each single-threshold check
    for check in t.checks:
        count = counts[check.count]
        owes = owes_label(count.duty)
        unit = "%" if count.kind == "rate" else ""
        found = figures.get(check.id, [])
        if check.ladder is None:
            if not found:
                continue
            m = found[0]
            last_steps.append(m.due)
            figure = (f" By then {m.due} {step}s count: {_count(m.misses, missed_one, missed)} {_a(owes)} {m.outcome}."
                      if m.misses is not None else "")
            lines.append(f"- {check.label.capitalize()} ({count.label} {check.comparison} {m.threshold:g}{unit}) is "
                         f"checked once, at the end of {period} {m.period}, after {step} {m.due}. It is final: nothing "
                         f"later changes it, not even {_a(request)} approved later.{figure}")
        else:
            reached = "; ".join(f"at {m.misses} {missed_one if m.misses == 1 else missed}, '{m.outcome}'"
                                for m in found if m.misses is not None)
            if reached:
                lines.append(f"- {check.label.capitalize()} are checked at the end of every {period}, counting the "
                             f"whole term: {reached}. A step once reached stays.")

    for duty in t.duties:
        recorder = roles[duty.recorded_by].label.lower()
        attribute = attributes.get(duty.obstacle_attribute) if duty.obstacle_attribute else None
        delays = [k for k in t.disruptions if k.duty == duty.id and k.kind == "obstacle"]
        clashes = [k for k in t.disruptions if k.duty == duty.id and k.kind == "conflict"]
        stakes = _stakes(t, values, person, clashes)
        clashes = [k for k in clashes if k.obligation is None]  # the rest are stated with their stakes
        unless = ", except during a clash below" if stakes else ""
        lines.append(f"- No action for {_a(step)} means your plan stays: {duty.label}{unless}. Each {step} is recorded "
                     f"automatically from what happened (the {recorder} need not record it), after everyone decides.")
        if delays and attribute:
            late = "" if missed_word.lower() == "late" else f" (arriving late counts as {missed_word})"
            lines.append(f"- {_labels(delays).capitalize()}: a delay longer than your {_short(attribute.label)} means "
                         f"you can't {duty.label} in time{late}; a shorter one doesn't stop you.")
        if clashes:
            lines.append(f"- {_labels(clashes).capitalize()}: you miss the {step} only if you choose to.")
        lines += stakes
        if any(e.kind == "correct_record" and e.duty == duty.id for a in t.actions for e in a.effects):
            lines.append("- A recorded mark can be corrected only to what really happened.")
    for attribute_id in sorted({e.attribute for a in t.actions for e in a.effects if e.kind == "set_attribute"}):
        if attribute_id in attributes:
            lines.append(f"- A change to your {_short(attributes[attribute_id].label)} applies from the next {step}.")

    for count in t.counts:
        bits = []
        if "approved_request" in count.exclude:
            if excused_reading(t, count, values) == "count_as_met":
                met = t.terms.get("duty_met", "met")
                bits.append(f"An approved {request}'s {step}s count as {met}; a pending or rejected one still "
                            f"counts them as {missed}.")
            else:
                bits.append(f"An approved {request} excuses its {step}s; a pending or rejected one still counts "
                            f"them as {missed}.")
        if "cancelled" in count.exclude:
            bits.append(f"A cancelled {step} doesn't count.")
        if bits:
            lines.append("- " + " ".join(bits))

    for rt in t.request_types:
        handler = roles[rt.handled_by].label.lower()
        kinds = [k for k in t.disruptions if k.duty == rt.covers and k.kind in ("obstacle", "conflict")]
        exceptional, routine = [k for k in kinds if not k.routine], [k for k in kinds if k.routine]
        reading = _reading(t, values, rt.exceptional_param, "unforeseen_only")
        if reading == "any_documented":  # slice M8a: a routine cause may be excused too
            exceptional, routine = kinds, []
        no_proof = [k for k in kinds if not k.leaves_proof] if _reading(t, values, rt.proof_param, False) else []
        exceptional = [k for k in exceptional if k not in no_proof]
        if rt.endorsed_by:
            lines.append(f"- {_a(request).capitalize()} needs the {roles[rt.endorsed_by].label.lower()}'s consent "
                         f"before it reaches the {handler}; a refusal ends it.")
        rule = values.get(rt.decision_rule_param) if rt.decision_rule_param else None
        if rt.decided_by == "rule" and rule in ("approve_if_covered_missed", "approve_if_filed_before_occurrence"):
            excused = f"caused by {_labels(exceptional)}" if exceptional else "caused by a disruption"
            if no_proof and not exceptional:
                excused = "with proof"
            refused = "by choice when nothing stopped you" + (f", or for {_labels(routine, article=True)}," if routine else "")
            lines.append(f"- The {handler} excuses only {missed} {excused}; one {refused} is rejected.")
        elif rt.decided_by == "llm":
            lines.append(f"- The {handler} decides each {request} seeing what caused each {missed_one} it covers.")
            if reading != "decider_judges":
                barred = (f"for {_labels(routine, article=True)}, or when nothing stopped you," if routine
                          else "when nothing stopped you")
                lines.append(f"- {_a(request).capitalize()} {barred} is rejected at once, before the {handler} "
                             f"sees it.")
        if no_proof:
            lines.append(f"- Proof is required: {_labels(no_proof)} {'leaves' if len(no_proof) == 1 else 'leave'} "
                         f"no proof, so {_a(request)} for one is rejected for no documentation.")
        deadline = int(_reading(t, values, rt.deadline_param, 0) or 0)
        if deadline:
            unit = period if deadline == 1 else f"{period}s"
            lines.append(f"- {_a(request).capitalize()} must be filed within {deadline} {unit} of the {step} it "
                         f"covers; a later one is refused.")
        capacity = values.get(rt.capacity_param)
        if capacity is None:
            continue
        when = f"at the end of each {period}" if rt.processed == "period_end" else f"each {step}, before it is recorded"
        slot = period if rt.processed == "period_end" else step
        how_many = f"no {rt.label}s" if capacity == 0 else f"up to {capacity} {rt.label}s per {slot}, first come, first served"
        single = any(c.ladder is None for c in t.checks)
        before = (f", before the check; one still waiting at the check counts as {missed}" if single
                  else f"; one still waiting at a check counts as {missed}" if t.checks else "")
        lines.append(f"- The {handler} decides {how_many}, {when}{before}.")
        if rt.timing_param and values.get(rt.timing_param) == "after_missed":
            lines.append(f"- {rt.label.capitalize()}s cover only {missed} already recorded: never the {step} in "
                         f"progress (file for it from the next {step}), and {_a(request)} listing one is refused"
                         + ("" if values.get(rt.partial_at_submit_param) else " whole") + ".")
            for last in last_steps:
                lines.append(f"- So a miss in {step} {last} can't be excused before the check.")
    return lines
