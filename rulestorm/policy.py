"""Policy input, the Blueprint schema and `interpret` (policy text -> checked Blueprint).

`interpret` makes two model calls, always in this order, sharing one 55 s wall-clock budget:
1. pick: the policy texts plus every template's scope line -> a template ID, or "none" with a
   reason (`status: out_of_scope`, and no fill call);
2. fill: the chosen template's values model, built from its parameter specs
   (rulestorm/blueprint.py), with every value labelled a fact or an assumption.
Each blueprint request first takes one unit of the daily `blueprint_calls` cap.

The old attendance `Blueprint` (policy + scenario) below is still read by the old engine and the
stress variants until slices L7 and L8 move them onto the template format.
"""

import time
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field, ValidationError, create_model, model_validator

from rulestorm import config, llm
from rulestorm.blueprint import TemplateBlueprint, fill_prompt, fill_schema, to_blueprint
from rulestorm.core.model import Template, shipped_templates
from rulestorm.education import ARCHETYPES, TERM_WEEKS, Archetype

if TYPE_CHECKING:
    from rulestorm.store import Store

MAX_INPUT_CHARS = 2000
# Template fills measured 24 Nov (slice L6b, 10 real runs): about 1,000-1,060 output tokens and
# 21-28 s per request (pick + fill); 1,800 is about 1.7x that, so it only stops a runaway reply.
# All calls share one 55 s budget, inside CloudFront's 60 s origin timeout (docs/ARCHITECTURE.md).
BLUEPRINT_MAX_TOKENS = 1800
BLUEPRINT_DEADLINE_S = 55.0
# The pick reply is one ID and one sentence (~40 tokens); the cap stops a runaway reply.
PICK_MAX_TOKENS = 150


class PolicyInput(BaseModel):
    """What the policymaker types: the rule, why it exists, and where it applies."""

    text: str = Field(min_length=1, max_length=MAX_INPUT_CHARS)
    purpose: str = Field(min_length=1, max_length=MAX_INPUT_CHARS)
    environment: str = Field(min_length=1, max_length=MAX_INPUT_CHARS)


class Policy(PolicyInput):
    """A stored policy."""

    id: str
    created_at: str


# --- Blueprint -----------------------------------------------------------------------------

# Every one of these must be labelled in facts or assumptions, so the policymaker can see
# which values came from their text and which the AI proposed.
LABELLED_FIELDS = (
    "policy.threshold_pct",
    "scenario.admin_capacity_per_week",
    "scenario.checkpoint_week",
    "scenario.disruptions",
    "scenario.students",
    "scenario.faculty",
    "scenario.advisor",
)


class PolicyParameters(BaseModel):
    threshold_pct: int = Field(ge=50, le=100, description="minimum attendance % for eligibility")
    scope: Literal["per_course", "overall"]
    exception_rule: str = Field(min_length=1, max_length=300)
    outcomes_to_monitor: list[str] = Field(min_length=1, max_length=8)


class Profile(BaseModel):
    """Who an LLM agent is and what it wants. The role is fixed by the education model; the
    profile comes from the user's text or an AI assumption the user approves (slice 3c)."""

    description: str = Field(
        min_length=1, max_length=200, description="who this person is, in this institution's setting"
    )
    goals: list[str] = Field(min_length=1, max_length=3, description="what this person wants this term")


class StudentProfile(Profile):
    archetype: Archetype
    constraints: list[str] = Field(min_length=1, max_length=5)
    travel_buffer_min: int = Field(
        ge=0, le=180, description="minutes of slack before class; a longer delay makes them late"
    )


class Disruption(BaseModel):
    week: int = Field(ge=1, le=TERM_WEEKS)
    type: Literal["transport", "admin_capacity"]
    description: str = Field(min_length=1, max_length=200)
    delay_min: int = Field(0, ge=0, le=180, description="transport only: delay in minutes")
    affected: list[Archetype] = Field(default_factory=list, description="transport only")
    admin_capacity_during: int | None = Field(
        None, ge=0, le=50, description="admin_capacity only: requests the office can process that week"
    )

    @model_validator(mode="after")
    def _fields_match_type(self) -> "Disruption":
        if self.type == "transport" and (self.delay_min <= 0 or not self.affected):
            raise ValueError("a transport disruption needs delay_min > 0 and a non-empty affected list")
        if self.type == "admin_capacity" and self.admin_capacity_during is None:
            raise ValueError("an admin_capacity disruption needs admin_capacity_during")
        return self


class Scenario(BaseModel):
    students: list[StudentProfile] = Field(min_length=4, max_length=4)
    faculty: Profile
    advisor: Profile
    admin_capacity_per_week: int = Field(ge=0, le=50)
    checkpoint_week: int = Field(ge=1, le=TERM_WEEKS)
    disruptions: list[Disruption] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def _one_student_per_archetype(self) -> "Scenario":
        if sorted(s.archetype for s in self.students) != sorted(ARCHETYPES):
            raise ValueError(f"students must be exactly one of each archetype: {', '.join(ARCHETYPES)}")
        return self


class Label(BaseModel):
    field: str = Field(min_length=1, max_length=80, description="blueprint path, e.g. scenario.checkpoint_week")
    statement: str = Field(min_length=1, max_length=200)


class Blueprint(BaseModel):
    policy: PolicyParameters
    scenario: Scenario
    facts: list[Label] = Field(min_length=1, max_length=8, description="values stated in the user's text")
    assumptions: list[Label] = Field(min_length=1, max_length=8, description="values the AI proposed")

    @model_validator(mode="after")
    def _key_values_labelled(self) -> "Blueprint":
        labelled = [label.field for label in self.facts + self.assumptions]
        missing = [f for f in LABELLED_FIELDS if not any(x.startswith(f) for x in labelled)]
        if missing:
            raise ValueError(f"label these in facts or assumptions: {', '.join(missing)}")
        return self


class BlueprintDraft(BaseModel):
    """The result of interpreting a policy, before it is stored."""

    policy_id: str
    model_id: str
    status: Literal["valid", "invalid", "out_of_scope"]
    errors: list[str] = Field(default_factory=list)
    # The pick (call 1): shown on the review screen as one more labelled AI assumption.
    template_id: str | None = None
    template_version: int | None = None
    pick_reason: str | None = None
    # The template format (slice L6b); the old attendance format while L7/L8 port its readers.
    blueprint: TemplateBlueprint | Blueprint | None = None
    attempts: int
    seconds: float
    # Measured per request: why a reply had to be retried, and the tokens used (sets max_tokens).
    retried: list[str] = Field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    # Stress variants (slice 6c): the approved blueprint this one varies, and why.
    parent_id: str | None = None
    variant: str | None = None
    weak_point: str | None = None


class BlueprintRecord(BlueprintDraft):
    """A stored blueprint. Approval (slice 3b) freezes it."""

    id: str
    approved: bool = False
    created_at: str


def pick_prompt(policy: Policy, templates: list[Template]) -> str:
    scopes = "\n".join(f"- {t.id}: {t.scope}" for t in templates)
    return (
        "You decide which simulation template can model an institution's policy. A template "
        "fits only if its scope covers what the policy regulates; a policy about something else "
        "fits none, even if it is set in the same institution.\n"
        f"Templates (id: scope):\n{scopes}\n"
        "Reply with the id of the template that fits, or \"none\" if no template fits, and a "
        "reason in one sentence (under 25 words).\n\n"
        f"Policy:\n{policy.text}\n\nPurpose:\n{policy.purpose}\n\nEnvironment:\n{policy.environment}"
    )


def pick_schema(template_ids: list[str]) -> type[BaseModel]:
    """The reply must name a known template or "none"; anything else is retried with the error."""
    return create_model(
        "TemplatePick",
        template_id=(Literal[tuple([*template_ids, "none"])], ...),
        reason=(str, Field(min_length=1, max_length=300)),
    )


def interpret(policy: Policy, model: llm.Model | None = None) -> BlueprintDraft:
    """Pick, then fill: at most 2 attempts per call, no boto retries, one shared deadline."""
    model = model or llm.get_model(max_attempts=1)
    started = time.monotonic()
    templates = {t.id: t for t in shipped_templates()}
    draft = BlueprintDraft(policy_id=policy.id, model_id=model.model_id, status="invalid", attempts=0, seconds=0)

    pick = llm.decide(pick_prompt(policy, list(templates.values())), pick_schema(list(templates)), model=model,
                      max_tokens=PICK_MAX_TOKENS, deadline_s=BLUEPRINT_DEADLINE_S)
    draft.attempts = pick.attempts
    _measure(draft, pick, pick_schema(list(templates)))
    if pick.no_action:
        draft.errors = [f"template pick: {pick.error}"]
    elif pick.value.template_id == "none":
        draft.status, draft.pick_reason = "out_of_scope", pick.value.reason
    else:
        template = templates[pick.value.template_id]
        draft.template_id, draft.template_version = template.id, template.version
        draft.pick_reason = pick.value.reason
        fill = llm.decide(fill_prompt(template, policy.text, policy.purpose, policy.environment),
                          fill_schema(template), model=model, max_tokens=BLUEPRINT_MAX_TOKENS,
                          deadline_s=BLUEPRINT_DEADLINE_S - (time.monotonic() - started))
        draft.attempts += fill.attempts
        _measure(draft, fill, fill_schema(template))
        draft.status = "invalid" if fill.no_action else "valid"
        draft.errors = [fill.error] if fill.error else []
        draft.blueprint = None if fill.no_action else to_blueprint(template, fill.value)
    draft.seconds = round(time.monotonic() - started, 2)
    return draft


def _measure(draft: BlueprintDraft, outcome: llm.Outcome, schema: type[BaseModel]) -> None:
    """Adds the call's tokens, and why each retried reply was invalid (decide keeps only the last error)."""
    draft.input_tokens += outcome.input_tokens
    draft.output_tokens += outcome.output_tokens
    for raw in outcome.raw_replies[:-1]:  # every reply but the last was invalid
        try:
            schema.model_validate_json(llm._extract_json(raw))
        except ValidationError as exc:
            draft.retried.append(llm._short(str(exc)))


class PolicyNotFound(LookupError):
    pass


class BlueprintNotFound(LookupError):
    pass


class BlueprintInvalid(ValueError):
    """Only a blueprint that passed validation can be approved."""


class BlueprintFrozen(PermissionError):
    """An approved blueprint cannot be edited."""


class BlueprintNotApproved(PermissionError):
    """A run needs an approved blueprint."""


class DailyCapReached(RuntimeError):
    """Today's cap is used up; refused before any model call (HTTP 429)."""


def take_blueprint_call(store: "Store") -> None:
    """Every blueprint and stress-variant request takes one unit of today's cap first."""
    if not store.take_daily("blueprint_calls", config.max_blueprint_calls_per_day()):
        raise DailyCapReached(f"daily blueprint cap of {config.max_blueprint_calls_per_day()} reached")


def create_blueprint(store: "Store", policy_id: str, model: llm.Model | None = None) -> BlueprintRecord:
    """The one entry point the API and CLI share."""
    policy = store.get_policy(policy_id)
    if policy is None:
        raise PolicyNotFound(policy_id)
    take_blueprint_call(store)
    return store.save_blueprint(interpret(policy, model))


def approve_blueprint(store: "Store", blueprint_id: str) -> BlueprintRecord:
    """Approve and freeze. Approving an already approved blueprint is a no-op."""
    record = store.get_blueprint(blueprint_id)
    if record is None:
        raise BlueprintNotFound(blueprint_id)
    if record.status != "valid":
        raise BlueprintInvalid(blueprint_id)
    store.mark_approved(blueprint_id)
    return store.get_blueprint(blueprint_id)


def require_approved(store: "Store", blueprint_id: str) -> BlueprintRecord:
    """The check every run start goes through."""
    record = store.get_blueprint(blueprint_id)
    if record is None:
        raise BlueprintNotFound(blueprint_id)
    if not record.approved:
        raise BlueprintNotApproved(blueprint_id)
    return record
