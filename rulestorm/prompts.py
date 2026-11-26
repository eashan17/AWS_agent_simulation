"""Each LLM person's prompt, generated from the template, the blueprint's values and their context.

No domain word lives here: the setting, the labels, each parameter's sentence and each action's
parameter hints come from the template (rulestorm/templates/*.json). The layout keeps every line
the real runs of slice 6b needed (the slack line, the missed occurrences no request covers, the
outcomes of the person's last actions), checked character for character by tests/test_prompts.py
against prompts frozen from the old engine, plus a "Request rules" block rendered from the
request parameters' sentences, and a "How the rules work" block (rulestorm/rulebook.py, 26 Nov):
when each check runs, that its result is final, how many misses fail it, what counts and how
requests are queued before it, so every person knows the rules the engine applies to them.

A role's prompt lists only its own allowed actions. Rules (recording, queue processing,
checks) are never actions, so they are never offered.
"""

import json
from collections.abc import Sequence
from typing import Any

from rulestorm.core.model import REQUEST_OUTCOMES, Action, Parameter, Template
from rulestorm.core.term import DecisionContext
from rulestorm.rulebook import rule_lines


def render_prompt(template: Template, values: dict[str, Any], c: DecisionContext,
                  memory: Sequence[str] = ()) -> str:
    cal, terms = template.calendar, template.terms
    lines = [
        f"You are the {c.role} agent `{c.person}` in {terms.get('setting', 'a simulated term')} "
        f"({cal.period_label} {c.period}, {cal.step_label} {c.step}). "
        "Decide what you do now, as this person would.",
        f"Now: {cal.step_label} {c.step} ({cal.period_label} {c.period}). Each event below names the "
        f"{cal.step_label} it is about, if it is about one.",
        "",
        "Who you are (from the approved blueprint):",
    ]
    profile = c.profile or {}
    lines.append(f"- description: {profile['description']}" if profile.get("description") else "- description: (none)")
    for field in ("goals", "constraints"):
        if profile.get(field):
            lines.append(f"- {field}: " + "; ".join(profile[field]))
    for p in section(template, "you"):
        value = c.attributes.get(p.attribute) if p.type == "attribute" else values.get(p.name)
        if value is not None:
            lines.append("- " + sentence(p, value, values))

    lines += ["", "Policy:", *("- " + sentence(p, values[p.name], values) for p in section(template, "policy"))]
    rules = [sentence(p, values[p.name], values) for p in section(template, "request_rules") if p.name in values]
    if rules:
        lines += ["", "Request rules:", *(f"- {r}" for r in rules)]
    how = rule_lines(template, values)
    for rt_id, capacity in c.capacity_now.items():
        rt = next(r for r in template.request_types if r.id == rt_id)
        handler = next(r for r in template.roles if r.id == rt.handled_by).label.lower()
        normal = values.get(rt.capacity_param)
        how.append(f"- This {cal.period_label} the {handler} can decide at most {capacity} {rt.label}s"
                   + (f" (normally {normal})." if normal is not None else "."))
    if how:
        lines += ["", "How the rules work (the engine applies these exactly):", *how]

    lines += [
        "",
        "What just happened (the events that triggered you):",
        *(f"- {t.event_id} {cal.period_label} {t.period}"
          + (f" {cal.step_label} {t.step}" if t.step is not None else "")
          + f" {t.type}: {json.dumps(t.payload, ensure_ascii=False)}"
          + (f" changed {json.dumps(t.state_change, ensure_ascii=False)}" if t.state_change else "")
          for t in c.triggers),
    ]
    if c.situation:  # slice M4: after the trigger list, so the frozen lines above stay as they are
        lines += ["", f"Your situation now ({cal.step_label} {c.step}):", *(f"- {x}" for x in c.situation)]
    request_word = terms.get("request", "request")
    if c.counts:
        for count_id, result in c.counts.items():
            label = next(x.label for x in template.counts if x.id == count_id)
            lines.append(f"Your {label} so far: {result.text()}; pending requests: "
                         f"{', '.join(result.pending) or 'none'}")
        missed = terms.get("missed_plural", "missed occurrences")
        lines.append(f"Your recorded {missed} that no {request_word} covers: "
                     f"{', '.join(f'{cal.step_label} {n}' for n in c.uncovered_missed) or 'none'}")
        if c.own_requests:
            lines.append(f"Your {request_word}s (each covers only the {cal.step_label}s listed): "
                         + "; ".join(own_request(template, r) for r in c.own_requests))
    elif c.pending_requests:
        lines.append(f"Pending {request_word}s: {', '.join(c.pending_requests)}")
    if c.awaiting_consent:
        lines += ["", f"{request_word.capitalize()}s waiting for your consent:",
                  *(request_line(template, r) for r in c.awaiting_consent)]
    if c.offered_requests:
        lines += ["", *decision_lines(template, c)]
    if c.last_outcomes:
        lines += ["", "What happened to the actions of your last decision:", *(f"- {o}" for o in c.last_outcomes)]
    if memory:
        lines += ["", "Your recent decisions:", *(f"- {m}" for m in memory)]

    role = next(r for r in template.roles if r.id == c.role)
    actions = {a.id: a for a in template.actions}
    offered_actions = sorted(a for a in role.actions if a not in c.unavailable_actions)
    lines += [
        "",
        f"Actions you may propose (0 to {c.action_limit()}; an empty list means you do nothing):",
        *(f"- {a}: params {action_params(actions[a])}" for a in offered_actions),
        "First give a short reason and your current strategy, then the actions that carry them out. "
        "Each action is {\"action\": <name>, \"params\": {...}}.",
    ]
    return "\n".join(lines)


def decision_lines(template: Template, c: DecisionContext) -> list[str]:
    """For an LLM decider at an open slot: the requests offered (within capacity, first come
    first served) and the outcomes the engine accepts."""
    cal, word = template.calendar, template.terms.get("request", "request")
    lines = [f"{word.capitalize()}s waiting for your decision now, first come first served "
             f"(you can decide at most {c.decision_capacity} now; the rest wait):"]
    lines += [request_line(template, r) for r in c.offered_requests]
    lines.append(f"Allowed outcomes: {', '.join(REQUEST_OUTCOMES)}. "
                 + (f"You may approve only some {cal.step_label}s of a {word}."
                    if c.partial_decisions else f"Approve or reject each {word} whole."))
    return lines


def own_request(template: Template, r: dict[str, Any]) -> str:
    """`R1 (night 12): approved`, `R2 (nights 8, 9): approved for night 8 only`, `R3 (night 9): rejected
    (consent refused)`, `R4 (night 14): pending, awaiting consent`."""
    step = template.calendar.step_label

    def steps(ns: list[int]) -> str:
        return f"{step}{'s' if len(ns) > 1 else ''} {', '.join(map(str, ns))}"

    status = r["status"]
    if status == "approved" and r["approved_steps"] != r["steps"]:
        status = f"approved for {steps(r['approved_steps'])} only"
    elif status == "rejected" and r["endorsement"] == "refused":
        status = "rejected (consent refused)"
    elif status == "pending" and r["endorsement"] == "awaiting":
        status = "pending, awaiting consent"
    return f"{r['request_id']} ({steps(r['steps'])}): {status}"


def request_line(template: Template, r: dict[str, Any]) -> str:
    cal = template.calendar
    facts = r.get("facts") or {}
    steps = ", ".join(f"{cal.step_label} {s}" + (f" ({facts.get(s) or facts.get(str(s))})"
                                                  if facts.get(s) or facts.get(str(s)) else "")
                      for s in r["steps"])
    reason = f'; reason: "{r["reason"]}"' if r["reason"] else ""
    return f"- {r['request_id']} from {r['person']}: {steps} (filed {cal.period_label} {r['filed_period']}){reason}"


def section(template: Template, name: str) -> list[Parameter]:
    return [p for p in template.parameters if p.prompt_section == name]


def sentence(p: Parameter, value: Any, values: dict[str, Any]) -> str:
    """A parameter's sentence for this value; {name} placeholders take other parameters' values."""
    if p.sentences is not None:
        key = str(value).lower() if isinstance(value, bool) else str(value)
        return p.sentences[key].format(value=value, **values)
    return (p.sentence or "{value}").format(value=value, **values)


def action_params(action: Action) -> str:
    """`{"name": <hint>, ...}`, then `; optional "name": <hint>` for each optional parameter, which
    says that leaving it out keeps things as they are (a model once sent 0 as a placeholder)."""
    required = [p for p in action.params if p.required]
    text = "{" + ", ".join(f'"{p.name}": {p.hint or "<" + p.type + ">"}' for p in required) + "}"
    for p in action.params:
        if not p.required:
            omit = p.omit_means or "leave it out to keep yours as it is"
            text += f'; optional "{p.name}": {p.hint or "<" + p.type + ">"} ({omit})'
    return text
