"""The building-block schema and the template check.

A template describes one rule world as data: who exists, what each role may do, what is
owed, requested, counted and checked, and which values the blueprint must fill. It may use
only the building blocks below (docs/ARCHITECTURE.md, The building blocks). Anything outside
them needs new engine code, by design.

`check_template` is what makes a template safe for the engine to trust: the schema, then
every reference between blocks (an action's duty, a check's count, a parameter name), and the
fixed libraries of effects, preconditions, rules, decision rules and triggers. The dry run with
a scripted decider joins it in slice L4.
"""

import json
import string
from collections import Counter
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

# --- fixed libraries: the only words a template may use ------------------------------------

Rule = Literal["recorder", "queue_processor", "checker"]
EffectKind = Literal[
    "plan_meet", "plan_miss", "set_attribute", "file_request", "endorse", "decide_request",
    "message", "respond", "correct_record", "cancel_occurrence",
]
Precondition = Literal["own_occurrence", "occurrence_recorded", "occurrence_not_yet", "not_already_covered"]
DecisionRule = Literal["approve_if_covered_missed", "approve_if_filed_before_occurrence", "approve_all"]
RequestTiming = Literal["after_missed", "in_advance"]
TriggerKind = Literal[
    "obstacle_hit",            # an obstacle hits a person
    "own_duty_missed",         # a person's own duty is recorded missed
    "count_near_threshold",    # a count comes within `within` of its check's threshold
    "request_pending",         # a request has been pending >= `periods` periods
    "many_missed",             # >= `min_people` people missed in one step
    "endorsement_awaiting",    # a request awaits its endorsed_by person's consent
    "decision_awaiting",       # a request awaits an LLM decision at its processing slot
    "escalation_outcome",      # an escalation outcome reaches its listed roles
]
DisruptionKindName = Literal["obstacle", "capacity", "cancellation"]
CountExclusion = Literal["approved_request", "cancelled"]
ParameterKind = Literal["policy", "environment", "people"]
ParameterType = Literal["int", "bool", "choice", "text", "attribute", "profiles", "disruptions"]
PromptSection = Literal["policy", "request_rules", "you"]

# Which reference each effect needs (a field on the Effect).
EFFECT_NEEDS: dict[str, str | None] = {
    "plan_meet": "duty", "plan_miss": "duty", "correct_record": "duty", "cancel_occurrence": "duty",
    "set_attribute": "attribute",
    "file_request": "request_type", "endorse": "request_type", "decide_request": "request_type",
    "message": "to", "respond": None,
}
# Effects about particular occurrences of a duty: the action must name the step(s).
OCCURRENCE_EFFECTS = {"plan_meet", "plan_miss", "correct_record", "cancel_occurrence", "file_request"}


class Block(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- building blocks --------------------------------------------------------------------------


class Calendar(Block):
    periods: int = Field(ge=1, le=52)
    steps_per_period: int = Field(ge=1, le=14)
    period_label: str = Field(min_length=1)
    step_label: str = Field(min_length=1)


class Role(Block):
    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    llm: bool
    rules: list[Rule] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list, description="action IDs this role may take")


class Person(Block):
    """Who exists. Labels and profiles come from the blueprint."""

    id: str = Field(min_length=1)
    role: str


class Attribute(Block):
    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    role: str
    min: int
    max: int


class Duty(Block):
    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    owed_by: str
    recorded_by: str
    obstacle_attribute: str | None = Field(None, description="a delay above this attribute means missed")


class ActionParam(Block):
    name: str = Field(min_length=1)
    # step / step_list name the occurrence(s) an action is about; person names a target person
    type: Literal["int", "str", "bool", "step", "step_list", "person"]
    required: bool = True
    hint: str = Field("", description="how the value is described to an LLM person, e.g. <current session>")


class Effect(Block):
    kind: EffectKind
    duty: str | None = None
    attribute: str | None = None
    request_type: str | None = None
    to: str | None = Field(None, description="message only: the role it goes to")


class Action(Block):
    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    params: list[ActionParam] = Field(default_factory=list)
    effects: list[Effect] = Field(min_length=1)
    preconditions: list[Precondition] = Field(default_factory=list)


class RequestType(Block):
    """Fields named `*_param` hold a parameter name: the blueprint fills the value."""

    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    filed_by: str
    covers: str
    handled_by: str
    processed: Literal["each_step", "period_end"]
    endorsed_by: str | None = None
    decided_by: Literal["rule", "llm"]
    decision_rule_param: str | None = None
    timing_param: str
    partial_at_submit_param: str
    partial_at_decide_param: str
    capacity_param: str


class Count(Block):
    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    kind: Literal["rate", "tally"]
    duty: str
    exclude: list[CountExclusion] = Field(default_factory=list)


class LadderStep(Block):
    threshold_param: str
    outcome: str = Field(min_length=1)
    notifies: list[str] = Field(default_factory=list)


class Check(Block):
    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    run_by: str
    count: str
    comparison: Literal[">=", "<="]
    threshold_param: str | None = None
    at_param: str | None = Field(None, description="the period the single-threshold check runs in")
    ladder: list[LadderStep] | None = None

    @model_validator(mode="after")
    def _one_form(self) -> "Check":
        single = self.threshold_param is not None or self.at_param is not None
        if single == (self.ladder is not None):
            raise ValueError("a check has either threshold_param and at_param, or a ladder, not both")
        if single and (self.threshold_param is None or self.at_param is None):
            raise ValueError("a single-threshold check needs both threshold_param and at_param")
        return self


class DisruptionKind(Block):
    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    kind: DisruptionKindName
    duty: str | None = Field(None, description="obstacle and cancellation: the duty it hits")
    request_type: str | None = Field(None, description="capacity: the queue it changes")


class Trigger(Block):
    kind: TriggerKind
    notifies: list[str] = Field(default_factory=list, description="roles told besides the person concerned")
    within: int | None = None
    periods: int | None = None
    min_people: int | None = None


class Parameter(Block):
    name: str = Field(min_length=1)
    kind: ParameterKind
    type: ParameterType
    min: int | None = None
    max: int | None = None
    choices: list[str] | None = None
    attribute: str | None = Field(None, description="type attribute: which attribute each person sets")
    max_length: int | None = Field(None, description="type text: longest allowed value")
    prompt_section: PromptSection | None = Field(None, description="where the value is shown to LLM people")
    sentence: str | None = Field(None, description="how the value reads in a prompt: {value} is replaced, "
                                                   "and {name} by another parameter's value")
    sentences: dict[str, str] | None = Field(None, description="choice/bool: one sentence per value")


class ExampleInput(Block):
    text: str = Field(min_length=1, max_length=2000)
    purpose: str = Field(min_length=1, max_length=2000)
    environment: str = Field(min_length=1, max_length=2000)


class Template(Block):
    id: str = Field(min_length=1)
    version: int = Field(ge=1)
    title: str = Field(min_length=1)
    scope: str = Field(min_length=1, description="one line: which policies this template can model")
    terms: dict[str, str] = Field(default_factory=dict, description="display words")
    example_input: ExampleInput
    calendar: Calendar
    roles: list[Role] = Field(min_length=1)
    people: list[Person] = Field(min_length=1)
    attributes: list[Attribute] = Field(default_factory=list)
    duties: list[Duty] = Field(min_length=1)
    actions: list[Action] = Field(default_factory=list)
    request_types: list[RequestType] = Field(default_factory=list)
    counts: list[Count] = Field(default_factory=list)
    checks: list[Check] = Field(default_factory=list)
    disruptions: list[DisruptionKind] = Field(default_factory=list)
    triggers: list[Trigger] = Field(default_factory=list)
    parameters: list[Parameter] = Field(min_length=1)

    @property
    def ref(self) -> str:
        return f"{self.id}@{self.version}"


# --- the template check -----------------------------------------------------------------------


class TemplateCheck(BaseModel):
    source: str
    valid: bool
    errors: list[str] = Field(default_factory=list)
    template: Template | None = None

    def lines(self) -> list[str]:
        if not self.valid:
            return [f"invalid: {error}" for error in self.errors]
        t = self.template
        return [
            f"{t.ref}: valid",
            f"roles {len(t.roles)}, people {len(t.people)}, duties {len(t.duties)}, "
            f"actions {len(t.actions)}, request types {len(t.request_types)}, "
            f"counts {len(t.counts)}, checks {len(t.checks)}",
            "parameters: " + ", ".join(p.name for p in t.parameters),
            "dry run: ok",
        ]


def template_path(name_or_path: str) -> Path:
    """A bare name (`attendance`) is a shipped template; anything else is a file path."""
    path = Path(name_or_path)
    if path.suffix == "" and path.parent == Path("."):
        return TEMPLATES_DIR / f"{name_or_path}.json"
    return path


def check_file(name_or_path: str) -> TemplateCheck:
    path = template_path(name_or_path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return TemplateCheck(source=str(path), valid=False, errors=[f"no template file at {path}"])
    except json.JSONDecodeError as exc:
        return TemplateCheck(source=str(path), valid=False, errors=[f"not valid JSON: {exc}"])
    return check_template(raw, source=str(path))


def load_template(name_or_path: str) -> Template:
    """The template, only if it passes the check."""
    result = check_file(name_or_path)
    if not result.valid:
        raise ValueError(f"template {name_or_path} is invalid: " + "; ".join(result.errors))
    return result.template


def check_template(raw: dict, source: str = "<data>") -> TemplateCheck:
    try:
        template = Template.model_validate(raw)
    except ValidationError as exc:
        errors = [f"{'.'.join(str(p) for p in e['loc']) or 'template'}: {e['msg']}" for e in exc.errors()]
        return TemplateCheck(source=source, valid=False, errors=errors)
    errors = _reference_errors(template)
    if not errors:  # the dry run needs sound references: a full term with a scripted decider
        from rulestorm.core.term import dry_run

        errors = dry_run(template)
    return TemplateCheck(source=source, valid=not errors, errors=errors, template=None if errors else template)


def _reference_errors(t: Template) -> list[str]:
    errors: list[str] = []

    def unique(kind: str, ids: list[str]) -> set[str]:
        for dup, n in Counter(ids).items():
            if n > 1:
                errors.append(f"{kind} id '{dup}' is used {n} times")
        return set(ids)

    roles = unique("role", [r.id for r in t.roles])
    people = unique("person", [p.id for p in t.people])
    attributes = unique("attribute", [a.id for a in t.attributes])
    duties = unique("duty", [d.id for d in t.duties])
    actions = unique("action", [a.id for a in t.actions])
    request_types = unique("request type", [r.id for r in t.request_types])
    counts = unique("count", [c.id for c in t.counts])
    unique("check", [c.id for c in t.checks])
    unique("disruption", [d.id for d in t.disruptions])
    params = {p.name: p for p in t.parameters}
    unique("parameter", [p.name for p in t.parameters])
    rules_of = {r.id: set(r.rules) for r in t.roles}

    def ref(owner: str, kind: str, value: str | None, known: set[str]) -> None:
        if value is not None and value not in known:
            errors.append(f"{owner} refers to unknown {kind} '{value}'")

    def param(owner: str, name: str | None, kinds: set[str] | None = None) -> None:
        if name is None:
            return
        if name not in params:
            errors.append(f"{owner} refers to unknown parameter '{name}'")
        elif kinds and params[name].kind not in kinds:
            errors.append(f"{owner} needs a parameter of kind {'/'.join(sorted(kinds))}, "
                          f"but '{name}' is {params[name].kind}")

    def has_rule(owner: str, role: str, rule: str) -> None:
        if role in rules_of and rule not in rules_of[role]:
            errors.append(f"{owner} needs role '{role}' to have the {rule} rule")

    # roles: rules are not actions, so only LLM roles take actions
    for role in t.roles:
        if not role.llm and role.actions:
            errors.append(f"role '{role.id}' is not an LLM role, so it cannot take actions")
        if not role.llm and not role.rules:
            errors.append(f"role '{role.id}' is neither an LLM role nor a rule")
        for action_id in role.actions:
            ref(f"role '{role.id}'", "action", action_id, actions)
    used = {a for r in t.roles for a in r.actions}
    for action in t.actions:
        if action.id not in used:
            errors.append(f"action '{action.id}' is not allowed to any role")

    for person in t.people:
        ref(f"person '{person.id}'", "role", person.role, roles)
    for attribute in t.attributes:
        ref(f"attribute '{attribute.id}'", "role", attribute.role, roles)
        if attribute.min > attribute.max:
            errors.append(f"attribute '{attribute.id}' has min above max")

    for duty in t.duties:
        owner = f"duty '{duty.id}'"
        ref(owner, "role", duty.owed_by, roles)
        ref(owner, "role", duty.recorded_by, roles)
        has_rule(owner, duty.recorded_by, "recorder")
        ref(owner, "attribute", duty.obstacle_attribute, attributes)

    for action in t.actions:
        owner = f"action '{action.id}'"
        for effect in action.effects:
            need = EFFECT_NEEDS[effect.kind]
            if need and getattr(effect, need) is None:
                errors.append(f"{owner}: effect {effect.kind} needs '{need}'")
            ref(owner, "duty", effect.duty, duties)
            ref(owner, "attribute", effect.attribute, attributes)
            ref(owner, "request type", effect.request_type, request_types)
            ref(owner, "role", effect.to, roles)
        for dup, n in Counter(p.name for p in action.params).items():
            if n > 1:
                errors.append(f"{owner} has parameter '{dup}' {n} times")
        types = Counter(p.type for p in action.params)
        kinds = {e.kind for e in action.effects}
        if kinds & OCCURRENCE_EFFECTS and types["step"] + types["step_list"] != 1:
            errors.append(f"{owner} needs exactly one step or step_list parameter")
        if "correct_record" in kinds and (types["person"] != 1 or types["bool"] != 1):
            errors.append(f"{owner}: correct_record needs one person and one bool parameter")
        if "set_attribute" in kinds:
            for effect in action.effects:
                if effect.attribute and effect.attribute not in {p.name for p in action.params}:
                    errors.append(f"{owner}: set_attribute needs a parameter named '{effect.attribute}'")

    for rt in t.request_types:
        owner = f"request type '{rt.id}'"
        for role in (rt.filed_by, rt.handled_by, rt.endorsed_by):
            ref(owner, "role", role, roles)
        ref(owner, "duty", rt.covers, duties)
        if rt.decided_by == "rule":
            has_rule(owner, rt.handled_by, "queue_processor")
            if rt.decision_rule_param is None:
                errors.append(f"{owner} is decided by rule, so it needs decision_rule_param")
        for name in (rt.decision_rule_param, rt.timing_param, rt.partial_at_submit_param, rt.partial_at_decide_param):
            param(owner, name, {"policy"})
        param(owner, rt.capacity_param, {"environment"})
        _choices_within(errors, params, rt.decision_rule_param, DecisionRule)
        _choices_within(errors, params, rt.timing_param, RequestTiming)

    for count in t.counts:
        ref(f"count '{count.id}'", "duty", count.duty, duties)

    for check in t.checks:
        owner = f"check '{check.id}'"
        ref(owner, "role", check.run_by, roles)
        has_rule(owner, check.run_by, "checker")
        ref(owner, "count", check.count, counts)
        param(owner, check.threshold_param, {"policy"})
        param(owner, check.at_param)
        for step in check.ladder or []:
            param(owner, step.threshold_param, {"policy"})
            for role in step.notifies:
                ref(owner, "role", role, roles)

    for d in t.disruptions:
        owner = f"disruption '{d.id}'"
        ref(owner, "duty", d.duty, duties)
        ref(owner, "request type", d.request_type, request_types)
        if d.kind in ("obstacle", "cancellation") and d.duty is None:
            errors.append(f"{owner}: a {d.kind} needs 'duty'")
        if d.kind == "capacity" and d.request_type is None:
            errors.append(f"{owner}: a capacity disruption needs 'request_type'")

    for i, trigger in enumerate(t.triggers, 1):
        for role in trigger.notifies:
            ref(f"trigger {i} ({trigger.kind})", "role", role, roles)

    for p in t.parameters:
        owner = f"parameter '{p.name}'"
        if p.type == "int" and (p.min is None or p.max is None or p.min > p.max):
            errors.append(f"{owner} is an int, so it needs min <= max")
        if p.type == "choice" and not p.choices:
            errors.append(f"{owner} is a choice, so it needs choices")
        if p.type == "attribute":
            if p.attribute is None:
                errors.append(f"{owner} is an attribute, so it needs 'attribute'")
            ref(owner, "attribute", p.attribute, attributes)
        if p.type == "text" and not p.max_length:
            errors.append(f"{owner} is text, so it needs max_length")
        errors.extend(_sentence_errors(p, params))

    return errors


def _choices_within(errors: list[str], params: dict[str, Parameter], name: str | None, allowed) -> None:
    p = params.get(name) if name else None
    if p is None:
        return
    known = set(allowed.__args__)
    if p.type != "choice" or not p.choices:
        errors.append(f"parameter '{name}' must be a choice from: {', '.join(sorted(known))}")
        return
    for choice in p.choices:
        if choice not in known:
            errors.append(f"parameter '{name}' has unknown choice '{choice}'")


def _sentence_errors(p: Parameter, params: dict[str, Parameter]) -> list[str]:
    owner = f"parameter '{p.name}'"
    errors = []
    if p.sentence is not None and p.sentences is not None:
        errors.append(f"{owner} has both sentence and sentences")
    if p.prompt_section and p.sentence is None and p.sentences is None:
        errors.append(f"{owner} is shown in the {p.prompt_section} section, so it needs a sentence")
    if p.sentences is not None:
        expected = set(p.choices or []) if p.type == "choice" else {"true", "false"} if p.type == "bool" else None
        if expected is None:
            errors.append(f"{owner}: only choice and bool parameters can have one sentence per value")
        elif set(p.sentences) != expected:
            errors.append(f"{owner}: sentences must cover exactly {', '.join(sorted(expected))}")
    for text in [p.sentence or "", *(p.sentences or {}).values()]:
        for _, field, _, _ in string.Formatter().parse(text):
            if field and field != "value" and field not in params:
                errors.append(f"{owner}: sentence refers to unknown parameter '{field}'")
    return errors


def shipped_templates() -> list[Template]:
    """Every template in rulestorm/templates/, in file-name order. All must pass the check."""
    return [load_template(path.stem) for path in sorted(TEMPLATES_DIR.glob("*.json"))]
