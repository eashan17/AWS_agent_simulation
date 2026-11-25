"""Correcting a blueprint before approval (slice 18).

The policymaker can change any single value (a number, a yes/no, a choice or a text) and any
person's own value (for attendance, a student's travel buffer) of a blueprint that is not yet
approved. Each new value is checked by the template's values model, and so by the engine, like
the AI's draft was. A corrected value becomes the policymaker's **fact** ("Corrected by you: ..."),
replacing whatever labelled it before. Lists (disruptions, profiles) aren't edited here. Once a
blueprint is approved it is frozen: the store refuses the change.
"""

import copy
from typing import Any

from pydantic import ValidationError

from rulestorm.blueprint import Label, TemplateBlueprint, values_model
from rulestorm.core.model import Parameter, load_template
from rulestorm.policy import BlueprintFrozen, BlueprintInvalid, BlueprintNotFound, BlueprintRecord

SINGLE = ("int", "bool", "choice", "text")
MAX_CHANGES = 30


class EditRefused(ValueError):
    """The asked-for change isn't allowed or doesn't pass the template's checks (HTTP 422)."""


def _statement(p: Parameter, old: Any, new: Any) -> str:
    if p.type == "text":
        return f"Corrected by you: {p.name} reworded"
    if p.type == "attribute":
        return "Corrected by you: " + ", ".join(f"{p.name} {person} {old.get(person)} -> {v}"
                                                for person, v in new.items() if old.get(person) != v)
    return f"Corrected by you: {p.name} {old} -> {new}"


def correct_values(store, blueprint_id: str, changes: dict[str, Any]) -> BlueprintRecord:
    """Applies the changes to an unapproved, valid blueprint and stores it. Raises BlueprintNotFound,
    BlueprintFrozen (approved), BlueprintInvalid (not valid) or EditRefused."""
    record = store.get_blueprint(blueprint_id)
    if record is None or record.blueprint is None:
        raise BlueprintNotFound(blueprint_id)
    if record.approved:
        raise BlueprintFrozen(blueprint_id)
    if record.status != "valid":
        raise BlueprintInvalid(blueprint_id)
    if not changes:
        raise EditRefused("no changes given")
    if len(changes) > MAX_CHANGES:
        raise EditRefused(f"at most {MAX_CHANGES} changes at once")
    template = load_template(record.blueprint.template_id)
    params = {p.name: p for p in template.parameters}
    bp = record.blueprint
    values = copy.deepcopy(bp.values)
    for name, value in changes.items():
        p = params.get(name)
        if p is None:
            raise EditRefused(f"{template.id} has no value {name}")
        if p.type == "attribute":
            if not isinstance(value, dict) or not value:
                raise EditRefused(f"{name} takes each person's value, e.g. {{\"<person>\": 20}}")
            unknown = set(value) - set(values[name])
            if unknown:
                raise EditRefused(f"{name} has no person {sorted(unknown)[0]}")
            values[name] = {**values[name], **value}
        elif p.type in SINGLE:
            if p.type == "int" and (isinstance(value, bool) or not isinstance(value, int)):
                raise EditRefused(f"{name} takes a whole number")
            if p.type == "bool" and not isinstance(value, bool):
                raise EditRefused(f"{name} takes true or false")
            if p.type in ("choice", "text") and not isinstance(value, str):
                raise EditRefused(f"{name} takes text")
            values[name] = value
        else:
            raise EditRefused(f"{name} is a list ({p.type}); it isn't editable here")
    try:
        values = values_model(template).model_validate(values).model_dump()
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(x) for x in first["loc"])
        raise EditRefused(f"{where}: {first['msg']}")
    changed = [n for n in changes if values[n] != bp.values[n]]
    if not changed:
        raise EditRefused("nothing changed: every value is already as given")
    names = set(changed)
    new = TemplateBlueprint(
        template_id=bp.template_id, template_version=bp.template_version, values=values,
        facts=[x for x in bp.facts if x.field not in names]
        + [Label(field=n, statement=_statement(params[n], bp.values[n], values[n])[:200]) for n in changed],
        assumptions=[x for x in bp.assumptions if x.field not in names],
    )
    return store.update_blueprint(blueprint_id, new)
