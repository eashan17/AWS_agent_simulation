"""Guided scenario search (slice 16): rounds of AI-targeted and random scenarios that look for the
conditions under which an approved policy breaks.

Each round has 3 scenarios: 2 proposed by the AI with the stress-variant prompt (the engine's
own figures for how many misses fail each check and how the queue fills) and 1 random one, drawn
within the template's allowed ranges with no AI call, so the search also looks where the AI
wouldn't (BRIEF: about 60% targeted, 40% random). A scenario changes only `environment` values;
the policy and every person's values stay the approved blueprint's.

After each run, its **closeness** is read from its own records: the fewest misses anyone had to
spare before a check would fail them, requests still pending at a check, and the queue's peak
against its capacity. From round 2 the prompt carries those results and asks the AI to push the
weak point that came closest; the random scenario varies the closest scenario so far.

A run with a finding is run once more on the same scenario. Only a break the rerun repeats ends
the search (`broken`); otherwise the scenario is marked "broke once, not repeated" and the search
goes on, because the AI people choose afresh in each run. With no confirmed break the search ends
`not_broken` with the closest scenario. Runs go one at a time, through the normal runner and its
daily caps. Everything here is within-model evidence.
"""

import copy
import logging
import random
import threading
import uuid
from typing import Any

from pydantic import BaseModel, ValidationError

from rulestorm import config, llm
from rulestorm.blueprint import Label, TemplateBlueprint, values_model
from rulestorm.comparison import ComparisonActive, _run_one
from rulestorm.core.engine import count_value
from rulestorm.core.model import Template, load_template
from rulestorm.counterfactual import LABEL, NOTE
from rulestorm.explore import (
    _first_failing,
    apply_variant,
    environment,
    variants_prompt,
    variants_schema,
)
from rulestorm.policy import (
    BLUEPRINT_DEADLINE_S,
    BlueprintDraft,
    DailyCapReached,
    approve_blueprint,
    require_approved,
    take_blueprint_call,
)
from rulestorm.runner import RunActive
from rulestorm.store import _now

log = logging.getLogger("rulestorm.search")

TARGETED_PER_ROUND = 2
RANDOM_PER_ROUND = 1
MIN_RUNS, MAX_RUNS, DEFAULT_RUNS = 3, 9, 6
RANDOM_TRIES = 40


class SearchNotFound(LookupError):
    pass


class SearchActive(RuntimeError):
    """A search is already going; `search_id` is that one (HTTP 409)."""

    def __init__(self, search_id: str) -> None:
        super().__init__(f"search {search_id} is still running")
        self.search_id = search_id


# --- closeness: how near a run came to breaking, from its own records --------------------------


def _counted(template: Template, events: list[dict], duty: str, exclude_approved: bool,
             last_step: int | None) -> dict[str, tuple[int, int]]:
    """Each person's (met, missed) for one duty from the final records (corrections applied),
    leaving out occurrences an approved request excuses, up to `last_step`."""
    records: dict[tuple[str, int], str] = {}
    for e in events:
        for key, change in (e.get("state_change") or {}).items():
            parts = key.split(".")
            if len(parts) == 4 and parts[0] == "record" and parts[1] == duty:
                records[(parts[2], int(parts[3]))] = change["to"]
    filer = {e["payload"]["request_id"]: e["payload"].get("person") or e["actor"]
             for e in events if e["type"] == "request_filed"}
    excused = {(filer.get(e["payload"]["request_id"]), s) for e in events if e["type"] == "request_decided"
               for s in e["payload"].get("approved_steps", [])} if exclude_approved else set()
    out: dict[str, list[int]] = {}
    for (person, step), outcome in records.items():
        if last_step is not None and step > last_step:
            continue
        if outcome == "missed" and (person, step) in excused:
            continue
        tally = out.setdefault(person, [0, 0])
        tally[0 if outcome == "met" else 1] += outcome in ("met", "missed")
    return {p: (m, x) for p, (m, x) in out.items()}


def closeness(template: Template, values: dict[str, Any], events: list[dict]) -> dict:
    """The smallest number of misses anyone had to spare before a check fails them (0 or less:
    failed or reached), requests pending at a check, and the queue's peak against its capacity."""
    t = template
    counts = {c.id: c for c in t.counts}
    missed_word = t.terms.get("missed_plural", "misses")
    checks = []
    for check in t.checks:
        count = counts[check.count]
        exclude = "approved_request" in count.exclude
        if check.ladder is None:
            period = values[check.at_param]
            threshold = values[check.threshold_param]
            outcome = t.terms.get("check_failed", "failed")
            recorded = {e["payload"]["person"]: (e["payload"]["count"]["met"], e["payload"]["count"]["missed"])
                        for e in events if e["type"] == "check_evaluated" and e["payload"]["check"] == check.id}
            tallies = recorded or _counted(t, events, count.duty, exclude, period * t.calendar.steps_per_period)
            where = f"{t.calendar.period_label} {period}"
        else:
            threshold = values[check.ladder[0].threshold_param]
            outcome = check.ladder[0].outcome
            tallies = _counted(t, events, count.duty, exclude, None)
            where = "the term"
        for person, (met, missed) in tallies.items():
            fails_at = _first_failing(count.kind, check.comparison, threshold, met + missed)
            if fails_at is None:
                continue
            spare = fails_at - missed
            checks.append({"check": check.id, "person": person, "spare": spare,
                           "value": count_value(count.kind, met, missed),
                           "text": (f"{person}: {spare} {missed_word} to spare before '{outcome}' ({where})"
                                    if spare > 0 else f"{person} reached '{outcome}' ({where})")})
    checks.sort(key=lambda c: c["spare"])
    pending = sum(len(e["payload"].get("pending_requests", [])) for e in events if e["type"] == "check_evaluated")
    queues = [e["payload"] for e in events if e["type"] == "queue_processed"]
    peak = max((len(q["pending"]) for q in queues), default=0)
    capacity = min((q["capacity"] for q in queues), default=None)
    return {
        "closest": checks[0] if checks else None,
        "checks": checks[:5],
        "pending_at_check": pending,
        "queue": {"peak": peak, "lowest_capacity": capacity,
                  "periods_over_capacity": sum(e["type"] == "queue_over_capacity" for e in events)},
    }


def _rank(c: dict | None) -> tuple:
    """Lower is closer to breaking: fewest misses to spare, then most pending, then fullest queue."""
    if not c:
        return (10**6, 0, 0)
    spare = c["closest"]["spare"] if c["closest"] else 10**6
    return (spare, -c["pending_at_check"], -c["queue"]["periods_over_capacity"])


def closeness_line(c: dict) -> str:
    bits = [c["closest"]["text"] if c["closest"] else "no check came close"]
    if c["pending_at_check"]:
        bits.append(f"{c['pending_at_check']} request(s) still pending at a check")
    q = c["queue"]
    if q["periods_over_capacity"]:
        bits.append(f"queue over capacity in {q['periods_over_capacity']} period(s), peak {q['peak']}")
    return "; ".join(bits)


# --- random scenarios (no AI) -------------------------------------------------------------------


def random_scenario(template: Template, base: dict[str, Any], rng: random.Random) -> dict[str, Any]:
    """`base` with its environment values redrawn at random inside the template's ranges, checked
    by the values model (and so by the engine). Policy and people values are never touched."""
    t, cal = template, template.calendar
    model = values_model(t)
    duties = {d.id: d for d in t.duties}
    request_types = {r.id: r for r in t.request_types}
    for _ in range(RANDOM_TRIES):
        values = copy.deepcopy(base)
        for p in environment(t):
            if p.type == "int" and rng.random() < 0.6:
                values[p.name] = rng.randint(p.min, p.max if p.max - p.min <= 12 else min(p.max, max(2 * base[p.name], 6)))
            elif p.type == "disruptions":
                found = list(base[p.name]) if rng.random() < 0.5 else []
                for _ in range(rng.randint(1, 3)):
                    kind = rng.choice(t.disruptions)
                    d = {"kind": kind.id, "period": rng.randint(1, cal.periods), "steps": [], "people": [],
                         "delay": 0, "capacity": None, "description": f"random: {kind.label}"[:200]}
                    steps = list(range(1, cal.steps_per_period + 1))
                    if kind.kind in ("obstacle", "conflict"):
                        owed = [x.id for x in t.people if x.role == duties[kind.duty].owed_by]
                        d["steps"] = sorted(rng.sample(steps, rng.randint(1, len(steps))))
                        # A delay can hit many people at once; a personal clash is one person's.
                        d["people"] = (sorted(rng.sample(owed, rng.randint(1, len(owed)))) if kind.kind == "obstacle"
                                       else [rng.choice(owed)])
                        d["delay"] = rng.choice([15, 30, 45, 60, 90, 120]) if kind.kind == "obstacle" else 0
                    elif kind.kind == "capacity":
                        d["capacity"] = rng.randint(0, max(1, base[request_types[kind.request_type].capacity_param]))
                    else:
                        d["steps"] = [rng.choice(steps)]
                    found.append(d)
                values[p.name] = found[-10:]
        try:
            values = model.model_validate(values).model_dump()
        except ValidationError:
            continue
        if any(values[p.name] != base[p.name] for p in environment(t)):
            return values
    raise ValueError(f"no valid random scenario for {t.ref} in {RANDOM_TRIES} tries")


def changed_env(template: Template, parent: dict, child: dict) -> list[dict]:
    out = []
    for p in environment(template):
        a, b = parent[p.name], child[p.name]
        if a == b:
            continue
        if p.type == "disruptions":
            text = lambda d: f"{template.calendar.period_label} {d['period']}: {d['description']}"  # noqa: E731
            out.append({"parameter": p.name, "added": [text(d) for d in b if d not in a],
                        "removed": [text(d) for d in a if d not in b]})
        else:
            out.append({"parameter": p.name, "from": a, "to": b})
    return out


# --- the targeted proposal ----------------------------------------------------------------------


def search_prompt(template: Template, parent: TemplateBlueprint, environment_text: str, history: list[dict]) -> str:
    """The stress-variant prompt, plus what the runs so far showed, closest first."""
    lines = [variants_prompt(template, parent, environment_text)]
    if history:
        tried = sorted(history, key=lambda s: _rank(s["closeness"]))
        lines += ["", "Scenarios already run, from each run's own records, closest to breaking first:"]
        for s in tried:
            lines.append(f"- '{s['name']}' ({s['source']}): {closeness_line(s['closeness'])}")
        lines += [f"This round, propose exactly {TARGETED_PER_ROUND} new scenarios that push harder on the weak "
                  f"point that came closest ('{tried[0]['name']}': {closeness_line(tried[0]['closeness'])}). "
                  "Do not repeat a scenario already run."]
    else:
        lines += ["", f"This round, propose exactly {TARGETED_PER_ROUND} scenarios."]
    return "\n".join(lines)


def _targeted(store, template, parent, policy, history, model) -> tuple[list[BaseModel], str | None]:
    try:
        take_blueprint_call(store)
    except DailyCapReached as exc:
        return [], str(exc)
    outcome = llm.decide(search_prompt(template, parent.blueprint, policy.environment, history),
                         variants_schema(template), model=model, max_tokens=2000, deadline_s=BLUEPRINT_DEADLINE_S)
    if outcome.no_action or not outcome.value:
        return [], outcome.error or "the AI proposed nothing"
    return list(outcome.value.variants)[:TARGETED_PER_ROUND], None


def _save(store, parent, template, blueprint: TemplateBlueprint, name: str, weak_point: str, search_id: str) -> str:
    record = store.save_blueprint(BlueprintDraft(
        policy_id=parent.policy_id, model_id=parent.model_id, status="valid", attempts=0, seconds=0.0,
        template_id=parent.template_id, template_version=parent.template_version, pick_reason=parent.pick_reason,
        blueprint=blueprint, search_of=search_id, variant=name, weak_point=weak_point,
    ))
    approve_blueprint(store, record.id)
    return record.id


def _random_blueprint(template, parent: TemplateBlueprint, values: dict, name: str) -> TemplateBlueprint:
    names = {p.name for p in environment(template) if values[p.name] != parent.values[p.name]}
    return TemplateBlueprint(
        template_id=parent.template_id, template_version=parent.template_version, values=values,
        facts=[x for x in parent.facts if x.field not in names],
        assumptions=[x for x in parent.assumptions if x.field not in names]
        + [Label(field=n, statement=f"Random scenario (no AI) '{name}': drawn within the template's range")
           for n in sorted(names)],
    )


# --- starting and running it --------------------------------------------------------------------


def start_search(store, blueprint_id: str, max_runs: int = DEFAULT_RUNS, model: llm.Model | None = None,
                 agent_model: llm.Model | None = None, out_dir: str = "runs", seed: int | None = None) -> dict:
    """Checks, saves the search as `running` and starts it in the background; answers at once.
    Raises BlueprintNotFound, BlueprintNotApproved, ValueError, SearchActive, ComparisonActive,
    RunActive or DailyCapReached."""
    parent = require_approved(store, blueprint_id)
    template = load_template(parent.template_id)
    if template.version != parent.template_version:
        raise ValueError(f"blueprint {blueprint_id} was made with {parent.template_id}@{parent.template_version}, "
                         f"but the template is now {template.ref}")
    if not MIN_RUNS <= max_runs <= MAX_RUNS:
        raise ValueError(f"max_runs must be {MIN_RUNS}-{MAX_RUNS}")
    if (active := store.running_search()):
        raise SearchActive(active)
    if (active := store.running_comparison() or store.running_repeat()):
        raise ComparisonActive(active)
    if (running := store.running_run()):
        raise RunActive(running)
    left = config.max_runs_per_day() - store.daily_usage()["runs"]
    if left < MIN_RUNS:
        raise DailyCapReached(f"a search needs at least {MIN_RUNS} runs; {max(left, 0)} left today")
    record = {
        "id": f"S-{uuid.uuid4().hex[:8]}", "blueprint_id": blueprint_id, "template": template.ref,
        "status": "running", "max_runs": max_runs, "runs_used": 0, "seed": seed if seed is not None else random.randrange(10**9),
        "label": LABEL, "note": NOTE, "rounds": [], "result": None, "error": None,
        "created_at": _now(), "finished_at": None,
    }
    store.save_search(record)
    threading.Thread(target=_search, args=(store, record, model, agent_model, out_dir),
                     name=f"search-{record['id']}", daemon=True).start()
    return record


def _search(store, record: dict, model, agent_model, out_dir: str) -> None:
    try:
        _rounds(store, record, model, agent_model, out_dir)
    except Exception as exc:  # noqa: BLE001 - any failure ends the search `failed`, never stuck
        log.exception("search %s failed", record["id"])
        from rulestorm.runner import public_error

        record.update(status="failed", error=public_error(exc), finished_at=_now())
        store.update_search(record)


def _run_scenario(store, record, scenario, agent_model, out_dir) -> dict:
    """One run of the scenario; returns its row (status, findings, closeness)."""
    row = {"run_id": None, "status": "waiting", "findings": [], "closeness": None}
    scenario["runs"].append(row)

    def started(run_id):
        row.update(run_id=run_id, status="running")
        store.update_search(record)

    status, run_id = _run_one(store, scenario["blueprint_id"], agent_model, out_dir, started)
    row.update(status=status, run_id=run_id)
    if run_id:
        record["runs_used"] += 1
        bp = store.get_blueprint(scenario["blueprint_id"]).blueprint
        events = store.run_events(run_id)
        row["findings"] = [{"finding_id": f["finding_id"], "kind": f["kind"]} for f in store.run_findings(run_id)]
        row["closeness"] = closeness(load_template(bp.template_id), bp.values, events)
    store.update_search(record)
    return row


def _rounds(store, record: dict, model, agent_model, out_dir: str) -> None:
    parent = store.get_blueprint(record["blueprint_id"])
    template = load_template(parent.template_id)
    policy = store.get_policy(parent.policy_id)
    rng = random.Random(record["seed"])
    model = model or llm.get_model(max_attempts=1)
    history: list[dict] = []  # every scenario run so far, with its best closeness
    stopped = None
    n = 0
    while record["runs_used"] < record["max_runs"] and record["status"] == "running" and not stopped:
        n += 1
        closest = min(history, key=lambda s: _rank(s["closeness"])) if history else None
        pushes = f"'{closest['name']}': {closeness_line(closest['closeness'])}" if closest else None
        rnd = {"round": n, "pushes": pushes, "proposal_error": None, "scenarios": []}
        record["rounds"].append(rnd)
        targeted, rnd["proposal_error"] = _targeted(store, template, parent, policy, history, model)
        scenarios = []
        for v in targeted:
            try:
                bp = apply_variant(template, parent.blueprint, v)
            except ValidationError as exc:
                rnd["scenarios"].append({"name": v.name, "source": "targeted", "weak_point": v.weak_point,
                                         "status": f"not run: {llm._short(str(exc))}", "runs": [], "changed": []})
                continue
            scenarios.append(("targeted", v.name, v.weak_point, bp))
        base = (store.get_blueprint(closest["blueprint_id"]).blueprint.values if closest else parent.blueprint.values)
        name = f"Random {n}" + (f" around '{closest['name']}'" if closest else "")
        values = random_scenario(template, base, rng)
        scenarios.append(("random", name, "drawn at random within the template's ranges, no AI",
                          _random_blueprint(template, parent.blueprint, values, name)))
        for source, sname, weak, bp in scenarios:
            rnd["scenarios"].append({"name": sname, "source": source, "weak_point": weak, "status": "waiting",
                                     "blueprint_id": _save(store, parent, template, bp, sname, weak, record["id"]),
                                     "changed": changed_env(template, parent.blueprint.values, bp.values),
                                     "runs": [], "confirmed": None})
        store.update_search(record)
        for s in rnd["scenarios"]:
            if s["status"] != "waiting":
                continue
            if record["runs_used"] >= record["max_runs"]:
                s["status"] = "not run: the search's runs were used up"
                continue
            first = _run_scenario(store, record, s, agent_model, out_dir)
            if first["run_id"] is None:
                s["status"], stopped = first["status"], first["status"]
                break
            history.append({"name": s["name"], "source": s["source"], "blueprint_id": s["blueprint_id"],
                            "closeness": first["closeness"]})
            if not first["findings"]:
                s["status"] = "ran: no finding"
                continue
            if record["runs_used"] >= record["max_runs"]:
                s.update(status="broke once, no runs left to repeat it", confirmed=False)
                continue
            again = _run_scenario(store, record, s, agent_model, out_dir)
            kinds = {f["kind"] for f in first["findings"]}
            if again["run_id"] and kinds & {f["kind"] for f in again["findings"]}:
                s.update(status="broke, repeated by the rerun", confirmed=True)
                record["status"] = "broken"
                record["result"] = {"scenario": s["name"], "source": s["source"], "blueprint_id": s["blueprint_id"],
                                    "runs": [first["run_id"], again["run_id"]],
                                    "findings": [f["finding_id"] for f in first["findings"] + again["findings"]],
                                    "closeness": closeness_line(first["closeness"])}
                break
            s.update(status="broke once, not repeated", confirmed=False)
        for s in rnd["scenarios"]:
            if s["status"] == "waiting":
                s["status"] = "not run: the search ended"
        store.update_search(record)
    if record["status"] == "running":
        closest = min(history, key=lambda s: _rank(s["closeness"])) if history else None
        record["status"] = "not_broken"
        record["result"] = {"summary": f"not broken in {record['runs_used']} runs", "stopped": stopped,
                            "closest": ({"scenario": closest["name"], "source": closest["source"],
                                         "blueprint_id": closest["blueprint_id"],
                                         "closeness": closeness_line(closest["closeness"])} if closest else None)}
    record["finished_at"] = _now()
    store.update_search(record)


def get_search(store, search_id: str) -> dict:
    record = store.get_search(search_id)
    if record is None:
        raise SearchNotFound(search_id)
    return record
