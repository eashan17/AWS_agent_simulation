"""Policy input, the stored blueprint records and `interpret` (policy text -> checked blueprint).

`interpret` makes two model calls, always in this order, sharing one 55 s wall-clock budget:
1. pick: the policy texts plus every template's scope line -> a template ID, or "none" with a
   reason (`status: out_of_scope`, and no fill call);
2. fill: the chosen template's values model, built from its parameter specs
   (rulestorm/blueprint.py), with every value labelled a fact or an assumption.
Each blueprint request first takes one unit of the daily `blueprint_calls` cap.

Records saved before slice L6b (the old attendance format) are not read; that dev data isn't
migrated (docs/ARCHITECTURE.md).
"""

import time
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field, ValidationError, create_model

from rulestorm import config, llm
from rulestorm.blueprint import TemplateBlueprint, fill_prompt, fill_schema, to_blueprint
from rulestorm.core.model import Template, shipped_templates

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
    blueprint: TemplateBlueprint | None = None
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
    # Counterfactual reruns (slice 13): the blueprint this one copies with one environment value
    # changed. Kept apart from parent_id so a counterfactual never shows up as a stress variant.
    counterfactual_of: str | None = None


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
