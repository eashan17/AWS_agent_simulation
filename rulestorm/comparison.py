"""Policy comparison (slice 15): strict, flexible and progressive versions of one policy, run
under the same conditions and compared as trade-offs.

The policymaker picks an approved blueprint. One model call proposes three versions of its
`policy` values (BRIEF's alternatives: the rule to the letter; defined provisions for
disruptions and verified circumstances; early warnings and support before the outcome is
decided). Only policy values can differ: the reply has no other fields, and the environment
(capacity, checkpoint, disruptions) and every person's values are copied from the approved
blueprint. A value the policymaker stated (a fact from their text, such as the 80% threshold)
stays as they wrote it in every version, so the three pursue the same standard; only worded
text (the exception rule) and the AI's assumptions can differ. Each version is checked by the
values model (and so by the engine), its changed values labelled AI assumptions, stored as its
own blueprint (`comparison_of`), approved and run.

The three runs go one after another in one background thread, since only one run goes at a
time; if someone else's run holds the slot, the comparison waits for it. The result is a table
of measures with one column per version, read from each run's recorded events. There is no
overall score or winner: the policymaker weighs the trade-offs. The AI people decide afresh in
each run, so the comparison is labelled within-model evidence.
"""

import copy
import json
import logging
import threading
import time
import uuid
from typing import Any

from pydantic import BaseModel, Field, ValidationError, create_model

from rulestorm import config, llm
from rulestorm.blueprint import Label, TemplateBlueprint, _allowed, _field, _meaning, values_model
from rulestorm.core.model import Parameter, Template, load_template
from rulestorm.counterfactual import LABEL, NOTE, measures
from rulestorm.explore import misses_lines, queue_lines
from rulestorm.policy import (
    BLUEPRINT_DEADLINE_S,
    BlueprintDraft,
    check_version,
    DailyCapReached,
    approve_blueprint,
    require_approved,
    take_blueprint_call,
)
from rulestorm.runner import FINISHED, RunActive, start_run
from rulestorm.store import _now

log = logging.getLogger("rulestorm.comparison")

VERSIONS = {
    "strict": "the rule applied to the letter: the formal process only, with the fewest exceptions",
    "flexible": "the same goal, with defined provisions for disruptions outside people's control and "
                "for verified exceptional circumstances",
    "progressive": "the same goal, with early warnings and support for people at risk before the "
                   "outcome is decided",
}
COMPARISON_MAX_TOKENS = 2000
RUNS_NEEDED = len(VERSIONS)
WAIT_FOR_SLOT_S = 15 * 60  # how long a version waits for someone else's run to finish
POLL_S = 3.0
NO_SCORE = "No single overall score: each row is a trade-off for the policymaker to weigh."


class ComparisonNotFound(LookupError):
    pass


class ComparisonActive(RuntimeError):
    """A comparison is already going; `comparison_id` is that one (HTTP 409)."""

    def __init__(self, comparison_id: str) -> None:
        super().__init__(f"comparison {comparison_id} is still running")
        self.comparison_id = comparison_id


def policy_params(template: Template) -> list[Parameter]:
    """The policy values; a version may change those not kept (see `kept`)."""
    return [p for p in template.parameters if p.kind == "policy"]


def kept(template: Template, parent: TemplateBlueprint) -> list[Parameter]:
    """Policy values the policymaker stated themselves (a fact labelled with the value's name),
    kept in every version. Text is the exception: rewording it is how the versions differ."""
    facts = {x.field for x in parent.facts}
    return [p for p in policy_params(template) if p.name in facts and p.type != "text"]


def changeable(template: Template, parent: TemplateBlueprint) -> list[Parameter]:
    """The policy values a version may set. A choice value the template allows only when the
    policy states it (stated_only) is left out, unless the approved policy already holds it."""
    fixed = {p.name for p in kept(template, parent)}
    out = []
    for p in policy_params(template):
        if p.name in fixed:
            continue
        if p.stated_only and parent.values.get(p.name) not in p.stated_only:
            p = p.model_copy(update={"choices": [c for c in p.choices if c not in p.stated_only], "stated_only": []})
        out.append(p)
    return out


# --- the proposal -------------------------------------------------------------------------------


def comparison_prompt(template: Template, parent: TemplateBlueprint, policy) -> str:
    t, cal, values = template, template.calendar, parent.values
    params = changeable(t, parent)
    fixed = kept(t, parent)
    lines = [
        f'You write policy alternatives for a simulation: "{t.title}" ({t.terms.get("setting", t.scope)}).',
        f"The term has {cal.periods} {cal.period_label}s with {cal.steps_per_period} {cal.step_label}s each.",
        f"The policymaker's policy:\n{policy.text}",
        f"Its purpose:\n{policy.purpose}",
        "",
        "How the simulation counts, worked out from the approved values:",
        *misses_lines(t, values),
        "",
        "How requests queue:",
        *queue_lines(t, values),
        "",
        "Approved policy values: " + json.dumps({p.name: values[p.name] for p in policy_params(t)}, ensure_ascii=False),
        *([("Kept in every version, as the policymaker stated them: "
            + ", ".join(f"{p.name} {values[p.name]}" for p in fixed))] if fixed else []),
        "The environment and the people stay exactly as approved; only these policy values can differ "
        "(name: meaning; allowed values):",
        *(f"- {p.name}: {_meaning(p)}; {_allowed(t, p)}" for p in params),
        "",
        "Write three versions of this policy that pursue the same purpose:",
        *(f"- {name}: {meaning}." for name, meaning in VERSIONS.items()),
        "Each version sets every one of the values above (it may keep a value unchanged) and states its "
        "approach in under 25 words. Write text values as the policy itself would state them. Keep the "
        "versions realistic for this institution; none is meant to win.",
    ]
    return "\n".join(lines)


def comparison_schema(template: Template, parent: TemplateBlueprint) -> type[BaseModel]:
    """One field per version, each with only the changeable policy values, so a version can't
    change the environment, the people or a stated value, and none can be left out."""
    values = create_model(f"Policy_{template.id}",
                          **{p.name: _field(template, p) for p in changeable(template, parent)})
    version = create_model(
        "PolicyVersion",
        approach=(str, Field(min_length=1, max_length=200, description="the version's approach, under 25 words")),
        values=(values, ...),
    )
    return create_model("PolicyVersions", **{name: (version, ...) for name in VERSIONS})


def apply_version(template: Template, parent: TemplateBlueprint, name: str, version: BaseModel) -> TemplateBlueprint:
    """The parent with the version's policy values, checked by the values model (and so by the
    engine). Raises ValidationError if the engine refuses them."""
    new = version.values.model_dump()
    values = values_model(template).model_validate(copy.deepcopy(parent.values)).model_dump()  # readings filled
    # Slice M8b: a value the version leaves out (one with a default, e.g. a reading) keeps the
    # approved value rather than falling back to the template's default.
    given = version.values.model_fields_set
    changed = [p for p in changeable(template, parent) if p.name in given and values[p.name] != new[p.name]]
    for p in changed:
        values[p.name] = new[p.name]
    values = values_model(template).model_validate(values).model_dump()
    names = {p.name for p in changed}

    def statement(p: Parameter) -> str:
        if p.type in ("int", "bool", "choice"):
            return f"{p.name} {parent.values[p.name]} -> {values[p.name]}"
        return f"{p.name} reworded: {version.approach}"

    return TemplateBlueprint(
        template_id=parent.template_id, template_version=parent.template_version, values=values,
        facts=[x for x in parent.facts if x.field not in names],
        assumptions=[x for x in parent.assumptions if x.field not in names] + [
            Label(field=p.name, statement=f"Policy version '{name}': {statement(p)}"[:200]) for p in changed],
    )


def changes(template: Template, parent: dict, child: dict) -> list[dict]:
    return [{"parameter": p.name, "from": parent[p.name], "to": child[p.name]}
            for p in policy_params(template) if parent[p.name] != child[p.name]]


# --- starting it --------------------------------------------------------------------------------


def start_comparison(store, blueprint_id: str, model: llm.Model | None = None,
                     agent_model: llm.Model | None = None, out_dir: str = "runs") -> dict:
    """Proposes the three versions (one model call, inside the blueprint budget), saves and approves
    them, and starts their runs in the background. Raises BlueprintNotFound, BlueprintNotApproved,
    ValueError (template changed), ComparisonActive, RunActive or DailyCapReached."""
    parent = require_approved(store, blueprint_id)
    template = load_template(parent.template_id)
    parent = check_version(template, parent)
    active = store.running_comparison() or store.running_search() or store.running_repeat()  # slices 16, 21
    if active:
        raise ComparisonActive(active)
    running = store.running_run()
    if running:  # checked before the model call, so a refused POST costs nothing
        raise RunActive(running)
    left = config.max_runs_per_day() - store.daily_usage()["runs"]
    if left < RUNS_NEEDED:
        raise DailyCapReached(f"a comparison needs {RUNS_NEEDED} runs; {max(left, 0)} left today")
    take_blueprint_call(store)
    policy = store.get_policy(parent.policy_id)
    model = model or llm.get_model(max_attempts=1)
    outcome = llm.decide(comparison_prompt(template, parent.blueprint, policy), comparison_schema(template, parent.blueprint),
                         model=model, max_tokens=COMPARISON_MAX_TOKENS, deadline_s=BLUEPRINT_DEADLINE_S)
    record = {
        "id": f"C-{uuid.uuid4().hex[:8]}", "blueprint_id": blueprint_id, "template": template.ref,
        "status": "invalid" if outcome.no_action else "running",
        "errors": [outcome.error] if outcome.error else [], "error": None,
        "label": LABEL, "proposal_seconds": outcome.seconds, "created_at": _now(), "finished_at": None,
        "kept": [{"parameter": p.name, "value": parent.blueprint.values[p.name], "why": "stated in the policy (a fact)"}
                 for p in kept(template, parent.blueprint)],
        "versions": [],
    }
    for name in VERSIONS if outcome.value else []:
        version = getattr(outcome.value, name)
        draft = BlueprintDraft(
            policy_id=parent.policy_id, model_id=model.model_id, status="valid",
            attempts=outcome.attempts, seconds=outcome.seconds,
            input_tokens=outcome.input_tokens, output_tokens=outcome.output_tokens,
            template_id=parent.template_id, template_version=parent.template_version, pick_reason=parent.pick_reason,
            comparison_of=blueprint_id, variant=name, weak_point=version.approach,
        )
        try:
            draft.blueprint = apply_version(template, parent.blueprint, name, version)
        except ValidationError as exc:
            draft.status, draft.errors = "invalid", [llm._short(str(exc))]
        saved = store.save_blueprint(draft)
        entry = {"name": name, "approach": version.approach, "blueprint_id": saved.id,
                 "blueprint_status": saved.status, "errors": saved.errors, "run_id": None,
                 "status": "waiting" if saved.status == "valid" else "not run: the values didn't pass the checks",
                 "changed": changes(template, parent.blueprint.values, saved.blueprint.values) if saved.blueprint else []}
        if saved.status == "valid":
            approve_blueprint(store, saved.id)
        record["versions"].append(entry)
    store.save_comparison(record)
    if record["status"] == "running":
        threading.Thread(target=_run_versions, args=(store, record["id"], agent_model, out_dir),
                         name=f"comparison-{record['id']}", daemon=True).start()
    return record


def _run_versions(store, comparison_id: str, agent_model, out_dir: str) -> None:
    record = store.get_comparison(comparison_id)
    try:
        for entry in record["versions"]:
            if entry["status"] != "waiting":
                continue
            entry["status"], entry["run_id"] = _run_one(store, entry["blueprint_id"], agent_model, out_dir,
                                                         lambda run_id: _mark(store, record, entry, run_id))
            store.update_comparison(record)
        record.update(status="completed", finished_at=_now())
    except Exception as exc:  # noqa: BLE001 - any failure ends the comparison `failed`, never stuck
        log.exception("comparison %s failed", comparison_id)
        from rulestorm.runner import public_error

        record.update(status="failed", error=public_error(exc), finished_at=_now())
    store.update_comparison(record)


def _mark(store, record: dict, entry: dict, run_id: str) -> None:
    entry.update(run_id=run_id, status="running")
    store.update_comparison(record)


def _run_one(store, blueprint_id: str, agent_model, out_dir: str, on_start) -> tuple[str, str | None]:
    """Start the version's run when the slot is free, then wait for it. Returns (status, run_id)."""
    end = time.monotonic() + WAIT_FOR_SLOT_S
    while True:
        try:
            run_id = start_run(store, blueprint_id, model=agent_model, out_dir=out_dir)
            break
        except RunActive:
            if time.monotonic() > end:
                return "not run: another run held the slot too long", None
            time.sleep(POLL_S)
        except DailyCapReached:
            return "not run: today's run limit was reached", None
    on_start(run_id)
    while (run := store.get_run(run_id))["status"] == "running":
        time.sleep(POLL_S)
    return run["status"], run_id


# --- the result ---------------------------------------------------------------------------------


def _traveller_role(template: Template) -> str | None:
    """The most numerous AI role: the people the rule is about (students, residents)."""
    ai = {r.id for r in template.roles if r.llm}
    counts: dict[str, int] = {}
    for x in template.people:
        if x.role in ai:
            counts[x.role] = counts.get(x.role, 0) + 1
    return max(counts, key=counts.get) if counts else None


def _column(store, template: Template, run_id: str) -> dict[str, Any]:
    run = store.get_run(run_id)
    events = store.run_events(run_id)
    m = measures(events)
    traveller = _traveller_role(template)
    staff = {x.id for x in template.people if x.role != traveller}
    known = {a.id for a in template.actions}  # an action the model made up is a mistyped reply
    return {
        "run": m,
        "check_failed": m["check_failed"],
        "pending_at_check": m["pending_at_check"],
        "requests_filed": m["requests_filed"],
        # Only refusals by a rule (permission, a precondition), not a reply the model mistyped.
        "refused_actions": sum(e["type"] == "action_rejected"
                               and not str(e["payload"].get("reason", "")).startswith("bad parameters")
                               and e["payload"].get("action") in known
                               for e in events),
        "queue_longest": m["queue_length"]["longest"],
        "periods_over_capacity": m["queue_length"]["periods_over_capacity"],
        "wait_mean": m["waiting_time"]["mean"],
        "never_decided": m["waiting_time"]["never_decided"],
        # The office's workload: requests it decided (by rule or by a person), not every staff turn.
        "requests_decided": sum(e["type"] == "request_decided" for e in events),
        "requests_rejected": sum(e["type"] == "request_decided" and e["payload"].get("decision") == "rejected"
                                 for e in events),
        "messages": sum(e["type"] in ("message_sent", "response_given") and e["actor"] in staff for e in events),
        "llm_calls": (run.get("summary") or {}).get("llm_calls"),
        **ledger_figures(store, run_id),
    }


def ledger_figures(store, run_id: str) -> dict[str, Any]:
    """Slice M9: the run's ledger figures for the table and the repeats: obligations lost, near
    misses, the lowest margin, unexcused absences, AI mistakes, each person's margin (to the step
    that harms them) and each harm's cause class. None when the ledger can't be read (a blueprint
    of an older template version)."""
    from rulestorm.cause import UNTRUE_CORRECTION
    from rulestorm.ledger import run_ledger

    try:
        _, book = run_ledger(store, run_id)
    except (LookupError, ValueError):
        return {"obligations_lost": None, "near_misses": None, "lowest_margin": None, "unexcused_absences": None,
                "ai_mistakes": None, "margins": {}, "cause_classes": {}}
    margins = {}
    for p in book.people:
        harmful = [m.spare for m in p.checks if m.spare is not None
                   and (m.ladder_step is None or m.ladder_step == max(x.ladder_step or 0 for x in p.checks
                                                                       if x.check == m.check))]
        if harmful:
            margins[p.person] = min(harmful)
    classes: dict[str, int] = {}
    for f in book.findings:
        if f["harm"]:
            key = f.get("cause_class") or "unclassified"
            classes[key] = classes.get(key, 0) + 1
    return {
        "obligations_lost": sum(p.obligations.lost for p in book.people),
        "near_misses": sum(f["kind"] == "near_threshold" for f in book.findings),
        "lowest_margin": min(margins.values(), default=None),
        "unexcused_absences": sum(p.absences.unexcused for p in book.people),
        "ai_mistakes": sum(p.integrity.false_claims + p.integrity.refused_by_reason.get(UNTRUE_CORRECTION, 0)
                           for p in book.people),
        "margins": margins,
        "cause_classes": classes,
    }


ROWS = [
    ("check_failed", "people who failed a check"),
    ("pending_at_check", "requests still waiting at a check"),
    ("requests_filed", "requests filed"),
    ("refused_actions", "actions the rules refused"),
    ("queue_longest", "longest queue"),
    ("periods_over_capacity", "periods the queue was over capacity"),
    ("wait_mean", "average wait for a decision (periods)"),
    ("never_decided", "requests never decided"),
    ("requests_decided", "requests decided (the office's workload)"),
    ("requests_rejected", "requests rejected"),
    ("messages", "messages from staff to people"),
    ("llm_calls", "model calls"),
    # Slice M9: from each run's ledger.
    ("obligations_lost", "obligations lost (jobs, care arrangements)"),
    ("near_misses", "near misses (passed with one miss to spare)"),
    ("lowest_margin", "lowest margin (misses anyone had to spare)"),
    ("unexcused_absences", "unexcused misses"),
    ("ai_mistakes", "AI mistakes (false claims, untrue corrections)"),
]


def get_comparison(store, comparison_id: str) -> dict:
    """The comparison as it stands: each version's changes and run, and once runs have finished,
    the trade-off table. Raises ComparisonNotFound."""
    record = store.get_comparison(comparison_id)
    if record is None:
        raise ComparisonNotFound(comparison_id)
    parent = store.get_blueprint(record["blueprint_id"])
    template = load_template(parent.template_id)
    fixed = [p.name for p in template.parameters if p.kind != "policy"]
    finished = [v for v in record["versions"] if v["run_id"] and v["status"] in FINISHED]
    blueprints = {v["name"]: store.get_blueprint(v["blueprint_id"]) for v in record["versions"]}
    record["matched"] = {
        "same_environment_and_people": all(
            bp.blueprint is not None and all(bp.blueprint.values[n] == parent.blueprint.values[n] for n in fixed)
            for bp in blueprints.values()),
        "compared": fixed,
    }
    record["note"] = NOTE
    record["no_overall_score"] = NO_SCORE
    if not finished:
        record["table"] = None
        return record
    columns = {v["name"]: _column(store, template, v["run_id"]) for v in finished}
    people = sorted({c["person"] for col in columns.values() for c in col["run"]["checks"]})
    record["table"] = {
        "columns": [v["name"] for v in finished],
        "rows": [{"measure": key, "label": label, **{name: col[key] for name, col in columns.items()}}
                 for key, label in ROWS],
        "checks": [{"person": person, **{name: next(({"value": c["value"], "passed": c["passed"], "period": c["period"]}
                                                   for c in col["run"]["checks"] if c["person"] == person), None)
                                         for name, col in columns.items()}} for person in people],
    }
    return record
