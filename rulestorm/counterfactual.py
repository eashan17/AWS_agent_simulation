"""Counterfactual reruns (slice 13): the same term with one condition changed, then compared.

The policymaker picks a run and one of its template's single-value `environment` parameters
(for attendance: the office's weekly capacity or the checkpoint week) and a new value. The run's
blueprint is copied with only that value changed: the policy, every person's profile and the
disruption schedule stay matched. The copy is checked by the values model (and so by the
engine), labelled a fact (the policymaker asked for it), approved and run like any other.

`compare` reads both runs' recorded events: the longest queue, how long requests waited, and
who passed or failed each check. The AI people decide afresh in each run, so their choices can
differ even when every condition matches; the comparison is labelled
"within-model evidence, not real-world causality".
"""

import copy
from statistics import mean
from typing import Any

from pydantic import ValidationError

from rulestorm import llm
from rulestorm.blueprint import Label, TemplateBlueprint, values_model
from rulestorm.core.model import Parameter, Template, load_template
from rulestorm.explore import environment, outcome
from rulestorm.policy import BlueprintDraft, approve_blueprint
from rulestorm.runner import FINISHED, RunActive, start_run

LABEL = "within-model evidence, not real-world causality"
SINGLE_VALUE = ("int", "bool", "choice")
NOTE = ("The AI people decide afresh in each run, so their choices can differ even when every "
        "condition is matched.")


class RunNotFound(LookupError):
    pass


class CounterfactualRefused(Exception):
    """The asked-for change isn't one environment value the template allows (HTTP 422)."""


class RunNotFinished(Exception):
    """A run being compared is still going or failed (HTTP 409)."""


def changeable(template: Template) -> list[Parameter]:
    """The values a counterfactual may change: one environment condition with a single value."""
    return [p for p in environment(template) if p.type in SINGLE_VALUE]


def change_one(template: Template, parent: TemplateBlueprint, parameter: str, value: Any) -> TemplateBlueprint:
    """The parent with only `parameter` set to `value`, checked by the values model."""
    allowed = {p.name: p for p in changeable(template)}
    if parameter not in allowed:
        names = ", ".join(allowed)
        kind = next((p.kind for p in template.parameters if p.name == parameter), None)
        if kind == "environment":
            raise CounterfactualRefused(f"{parameter} is a list, not one value; a counterfactual can change: {names}")
        if kind:
            raise CounterfactualRefused(f"{parameter} is a {kind} value; a counterfactual changes only an "
                                        f"environment condition: {names}")
        raise CounterfactualRefused(f"{template.id} has no parameter {parameter}; a counterfactual can change: {names}")
    p = allowed[parameter]
    if p.type == "int" and (isinstance(value, bool) or not isinstance(value, int)):
        raise CounterfactualRefused(f"{parameter} takes a whole number")
    if p.type == "bool" and not isinstance(value, bool):
        raise CounterfactualRefused(f"{parameter} takes true or false")
    values = copy.deepcopy(parent.values)
    values[parameter] = value
    try:
        values = values_model(template).model_validate(values).model_dump()
    except ValidationError as exc:
        first = exc.errors()[0]
        raise CounterfactualRefused(llm._short(f"{parameter} = {value!r} is not allowed: {first['msg']}"))
    old, new = parent.values[parameter], values[parameter]
    if old == new:
        raise CounterfactualRefused(f"{parameter} is already {old!r} in this run")
    return TemplateBlueprint(
        template_id=parent.template_id, template_version=parent.template_version, values=values,
        facts=[x for x in parent.facts if x.field != parameter]
              + [Label(field=parameter, statement=f"Counterfactual asked for by the policymaker: {parameter} {old} -> {new}")],
        assumptions=[x for x in parent.assumptions if x.field != parameter],
    )


def start_counterfactual(store, run_id: str, parameter: str, value: Any, model: llm.Model | None = None,
                         out_dir: str = "runs") -> dict:
    """Saves and approves the one-change copy of the run's blueprint and starts its run. Raises
    RunNotFound, CounterfactualRefused, ValueError (template changed), RunActive or DailyCapReached."""
    run = store.get_run(run_id)
    if run is None:
        raise RunNotFound(run_id)
    parent = store.get_blueprint(run["blueprint_id"])
    if parent is None or parent.blueprint is None:
        raise RunNotFound(run_id)
    template = load_template(parent.template_id)
    if template.version != parent.template_version:
        raise ValueError(f"blueprint {parent.id} was made with {parent.template_id}@{parent.template_version}, "
                         f"but the template is now {template.ref}")
    bp = change_one(template, parent.blueprint, parameter, value)
    running = store.running_run()
    if running:  # checked before saving, so a refused POST leaves no blueprint behind
        raise RunActive(running)
    old, new = parent.blueprint.values[parameter], bp.values[parameter]
    record = store.save_blueprint(BlueprintDraft(
        policy_id=parent.policy_id, model_id=parent.model_id, status="valid", attempts=0, seconds=0.0,
        template_id=parent.template_id, template_version=parent.template_version, pick_reason=parent.pick_reason,
        blueprint=bp, counterfactual_of=parent.id, variant=f"counterfactual: {parameter} {old} -> {new}",
    ))
    approve_blueprint(store, record.id)
    new_run = start_run(store, record.id, model=model, out_dir=out_dir)
    return {"run_id": new_run, "status": "running", "source_run_id": run_id, "blueprint_id": record.id,
            "source_blueprint_id": parent.id, "changed": {"parameter": parameter, "from": old, "to": new},
            "label": LABEL}


def measures(events: list[dict]) -> dict:
    """Queue length, waiting time and check results, from a run's recorded events."""
    queues = [e["payload"] for e in events if e["type"] == "queue_processed"]
    waits = [e["payload"]["waited_periods"] for e in events if e["type"] == "request_decided"]
    checks = [e for e in events if e["type"] == "check_evaluated"]
    broke = outcome(events)
    return {
        "queue_length": {"longest": max((len(q["pending"]) for q in queues), default=0),
                         "periods_over_capacity": broke["queue_over_capacity"]},
        "waiting_time": {"unit": "periods", "decided": len(waits),
                         "mean": round(mean(waits), 2) if waits else None, "longest": max(waits, default=None),
                         "never_decided": broke["requests_filed"] - len(waits)},
        "requests_filed": broke["requests_filed"],
        "checks": [{"check": c["payload"]["check"], "person": c["payload"]["person"], "period": c["period"],
                    "value": (c["payload"].get("count") or {}).get("value"), "threshold": c["payload"].get("threshold"),
                    "passed": c["payload"]["passed"], "pending_requests": len(c["payload"]["pending_requests"])}
                   for c in checks if "passed" in c["payload"]],
        "check_failed": broke["check_failed"],
        "pending_at_check": broke["pending_at_check"],
    }


def compare(store, run_a: str, run_b: str) -> dict:
    """Both finished runs side by side, with every value their blueprints differ in."""
    runs = [store.get_run(run_id) for run_id in (run_a, run_b)]
    for run_id, run in zip((run_a, run_b), runs):  # both looked up first, so a typo is 404, not 409
        if run is None:
            raise RunNotFound(run_id)
    for run in runs:
        if run["status"] not in FINISHED:
            raise RunNotFinished(f"run {run['id']} is {run['status']}; compare it once it has finished")
    blueprints = [store.get_blueprint(run["blueprint_id"]) for run in runs]
    a, b = (bp.blueprint for bp in blueprints)
    if a.template_id != b.template_id:
        raise CounterfactualRefused(f"run {run_a} uses {a.template_id} and run {run_b} uses {b.template_id}; "
                                    "only runs of the same template compare")
    template = load_template(a.template_id)
    kinds = {p.name: p.kind for p in template.parameters}
    differences = [{"parameter": name, "kind": kinds.get(name), "from": a.values.get(name), "to": b.values.get(name)}
                   for name in sorted(set(a.values) | set(b.values)) if a.values.get(name) != b.values.get(name)]
    return {
        "label": LABEL,
        "template": template.ref,
        "differences": differences,
        "matched": len(differences) == 1 and differences[0]["kind"] == "environment",
        "note": NOTE,
        "runs": [{"run_id": run["id"], "blueprint_id": run["blueprint_id"], "status": run["status"],
                  **measures(store.run_events(run["id"]))} for run in runs],
    }
