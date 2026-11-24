"""Stress variants (slice 6c): a slim version of the scenario exploration loop (BRIEF nice-to-have 11).

After the policymaker approves a blueprint, one Bedrock call proposes up to 3 harsher but
plausible versions of its scenario, each aimed at a different way the policy could fail.
A variant changes only the environment: admin capacity, checkpoint week and disruptions. The
policy and every agent profile stay the parent's, so runs compare under matched agents.
Each variant is stored as its own blueprint, its changed values labelled as AI assumptions,
and runs only after the policymaker approves it. Nothing harsh is written in code.
"""

import json

from pydantic import BaseModel, Field, ValidationError

from rulestorm import llm
from rulestorm.education import SESSIONS_PER_WEEK, TERM_WEEKS
from rulestorm.policy import (
    BLUEPRINT_DEADLINE_S,
    take_blueprint_call,
    Blueprint,
    BlueprintDraft,
    BlueprintRecord,
    Disruption,
    require_approved,
)

MAX_VARIANTS = 3
VARIANTS_MAX_TOKENS = 2000
VARIED_FIELDS = ("admin_capacity_per_week", "checkpoint_week", "disruptions")


class StressVariant(BaseModel):
    """What the model proposes. Capacity and checkpoint ranges are checked when the variant is
    applied, so one out-of-range variant is stored invalid instead of failing the others."""

    name: str = Field(min_length=1, max_length=60)
    weak_point: str = Field(min_length=1, max_length=200, description="how the policy could fail under these conditions")
    admin_capacity_per_week: int
    checkpoint_week: int
    disruptions: list[Disruption] = Field(min_length=1, max_length=10)


class StressVariants(BaseModel):
    variants: list[StressVariant] = Field(min_length=1, max_length=MAX_VARIANTS)


class VariantsResult(BaseModel):
    parent_id: str
    status: str  # "valid" (variants proposed; each has its own status) or "invalid"
    errors: list[str] = Field(default_factory=list)
    variants: list[BlueprintRecord] = Field(default_factory=list)
    attempts: int
    seconds: float


def absences_to_fall_below(threshold_pct: int, checkpoint_week: int) -> int:
    """The engine's counting rule, from the blueprint's own values: by the checkpoint a student
    has 2 sessions a week, and falls below the threshold after this many unexcused absences."""
    sessions = checkpoint_week * SESSIONS_PER_WEEK
    allowed = int(sessions * (100 - threshold_pct) / 100 + 1e-9)
    return allowed + 1


def variants_prompt(parent: Blueprint, environment: str) -> str:
    sc = parent.scenario
    threshold, week = parent.policy.threshold_pct, sc.checkpoint_week
    students = [
        {"archetype": s.archetype, "constraints": s.constraints, "travel_buffer_min": s.travel_buffer_min}
        for s in sc.students
    ]
    return (
        "You stress-test an attendance policy in an education simulation. The term has "
        f"{TERM_WEEKS} weeks and {SESSIONS_PER_WEEK} sessions a week. A transport disruption hits "
        "the first session of its week: a student whose travel buffer is shorter than the delay "
        "arrives late, counted absent, if they attend. The attendance office decides exception "
        "requests first come, first served, up to its weekly capacity. Eligibility is checked "
        "at the checkpoint week: by checkpoint week w a student has had 2w sessions, and pending "
        "or rejected requests count as absences. For example, with this policy's "
        f"{threshold}% threshold and checkpoint week {week}, a student falls below the threshold "
        f"after {absences_to_fall_below(threshold, week)} unexcused absences, so conditions that "
        "cost each student fewer absences than that cannot break eligibility.\n"
        f"Policy: {parent.policy.model_dump_json()}\n"
        f"Students: {json.dumps(students)}\n"
        f"Approved scenario: admin capacity {sc.admin_capacity_per_week} a week, checkpoint week "
        f"{sc.checkpoint_week}, disruptions {json.dumps([d.model_dump() for d in sc.disruptions])}\n"
        f"The policymaker's description of the environment:\n{environment}\n\n"
        f"Propose up to {MAX_VARIANTS} stress variants: harsher but still plausible conditions for "
        "this institution under which the policy could fail its purpose or treat students unfairly. "
        "Each targets a different weak point and sets only admin_capacity_per_week (0-50), "
        f"checkpoint_week (1-{TERM_WEEKS}) and disruptions. A strike lasting several weeks is one "
        "transport entry per week. Keep names under 6 words, weak_point under 25 words and "
        "disruption descriptions under 8 words."
    )


def apply_variant(parent: Blueprint, variant: StressVariant) -> Blueprint:
    """The parent with the variant's environment values. Raises ValidationError if out of range."""
    data = parent.model_dump()
    scenario = data["scenario"]
    new = {
        "admin_capacity_per_week": variant.admin_capacity_per_week,
        "checkpoint_week": variant.checkpoint_week,
        "disruptions": [d.model_dump() for d in variant.disruptions],
    }
    statements = {
        "admin_capacity_per_week": f"{scenario['admin_capacity_per_week']} -> {variant.admin_capacity_per_week} requests a week",
        "checkpoint_week": f"week {scenario['checkpoint_week']} -> week {variant.checkpoint_week}",
        "disruptions": variant.weak_point,
    }
    changed = [f for f in VARIED_FIELDS if scenario[f] != new[f]]
    for f in changed:
        scenario[f] = new[f]
    paths = [f"scenario.{f}" for f in changed]

    def unchanged(label: dict) -> bool:
        return not any(label["field"].startswith(p) for p in paths)

    data["facts"] = [label for label in data["facts"] if unchanged(label)]
    data["assumptions"] = [label for label in data["assumptions"] if unchanged(label)] + [
        {"field": f"scenario.{f}", "statement": f"Stress variant '{variant.name}': {statements[f]}"[:200]}
        for f in changed
    ]
    return Blueprint.model_validate(data)


def propose_variants(store, parent_id: str, model: llm.Model | None = None) -> VariantsResult:
    """One model call (at most 2 with the validation retry), inside the 55 s blueprint budget."""
    parent = require_approved(store, parent_id)
    if not isinstance(parent.blueprint, Blueprint):
        from rulestorm.agents import OldFormatOnly

        raise OldFormatOnly("stress variants on the template format come with slice L8")
    take_blueprint_call(store)
    policy = store.get_policy(parent.policy_id)
    model = model or llm.get_model(max_attempts=1)
    outcome = llm.decide(
        variants_prompt(parent.blueprint, policy.environment), StressVariants, model=model,
        max_tokens=VARIANTS_MAX_TOKENS, deadline_s=BLUEPRINT_DEADLINE_S,
    )
    result = VariantsResult(
        parent_id=parent_id, status="invalid" if outcome.no_action else "valid",
        errors=[outcome.error] if outcome.error else [], attempts=outcome.attempts, seconds=outcome.seconds,
    )
    for variant in outcome.value.variants if outcome.value else []:
        draft = BlueprintDraft(
            policy_id=parent.policy_id, model_id=model.model_id, status="valid",
            attempts=outcome.attempts, seconds=outcome.seconds,
            parent_id=parent_id, variant=variant.name, weak_point=variant.weak_point,
            template_id=parent.template_id, template_version=parent.template_version,
            pick_reason=parent.pick_reason,
        )
        try:
            draft.blueprint = apply_variant(parent.blueprint, variant)
        except ValidationError as exc:
            draft.status, draft.errors = "invalid", [llm._short(str(exc))]
        result.variants.append(store.save_blueprint(draft))
    return result


class VariantRow(BaseModel):
    """One line of the stress-test table, computed from that run's recorded events."""

    blueprint_id: str
    variant: str
    run_id: str | None = None
    status: str  # the run's status, or "not approved, not run"
    requests_filed: int = 0
    queue_over_capacity: int = 0
    pending_at_checkpoint: int = 0
    not_eligible: list[str] = Field(default_factory=list)
    broke: bool = False


def outcome(events: list[dict]) -> dict:
    """Did the policy break? Yes when a request is still pending at the checkpoint (bottleneck)
    or a student is not eligible (objective failure), as BRIEF must-have 7 defines them."""
    checks = [e["payload"] for e in events if e["type"] == "eligibility_evaluated"]
    pending = sum(len(p["pending_requests"]) for p in checks)
    not_eligible = [p["student"] for p in checks if not p["eligible"]]
    return {
        "requests_filed": sum(e["type"] == "exception_request_submitted" for e in events),
        "queue_over_capacity": sum(e["type"] == "queue_over_capacity" for e in events),
        "pending_at_checkpoint": pending,
        "not_eligible": not_eligible,
        "broke": pending > 0 or bool(not_eligible),
    }


def run_variants(store, parent_id: str, out_dir: str = "runs", on_variant=None) -> list[VariantRow]:
    """Run every approved variant of an approved blueprint, one real term each."""
    from rulestorm.agents import run_local

    require_approved(store, parent_id)
    rows = []
    for v in store.list_variants(parent_id):
        if v.status != "valid":
            continue
        row = VariantRow(blueprint_id=v.id, variant=v.variant or "", status="not approved, not run")
        if v.approved:
            if on_variant:
                on_variant(v)
            run_id, summary, _, path = run_local(store, v.id, out_dir=out_dir)
            with open(path, encoding="utf-8") as f:
                events = json.load(f)["events"]
            row = VariantRow(blueprint_id=v.id, variant=row.variant, run_id=run_id, status=summary.status, **outcome(events))
        rows.append(row)
    return rows
