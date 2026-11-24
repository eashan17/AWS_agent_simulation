"""Policy input, the Blueprint schema and `interpret` (policy text -> checked Blueprint)."""

from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field, model_validator

from rulestorm import llm
from rulestorm.education import ARCHETYPES, SESSIONS_PER_WEEK, TERM_WEEKS, Archetype

if TYPE_CHECKING:
    from rulestorm.store import Store

MAX_INPUT_CHARS = 2000
# Blueprint replies were ~430-520 tokens in the day-0 smoke test; the cap keeps both attempts
# inside the 55 s budget (docs/ARCHITECTURE.md, Model adapter contract).
BLUEPRINT_MAX_TOKENS = 1500


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
)


class PolicyParameters(BaseModel):
    threshold_pct: int = Field(ge=50, le=100, description="minimum attendance % for eligibility")
    scope: Literal["per_course", "overall"]
    exception_rule: str = Field(min_length=1, max_length=300)
    outcomes_to_monitor: list[str] = Field(min_length=1, max_length=8)


class StudentProfile(BaseModel):
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
    status: Literal["valid", "invalid"]
    errors: list[str] = Field(default_factory=list)
    blueprint: Blueprint | None = None
    attempts: int
    seconds: float


class BlueprintRecord(BlueprintDraft):
    """A stored blueprint. Approval (slice 3b) freezes it."""

    id: str
    approved: bool = False
    created_at: str


def blueprint_prompt(policy: Policy) -> str:
    archetypes = "; ".join(f"{name} ({desc})" for name, desc in ARCHETYPES.items())
    return (
        "You turn an institution's attendance policy into the parameters of an education "
        "policy simulation. The simulated term has one course, "
        f"{TERM_WEEKS} weeks and {SESSIONS_PER_WEEK} sessions a week.\n"
        f"Students: exactly four, one of each archetype: {archetypes}.\n"
        "Disruptions: type 'transport' (set delay_min and the affected archetypes) or "
        "'admin_capacity' (set admin_capacity_during, how many exception requests the "
        "attendance office can process that week).\n"
        "Use values stated in the user's text and list them under facts. Where the text gives "
        "no value, propose a plausible one and list it under assumptions. Each entry's `field` "
        f"is the blueprint path it covers; every one of these must appear: {', '.join(LABELLED_FIELDS)}. "
        "Keep facts and assumptions to at most 8 short entries each.\n\n"
        f"Policy:\n{policy.text}\n\nPurpose:\n{policy.purpose}\n\nEnvironment:\n{policy.environment}"
    )


def interpret(policy: Policy, model: llm.Model | None = None) -> BlueprintDraft:
    """Exactly 2 model calls at most (first try + validation retry), no boto retries."""
    model = model or llm.get_model(max_attempts=1)
    outcome = llm.decide(blueprint_prompt(policy), Blueprint, model=model, max_tokens=BLUEPRINT_MAX_TOKENS)
    return BlueprintDraft(
        policy_id=policy.id,
        model_id=model.model_id,
        status="invalid" if outcome.no_action else "valid",
        errors=[outcome.error] if outcome.error else [],
        blueprint=outcome.value,
        attempts=outcome.attempts,
        seconds=outcome.seconds,
    )


class PolicyNotFound(LookupError):
    pass


def create_blueprint(store: "Store", policy_id: str, model: llm.Model | None = None) -> BlueprintRecord:
    """The one entry point the API and CLI share."""
    policy = store.get_policy(policy_id)
    if policy is None:
        raise PolicyNotFound(policy_id)
    return store.save_blueprint(interpret(policy, model))
