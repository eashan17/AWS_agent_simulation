"""What the screens need to know about a template (slice U0): its display words, calendar labels,
people, roles and parameter specs, read from the template file, so the UI never hard-codes one
template's words. Read-only; no model call.
"""

from typing import Any

from rulestorm.core.model import TEMPLATES_DIR, Template


class TemplateNotFound(LookupError):
    pass


def shipped_ids() -> list[str]:
    """Only the shipped template files can be named: an ID is never used as a path."""
    return sorted(path.stem for path in TEMPLATES_DIR.glob("*.json"))


def template_info(template_id: str) -> dict[str, Any]:
    from rulestorm.counterfactual import changeable
    from rulestorm.evidence import template_named

    if template_id not in shipped_ids():
        raise TemplateNotFound(template_id)
    t: Template = template_named(template_id)
    return {
        "id": t.id, "version": t.version, "ref": t.ref, "title": t.title, "scope": t.scope,
        "terms": t.terms,
        "calendar": t.calendar.model_dump(),
        "example_input": t.example_input.model_dump(),
        "roles": [{"id": r.id, "label": r.label, "llm": r.llm, "rules": list(r.rules)} for r in t.roles],
        "people": [{"id": p.id, "role": p.role, "label": p.label} for p in t.people],
        "attributes": [a.model_dump() for a in t.attributes],
        "parameters": [p.model_dump(include={"name", "kind", "type", "min", "max", "choices", "attribute",
                                             "max_length", "description"}) for p in t.parameters],
        "disruption_kinds": [{"id": d.id, "label": d.label, "kind": d.kind} for d in t.disruptions],
        "checks": [{"id": c.id, "label": c.label, "comparison": c.comparison,
                    "ladder": [s.outcome for s in c.ladder] if c.ladder else None} for c in t.checks],
        "counterfactual_parameters": [p.name for p in changeable(t)],
    }
