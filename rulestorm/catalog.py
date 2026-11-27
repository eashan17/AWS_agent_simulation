"""What the screens need to know about a template (slice U0): its display words, calendar labels,
people, roles and parameter specs, read from the template file, so the UI never hard-codes one
template's words. Read-only; no model call.

Slice M8b adds `readings`: how RuleStorm reads the rule (how an excused occurrence counts, what
each disruption kind is, how a request is decided, what counts as exceptional, proof, the filing
deadline), each with the parameter that sets it, if any, so the policymaker can see the reading
and change it in a what-if or a policy version.
"""

from typing import Any

from rulestorm.core.model import TEMPLATES_DIR, Parameter, Template


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
        "readings": readings(t),
    }


def _setting(t: Template, name: str | None) -> dict[str, Any] | None:
    """A reading's parameter: its name, default and allowed values, with a sentence per value."""
    p: Parameter | None = next((p for p in t.parameters if p.name == name), None) if name else None
    if p is None:
        return None
    return {"parameter": p.name, "type": p.type, "default": p.default, "choices": p.choices,
            "min": p.min, "max": p.max, "sentences": p.sentences, "stated_only": p.stated_only,
            "description": p.description}


def readings(t: Template) -> dict[str, Any]:
    """How RuleStorm reads the rule (slice M8b). Template readings (routine, leaves_proof, an
    obligation) are fixed by the template; the rest name the parameter that sets them, listed in
    `parameters`. The values shown are the defaults: a blueprint's own values are on its record."""
    roles = {r.id: r.label for r in t.roles}
    counts = [{"count": c.id, "label": c.label, "excluded": list(c.exclude), "excused": _setting(t, c.excused_param)}
              for c in t.counts]
    kinds = [{"id": k.id, "label": k.label, "kind": k.kind, "duty": k.duty, "routine": k.routine,
              "leaves_proof": k.leaves_proof,
              "obligation": k.obligation.model_dump() if k.obligation else None} for k in t.disruptions]
    requests = [{"id": rt.id, "label": rt.label, "covers": rt.covers, "decided_by": rt.decided_by,
                 "decider": roles.get(rt.handled_by, rt.handled_by),
                 "endorsed_by": roles.get(rt.endorsed_by) if rt.endorsed_by else None,
                 "decision_rule": _setting(t, rt.decision_rule_param),
                 "exceptional": _setting(t, rt.exceptional_param),
                 "proof": _setting(t, rt.proof_param),
                 "deadline": _setting(t, rt.deadline_param)} for rt in t.request_types]
    named = [c["excused"] for c in counts] + [r[k] for r in requests
                                              for k in ("decision_rule", "exceptional", "proof", "deadline")]
    return {"counts": counts, "disruption_kinds": kinds, "request_types": requests,
            "template_readings": ["routine", "leaves_proof", "obligation"],
            "parameters": sorted({s["parameter"] for s in named if s})}
