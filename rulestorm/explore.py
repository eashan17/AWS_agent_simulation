"""Stress variants (slice 6c, ported to the template format in slice L8).

After the policymaker approves a blueprint, one Bedrock call proposes up to 3 harsher but
plausible versions of it, each aimed at a different way the policy could fail. A variant changes
only the template's `environment` parameters (for attendance: office capacity, checkpoint week,
disruptions); the policy and every person's values stay the parent's, so runs compare under
matched people. Each variant is stored as its own blueprint, its changed values labelled as AI
assumptions, and runs only after the policymaker approves it.

The prompt is written from the template and the blueprint's values, with two figures the model
can't be expected to work out: how many misses fail each check (from the count kind, the
threshold and when the check runs, using the engine's own counting) and the queue maths
(requests per period against capacity). Nothing harsh, and nothing template-specific, is
written here.
"""

import copy
import json
from typing import Any

from pydantic import BaseModel, Field, ValidationError, create_model

from rulestorm import llm
from rulestorm.blueprint import Label, TemplateBlueprint, _allowed, _field, _meaning, values_model
from rulestorm.core.engine import MAX_OCCURRENCES, MAX_OCCURRENCES_PER_PERSON, disruption_when, excused_reading
from rulestorm.detect import with_harm
from rulestorm.core.model import Parameter, Template, load_template
from rulestorm.rulebook import MissesToFail, _first_failing, misses_to_fail  # noqa: F401
from rulestorm.policy import (
    BLUEPRINT_DEADLINE_S,
    BlueprintDraft,
    BlueprintRecord,
    check_version,
    DailyCapReached,
    require_approved,
    take_blueprint_call,
)

MAX_VARIANTS = 3
VARIANTS_MAX_TOKENS = 2000


def environment(template: Template) -> list[Parameter]:
    """The only values a stress variant may change."""
    return [p for p in template.parameters if p.kind == "environment"]


# --- the figures the prompt carries -------------------------------------------------------------


# MissesToFail, _first_failing and misses_to_fail moved to rulestorm/rulebook.py (26 Nov), where
# every person's prompt uses them too; imported above so this module's names stay.


def misses_lines(template: Template, values: dict[str, Any]) -> list[str]:
    t, cal = template, template.calendar
    checks = {c.id: c for c in t.checks}
    counts = {c.id: c for c in t.counts}
    roles = {r.id: r for r in t.roles}
    missed = t.terms.get("missed_plural", "misses")
    lines = []
    for m in misses_to_fail(template, values):
        check = checks[m.check]
        count = counts[check.count]
        owes = roles[next(d.owed_by for d in t.duties if d.id == count.duty)].label
        unit = "%" if count.kind == "rate" else ""
        rule = f"{count.label} {check.comparison} {m.threshold:g}{unit}"
        if m.misses is None:
            tail = f"no number of {missed} fails it"
        else:
            tail = (f"{m.misses} {missed} make a {owes} {m.outcome}, so conditions that cost each {owes} fewer "
                    f"than {m.misses} {missed} can't")
        if m.period is not None:
            lines.append(f"- {check.label} ({rule}) is checked once, at the end of {cal.period_label} {m.period}. "
                         f"By then a {owes} has had {m.due} {cal.step_label}s: {tail}.")
        else:
            lines.append(f"- {check.label}, checked every {cal.period_label}: once {rule} no longer holds, "
                         f"the outcome is '{m.outcome}'; {tail}.")
    for count in t.counts:
        if "approved_request" in count.exclude:
            request = t.terms.get("request", "request")
            if excused_reading(t, count, values) == "count_as_met":
                lines.append(f"- An approved {request} counts the {cal.step_label}s it covers as "
                             f"{t.terms.get('duty_met', 'met')}; pending or rejected ones still count as {missed}.")
            else:
                lines.append(f"- An approved {request} excuses the {cal.step_label}s it covers; pending or "
                             f"rejected ones still count as {missed}.")
    return lines


def disruption_lines(template: Template) -> list[str]:
    t, step = template, template.calendar.step_label
    lines = []
    for kind in t.disruptions:
        if kind.kind == "obstacle":
            duty = next(d for d in t.duties if d.id == kind.duty)
            attribute = next((a for a in t.attributes if a.id == duty.obstacle_attribute), None)
            if attribute:
                lines.append(f"- {kind.label} hits the {step}s it lists: a person it names whose {attribute.label} is "
                             f"shorter than its delay misses that {step} even if they planned to {duty.label}.")
            else:
                lines.append(f"- {kind.label} hits the {step}s it lists: the people it names miss them.")
        elif kind.kind == "conflict":
            duty = next(d for d in t.duties if d.id == kind.duty)
            lines.append(f"- {kind.label} ({'routine' if kind.routine else 'not routine'}) keeps the people it names "
                         f"from the {step}s it lists unless they choose to {duty.label} anyway; it should fit "
                         f"their profile.")
        elif kind.kind == "capacity":
            rt = next(r for r in t.request_types if r.id == kind.request_type)
            lines.append(f"- {kind.label} sets how many {rt.label}s can be decided in its {t.calendar.period_label}.")
        else:
            duty = next(d for d in t.duties if d.id == kind.duty)
            lines.append(f"- {kind.label} cancels the {step}s it lists: nobody has to {duty.label} then.")
    return [f"- {line[2].upper()}{line[3:]}" for line in lines]


def queue_lines(template: Template, values: dict[str, Any]) -> list[str]:
    t, cal = template, template.calendar
    roles = {r.id: r for r in t.roles}
    lines = []
    for rt in t.request_types:
        capacity = values[rt.capacity_param]
        filers = [x.id for x in t.people if x.role == rt.filed_by]
        handler = roles[rt.handled_by].label
        when = (f"at the end of each {cal.period_label}" if rt.processed == "period_end"
                else f"after each {cal.step_label}")
        slot = cal.period_label if rt.processed == "period_end" else cal.step_label
        lines.append(f"- The {handler} decides {rt.label}s first come, first served, at most {capacity} per {slot}, "
                     f"{when}; the rest wait for the next {slot}.")
        n = len(filers)
        if n > capacity:
            backlog = f"{n - capacity} wait and the backlog grows by {n - capacity} per {slot}"
        else:
            backlog = f"all are decided in that {slot}"
        lines.append(f"- {n} {roles[rt.filed_by].label}s can file. If each files one per {slot}, that is {n} "
                     f"against {capacity} places: {backlog}.")
        if rt.processed == "period_end" and any(c.ladder is None for c in t.checks):
            lines.append(f"- The queue is processed before the check in the same {cal.period_label}, so "
                         f"{rt.label}s still waiting at the check count as not excused.")
        crunches = [d for p in environment(t) if p.type == "disruptions" for d in values[p.name]
                    if next(k for k in t.disruptions if k.id == d["kind"]).request_type == rt.id]
        for d in crunches:
            lines.append(f"- In the approved environment, {disruption_when(t, d)} can decide only "
                         f"{d['capacity']} ({d['description']}).")
    return lines


# --- the prompt and the reply -------------------------------------------------------------------


def variants_prompt(template: Template, parent: TemplateBlueprint, environment_text: str) -> str:
    t, cal, values = template, template.calendar, parent.values
    roles = {r.id: r for r in t.roles}
    env = environment(t)
    people = []
    attributes = [p for p in t.parameters if p.type == "attribute"]
    attribute_label = {a.id: a.label for a in t.attributes}
    profiles = next((values[p.name] for p in t.parameters if p.type == "profiles"), {})
    for x in t.people:
        bits = [f"{attribute_label[p.attribute]} {values[p.name][x.id]}" for p in attributes if x.id in values[p.name]]
        constraints = profiles.get(x.id, {}).get("constraints", [])
        if constraints:
            bits.append("constraints: " + "; ".join(constraints))
        label = f": {x.label}" if x.label else ""
        people.append(f"- {x.id} ({roles[x.role].label}{label})" + (f"; {', '.join(bits)}" if bits else ""))
    fixed = [p for p in t.parameters if p.kind == "policy"]
    lines = [
        f'You stress-test a policy in a simulation: "{t.title}" ({t.terms.get("setting", t.scope)}).',
        f"The term has {cal.periods} {cal.period_label}s with {cal.steps_per_period} {cal.step_label}s each.",
        "People:", *people,
        "",
        "How the simulation counts, worked out from the approved values:",
        *misses_lines(t, values),
        "",
        "How requests queue:",
        *queue_lines(t, values),
        "",
        "How disruptions work:",
        *disruption_lines(t),
        "",
        "Policy (fixed, not varied): " + json.dumps({p.name: values[p.name] for p in fixed}, ensure_ascii=False),
        "Approved environment: " + json.dumps({p.name: values[p.name] for p in env}, ensure_ascii=False),
        f"The policymaker's description of the environment:\n{environment_text}",
        "",
        f"Propose up to {MAX_VARIANTS} stress variants: harsher but still plausible conditions for this "
        "institution under which the policy could fail its purpose or treat people unfairly. Each targets a "
        "different weak point and sets every one of these values (name: meaning; allowed values):",
        *(f"- {p.name}: {_meaning(p)}; {_allowed(t, p)}" for p in env),
        f"A disruption that lasts or recurs over several {cal.period_label}s is one entry from `period` to "
        f"`until_period`, every `every` {cal.period_label}s; at most {MAX_OCCURRENCES} {cal.period_label} "
        f"occurrences in all and {MAX_OCCURRENCES_PER_PERSON} on one person. Use the figures "
        "above: conditions too mild to fail a check, or a queue that never fills, test nothing. Keep names "
        "under 6 words, weak_point under 25 words and disruption descriptions under 8 words.",
    ]
    return "\n".join(lines)


def variants_schema(template: Template) -> type[BaseModel]:
    """Only the environment values exist in the reply, so a variant can't change anything else.
    Ranges are checked here; the engine's own checks run when a variant is applied, so one bad
    variant is stored invalid instead of failing the others."""
    env = create_model(f"Environment_{template.id}", **{p.name: _field(template, p) for p in environment(template)})
    variant = create_model(
        "StressVariant",
        name=(str, Field(min_length=1, max_length=60)),
        weak_point=(str, Field(min_length=1, max_length=200, description="how the policy could fail under these conditions")),
        values=(env, ...),
    )
    return create_model("StressVariants", variants=(list[variant], Field(min_length=1, max_length=MAX_VARIANTS)))


def apply_variant(template: Template, parent: TemplateBlueprint, variant: BaseModel) -> TemplateBlueprint:
    """The parent with the variant's environment values, checked by the values model (and so by
    the engine). Raises ValidationError if the engine refuses them."""
    new = variant.values.model_dump()
    values = copy.deepcopy(parent.values)
    changed = [p for p in environment(template) if values[p.name] != new[p.name]]
    for p in changed:
        values[p.name] = new[p.name]
    values = values_model(template).model_validate(values).model_dump()
    names = {p.name for p in changed}

    def statement(p: Parameter) -> str:
        if p.type in ("int", "bool", "choice"):
            return f"{p.name} {parent.values[p.name]} -> {values[p.name]}"
        return variant.weak_point

    return TemplateBlueprint(
        template_id=parent.template_id, template_version=parent.template_version, values=values,
        facts=[x for x in parent.facts if x.field not in names],
        assumptions=[x for x in parent.assumptions if x.field not in names] + [
            Label(field=p.name, statement=f"Stress variant '{variant.name}': {statement(p)}"[:200]) for p in changed],
    )


class VariantsResult(BaseModel):
    parent_id: str
    status: str  # "valid" (variants proposed; each has its own status) or "invalid"
    errors: list[str] = Field(default_factory=list)
    variants: list[BlueprintRecord] = Field(default_factory=list)
    attempts: int
    seconds: float


def propose_variants(store, parent_id: str, model: llm.Model | None = None) -> VariantsResult:
    """One model call (at most 2 with the validation retry), inside the 55 s blueprint budget."""
    parent = require_approved(store, parent_id)
    template = load_template(parent.template_id)
    parent = check_version(template, parent)
    take_blueprint_call(store)
    policy = store.get_policy(parent.policy_id)
    model = model or llm.get_model(max_attempts=1)
    outcome = llm.decide(variants_prompt(template, parent.blueprint, policy.environment), variants_schema(template),
                         model=model, max_tokens=VARIANTS_MAX_TOKENS, deadline_s=BLUEPRINT_DEADLINE_S,
                         structured=True)
    result = VariantsResult(parent_id=parent_id, status="invalid" if outcome.no_action else "valid",
                            errors=[outcome.error] if outcome.error else [], attempts=outcome.attempts,
                            seconds=outcome.seconds)
    for variant in outcome.value.variants if outcome.value else []:
        draft = BlueprintDraft(
            policy_id=parent.policy_id, model_id=model.model_id, status="valid",
            attempts=outcome.attempts, seconds=outcome.seconds,
            input_tokens=outcome.input_tokens, output_tokens=outcome.output_tokens,
            parent_id=parent_id, variant=variant.name, weak_point=variant.weak_point,
            template_id=parent.template_id, template_version=parent.template_version, pick_reason=parent.pick_reason,
        )
        try:
            draft.blueprint = apply_variant(template, parent.blueprint, variant)
        except ValidationError as exc:
            draft.status, draft.errors = "invalid", [llm._short(str(exc))]
        result.variants.append(store.save_blueprint(draft))
    return result


# --- running them -------------------------------------------------------------------------------


class VariantRow(BaseModel):
    """One line of the stress-test table, computed from that run's recorded events."""

    blueprint_id: str
    variant: str
    run_id: str | None = None
    status: str  # the run's status, or "not approved, not run"
    requests_filed: int = 0
    queue_over_capacity: int = 0
    pending_at_check: int = 0
    check_failed: list[str] = Field(default_factory=list)
    broke: bool = False


def outcome(events: list[dict]) -> dict:
    """Did the policy break? Yes when a request is still pending at a check (a bottleneck) or a
    person fails a check (the objective failed), as BRIEF must-have 7 defines them. Reads only
    the engine's general event types, so it works on any template."""
    checks = [e["payload"] for e in events if e["type"] == "check_evaluated"]
    pending = sum(len(p["pending_requests"]) for p in checks)
    failed = sorted({p["person"] for p in checks if not p["passed"]})
    return {
        "requests_filed": sum(e["type"] == "request_filed" for e in events),
        "queue_over_capacity": sum(e["type"] == "queue_over_capacity" for e in events),
        "pending_at_check": pending,
        "check_failed": failed,
        "broke": pending > 0 or bool(failed),
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
            row = VariantRow(blueprint_id=v.id, variant=row.variant, run_id=run_id, status=summary.status,
                             **outcome(events))
        rows.append(row)
    return rows


# --- slice H: hunt for a real run with a finding --------------------------------------------------

class HuntRun(BaseModel):
    blueprint_id: str
    variant: str = Field(description="the variant's name; empty for the parent")
    run_id: str
    status: str
    findings: int


class HuntResult(BaseModel):
    parent_id: str
    max_runs: int
    runs: list[HuntRun] = Field(default_factory=list)
    found: HuntRun | None = None
    findings: list[dict] = Field(default_factory=list, description="the found run's findings")
    stopped: str | None = Field(None, description="why it stopped before a finding or max_runs")


def hunt(store, parent_id: str, max_runs: int = 10, model=None, out_dir: str = "runs",
         on_run=None, run_one=None) -> HuntResult:
    """Runs the parent's approved variants, then the parent, one real term at a time (again from
    the first while runs are left), and stops at the first run with a harm finding (a near miss
    alone doesn't stop it). Each run is saved
    with its findings, exactly as a background run is, so the one found can be opened by ID later.
    Stops early if a run fails or today's run cap is used up."""
    from rulestorm.runner import run_now

    run_one = run_one or (lambda bp_id: run_now(store, bp_id, model=model, out_dir=out_dir))
    parent = require_approved(store, parent_id)
    candidates = [(v.id, v.variant or "") for v in store.list_variants(parent_id)
                  if v.status == "valid" and v.approved] + [(parent.id, "")]
    result = HuntResult(parent_id=parent_id, max_runs=max_runs)
    for n in range(max_runs):
        blueprint_id, variant = candidates[n % len(candidates)]
        if on_run:
            on_run(n + 1, blueprint_id, variant)
        try:
            run_id = run_one(blueprint_id)
        except DailyCapReached as exc:
            result.stopped = str(exc)
            break
        run = store.get_run(run_id)
        findings = [with_harm(f) for f in store.run_findings(run_id)]
        row = HuntRun(blueprint_id=blueprint_id, variant=variant, run_id=run_id, status=run["status"],
                      findings=len(findings))
        result.runs.append(row)
        if any(f["harm"] for f in findings):  # slice M2: a near miss alone doesn't stop the hunt
            result.found, result.findings = row, findings
            break
        if run["status"] == "failed":
            result.stopped = f"run {run_id} failed: {run['error']}"
            break
    return result
