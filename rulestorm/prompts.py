"""Each LLM person's prompt, generated from the template, the blueprint's values and their context.

No domain word lives here: the setting, the labels, each parameter's sentence and each action's
parameter hints come from the template (rulestorm/templates/*.json). The layout keeps every line
the real runs of slice 6b needed (the slack line, the missed occurrences no request covers, the
outcomes of the person's last actions), checked character for character by tests/test_prompts.py
against prompts frozen from the old engine, plus a "Request rules" block rendered from the
request parameters' sentences.

A role's prompt lists only its own allowed actions. Rules (recording, queue processing,
checks) are never actions, so they are never offered.
"""

import json
from collections.abc import Sequence
from typing import Any

from rulestorm.core.model import Action, Parameter, Template
from rulestorm.core.term import DecisionContext


def render_prompt(template: Template, values: dict[str, Any], c: DecisionContext,
                  memory: Sequence[str] = ()) -> str:
    cal, terms = template.calendar, template.terms
    lines = [
        f"You are the {c.role} agent `{c.person}` in {terms.get('setting', 'a simulated term')} "
        f"({cal.period_label} {c.period}, {cal.step_label} {c.step}). "
        "Decide what you do now, as this person would.",
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

    lines += [
        "",
        "What just happened (the events that triggered you):",
        *(f"- {t.event_id} {cal.period_label} {t.period} {t.type}: {json.dumps(t.payload, ensure_ascii=False)}"
          + (f" changed {json.dumps(t.state_change, ensure_ascii=False)}" if t.state_change else "")
          for t in c.triggers),
    ]
    request_word = terms.get("request", "request")
    if c.counts:
        for count_id, result in c.counts.items():
            label = next(x.label for x in template.counts if x.id == count_id)
            lines.append(f"Your {label} so far: {result.text()}; pending requests: "
                         f"{', '.join(result.pending) or 'none'}")
        missed = terms.get("missed_plural", "missed occurrences")
        lines.append(f"Your recorded {missed} that no {request_word} covers: "
                     f"{', '.join(f'{cal.step_label} {n}' for n in c.uncovered_missed) or 'none'}")
    elif c.pending_requests:
        lines.append(f"Pending {request_word}s: {', '.join(c.pending_requests)}")
    if c.last_outcomes:
        lines += ["", "What happened to the actions of your last decision:", *(f"- {o}" for o in c.last_outcomes)]
    if memory:
        lines += ["", "Your recent decisions:", *(f"- {m}" for m in memory)]

    role = next(r for r in template.roles if r.id == c.role)
    actions = {a.id: a for a in template.actions}
    lines += [
        "",
        "Actions you may propose (0 to 3; an empty list means you do nothing):",
        *(f"- {a}: params {action_params(actions[a])}" for a in sorted(role.actions)),
        "Each action is {\"action\": <name>, \"params\": {...}}. "
        "Give a short reason and your current strategy.",
    ]
    return "\n".join(lines)


def section(template: Template, name: str) -> list[Parameter]:
    return [p for p in template.parameters if p.prompt_section == name]


def sentence(p: Parameter, value: Any, values: dict[str, Any]) -> str:
    """A parameter's sentence for this value; {name} placeholders take other parameters' values."""
    if p.sentences is not None:
        key = str(value).lower() if isinstance(value, bool) else str(value)
        return p.sentences[key].format(value=value, **values)
    return (p.sentence or "{value}").format(value=value, **values)


def action_params(action: Action) -> str:
    """`{"name": <hint>, ...}`, then `; optional "name": <hint>` for each optional parameter."""
    required = [p for p in action.params if p.required]
    text = "{" + ", ".join(f'"{p.name}": {p.hint or "<" + p.type + ">"}' for p in required) + "}"
    for p in action.params:
        if not p.required:
            text += f'; optional "{p.name}": {p.hint or "<" + p.type + ">"}'
    return text
