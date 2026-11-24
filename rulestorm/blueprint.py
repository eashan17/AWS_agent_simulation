"""A blueprint = template + values. The values model and the fill prompt come from the template.

`values_model(template)` builds a Pydantic model with one field per parameter spec (ranges,
choices, people and disruption kinds all read from the template), then checks the values
against the engine itself, so a disruption that names an unknown person, or hits someone who
doesn't owe its duty, makes the fill invalid and is retried with the error.

Every value is labelled a fact (stated in the user's text) or an assumption (proposed by the
AI). A label covers one parameter or a whole section (policy, environment, people), so the
lists stay short.
"""

from functools import lru_cache
from typing import Annotated, Any, ClassVar, Literal

from pydantic import BaseModel, Field, create_model, model_validator

from rulestorm.core.engine import Engine
from rulestorm.core.model import Parameter, Template

SECTIONS = ("policy", "environment", "people")
MAX_LABELS = 8
MAX_DISRUPTIONS = 10


# Kept short on purpose: with 8 people, profiles were 43% of a curfew fill's output and pushed it
# to 40-44 s, leaving no room for a retry in the 55 s budget (24 Nov, after slice L9d).
MAX_GOALS = 2
MAX_CONSTRAINTS = 2


class PersonProfile(BaseModel):
    description: str = Field(min_length=1, max_length=200, description="who this person is, in this setting")
    goals: list[str] = Field(min_length=1, max_length=MAX_GOALS, description="what this person wants this term")
    constraints: list[str] = Field(default_factory=list, max_length=MAX_CONSTRAINTS, description="what limits them")


class Label(BaseModel):
    field: str = Field(min_length=1, max_length=80,
                       description="a value's name, or a whole section: policy, environment or people")
    statement: str = Field(min_length=1, max_length=200)


class TemplateBlueprint(BaseModel):
    """What is stored and frozen on approval."""

    template_id: str
    template_version: int
    values: dict[str, Any]
    facts: list[Label]
    assumptions: list[Label]

    def label_for(self, template: Template, name: str) -> tuple[str, Label] | None:
        """The label covering a value: its own label first, else its section's."""
        kind = next(p.kind for p in template.parameters if p.name == name)
        for field in (name, kind):
            for tag, labels in (("fact", self.facts), ("assumption", self.assumptions)):
                for label in labels:
                    if label.field == field:
                        return tag, label
        return None


# --- the values model ---------------------------------------------------------------------------


class ValuesBase(BaseModel):
    template: ClassVar[Template]

    @model_validator(mode="after")
    def _engine_accepts(self) -> "ValuesBase":
        try:
            Engine(self.template, self.model_dump())
        except (KeyError, ValueError) as exc:
            raise ValueError(str(exc).strip("'\"")) from exc
        return self


def _field(t: Template, p: Parameter) -> tuple[Any, Any]:
    info = {"description": p.description} if p.description else {}
    if p.type == "int":
        return int, Field(ge=p.min, le=p.max, **info)
    if p.type == "bool":
        return bool, Field(**info)
    if p.type == "choice":
        return Literal[tuple(p.choices)], Field(**info)
    if p.type == "text":
        return str, Field(min_length=1, max_length=p.max_length, **info)
    if p.type == "attribute":
        attribute = next(a for a in t.attributes if a.id == p.attribute)
        people = [x.id for x in t.people if x.role == attribute.role]
        model = create_model(f"{p.name}_by_person",
                             **{pid: (int, Field(ge=attribute.min, le=attribute.max)) for pid in people})
        return model, Field(**info)
    if p.type == "profiles":
        llm_roles = {r.id for r in t.roles if r.llm}
        model = create_model("profiles_by_person",
                             **{x.id: (PersonProfile, ...) for x in t.people if x.role in llm_roles})
        return model, Field(**info)
    if p.type == "disruptions":
        people = Literal[tuple(x.id for x in t.people)]
        step = Annotated[int, Field(ge=1, le=t.calendar.steps_per_period)]
        model = create_model(
            "Disruption",
            kind=(Literal[tuple(d.id for d in t.disruptions)], ...),
            period=(int, Field(ge=1, le=t.calendar.periods)),
            steps=(list[step], Field(default_factory=list, description="positions within the period")),
            people=(list[people], Field(default_factory=list)),
            delay=(int, Field(0, ge=0, le=1000)),
            capacity=(int | None, Field(None, ge=0, le=1000)),
            description=(str, Field(min_length=1, max_length=200)),
        )
        low = 1 if t.disruptions else 0
        return list[model], Field(min_length=low, max_length=MAX_DISRUPTIONS, **info)
    raise ValueError(f"no values-model field for parameter type {p.type!r}")


@lru_cache(maxsize=None)
def _values_model(ref: str, template_json: str) -> type[ValuesBase]:
    t = Template.model_validate_json(template_json)
    model = create_model(f"Values_{t.id}", __base__=ValuesBase, **{p.name: _field(t, p) for p in t.parameters})
    model.template = t
    return model


def values_model(template: Template) -> type[ValuesBase]:
    return _values_model(template.ref, template.model_dump_json())


class FillBase(BaseModel):
    template: ClassVar[Template]

    @model_validator(mode="after")
    def _every_value_labelled(self) -> "FillBase":
        names = {p.name: p.kind for p in self.template.parameters}
        labels = [*self.facts, *self.assumptions]
        unknown = sorted({x.field for x in labels} - set(names) - set(SECTIONS))
        if unknown:
            raise ValueError(f"label fields must be a value's name or a section ({', '.join(SECTIONS)}); "
                             f"unknown: {', '.join(unknown)}")
        covered = {x.field for x in labels}
        missing = [n for n, kind in names.items() if n not in covered and kind not in covered]
        if missing:
            raise ValueError(f"label these in facts or assumptions (or label their section): {', '.join(missing)}")
        return self


def fill_schema(template: Template) -> type[FillBase]:
    model = create_model(
        f"Fill_{template.id}", __base__=FillBase,
        values=(values_model(template), ...),
        facts=(list[Label], Field(min_length=1, max_length=MAX_LABELS, description="values stated in the user's text")),
        assumptions=(list[Label], Field(min_length=1, max_length=MAX_LABELS, description="values the AI proposed")),
    )
    model.template = template
    return model


def to_blueprint(template: Template, fill: FillBase) -> TemplateBlueprint:
    return TemplateBlueprint(template_id=template.id, template_version=template.version,
                             values=fill.values.model_dump(), facts=fill.facts, assumptions=fill.assumptions)


# --- the fill prompt ----------------------------------------------------------------------------


def fill_prompt(template: Template, text: str, purpose: str, environment: str) -> str:
    t, cal = template, template.calendar
    roles = {r.id: r for r in t.roles}
    people = "\n".join(f"- {x.id} ({roles[x.role].label}{': ' + x.label if x.label else ''})" for x in t.people)
    lines = [
        f'You turn an institution\'s policy into the values of a policy simulation: "{t.title}".',
        f"The simulated term has {cal.periods} {cal.period_label}s with {cal.steps_per_period} "
        f"{cal.step_label}s each.",
        f"People (fixed by the simulation; you write their profiles):\n{people}",
        "",
        "Values to fill (name [section]: meaning; allowed values):",
        *(f"- {p.name} [{p.kind}]: {_meaning(p)}; {_allowed(t, p)}" for p in t.parameters),
        "",
        "Use values stated in the user's text and list them under facts. Where the text gives no "
        "value, including policy rules it is silent on (for example when a request may be filed), "
        "propose a plausible one and list it under assumptions. Each label's `field` is a value's "
        f"name, or a whole section ({', '.join(SECTIONS)}) to cover all its values at once; every "
        f"value must be covered. At most {MAX_LABELS} facts and {MAX_LABELS} assumptions, statements "
        "under 15 words. Make each person distinct.",
        "",
        f"Policy:\n{text}\n\nPurpose:\n{purpose}\n\nEnvironment:\n{environment}",
    ]
    return "\n".join(lines)


def _meaning(p: Parameter) -> str:
    return p.description or p.sentence or p.name


def _allowed(t: Template, p: Parameter) -> str:
    if p.type == "int":
        return f"a whole number {p.min}-{p.max}"
    if p.type == "bool":
        if p.sentences:
            return f"true ({p.sentences['true']}) or false ({p.sentences['false']})"
        return "true or false"
    if p.type == "choice":
        return "one of " + ", ".join(f"{c} ({p.sentences[c]})" if p.sentences else c for c in p.choices)
    if p.type == "text":
        return f"text under {p.max_length} characters"
    if p.type == "attribute":
        a = next(x for x in t.attributes if x.id == p.attribute)
        people = [x.id for x in t.people if x.role == a.role]
        return f"for each of {', '.join(people)}: {a.label}, a whole number {a.min}-{a.max}"
    if p.type == "profiles":
        llm_roles = {r.id for r in t.roles if r.llm}
        people = [x.id for x in t.people if x.role in llm_roles]
        return (f"for each of {', '.join(people)}: a description (under 12 words), 1-{MAX_GOALS} goals "
                f"and 0-{MAX_CONSTRAINTS} constraints (under 6 words each), drawn from the user's text where it says")
    if p.type == "disruptions":
        kinds = []
        for d in t.disruptions:
            if d.kind == "obstacle":
                duty = next(x for x in t.duties if x.id == d.duty)
                attribute = next((a for a in t.attributes if a.id == duty.obstacle_attribute), None)
                unit = f", in the same unit as {attribute.label}" if attribute else ""
                kinds.append(f"{d.id} ({d.label}: set period, steps, the people it hits (only people who "
                             f"must {duty.label}) and delay{unit})")
            elif d.kind == "capacity":
                rt = next(x for x in t.request_types if x.id == d.request_type)
                kinds.append(f"{d.id} ({d.label}: set period and capacity, the {rt.label}s that can be "
                             f"processed that {t.calendar.period_label})")
            else:
                kinds.append(f"{d.id} ({d.label}: set period and steps)")
        return (f"a list of 1-{MAX_DISRUPTIONS}, each with a short description; `period` is the "
                f"{t.calendar.period_label} number and steps are positions within "
                f"the {t.calendar.period_label} (1-{t.calendar.steps_per_period}). Kinds: " + "; ".join(kinds))
    return p.type
