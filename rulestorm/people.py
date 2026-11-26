"""One person in a run (slice M7c): who they are, their limits, and every decision with the state
it was made from. The brief's agent inspector ("goals, constraints, memory and recent decisions")
reads it. Rules over the run's own events and the blueprint, no model call, no engine rebuilt."""

from typing import Any

from pydantic import BaseModel, Field

from rulestorm.core.model import Template


class PersonDecision(BaseModel):
    event_id: str
    period: int
    step: int | None
    triggers: list[str] = Field(description="the event IDs that triggered the decision")
    actions: list[dict[str, Any]]
    reason: str
    strategy: str | None = None
    error: str | None = None
    state: dict[str, Any] | None = Field(None, description="the person's own state the decision was made from")
    state_lines: list[str] = Field(default_factory=list, description="that state in the template's words")


class PersonView(BaseModel):
    run_id: str
    person: str
    role: str
    label: str | None = None
    profile: dict[str, Any] | None = None
    attributes: dict[str, int] = Field(default_factory=dict, description="slack, obligation limits and the like")
    decisions: list[PersonDecision]


def person_view(template: Template, values: dict[str, Any], events: list[dict], run_id: str,
                person: str) -> PersonView:
    """Raises LookupError for someone the template doesn't have."""
    from rulestorm.core.margins import PersonState

    who = next((p for p in template.people if p.id == person), None)
    if who is None:
        raise LookupError(f"no person '{person}' in {template.ref}")
    profiles = next((values.get(p.name) or {} for p in template.parameters if p.type == "profiles"), {})
    attributes = {}
    for p in template.parameters:
        if p.type == "attribute":
            value = (values.get(p.name) or p.default or {}).get(person)
            if value is not None:
                attributes[p.attribute] = value
    decisions = []
    for e in events:
        if e["type"] != "decision" or e["actor"] != person:
            continue
        q = e["payload"]
        state = q.get("state")
        decisions.append(PersonDecision(
            event_id=e["event_id"], period=e["period"], step=e.get("step"), triggers=e.get("caused_by") or [],
            actions=q.get("proposals") or [], reason=q.get("reason") or "", strategy=q.get("strategy"),
            error=q.get("error"), state=state,
            state_lines=PersonState.model_validate(state).lines(template) if state else []))
    return PersonView(run_id=run_id, person=person, role=who.role, label=who.label, profile=profiles.get(person),
                      attributes=attributes, decisions=decisions)
