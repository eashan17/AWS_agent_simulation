"""Repeated runs (slice 21): the same approved blueprint run several times, so outcomes read as
"how often" instead of one run's luck.

Every condition, the policy and every person's values are identical in each run (it is the same
blueprint); only the AI people's choices differ, because they decide afresh. The summary counts,
from each finished run's recorded events: how many runs each person failed the check in, with each
run's figure; how many runs had each kind of finding; and each measure's lowest, mean and highest.
An earlier finished run of the same blueprint (e.g. the demo run) can be included as the first.
Runs go one at a time through the normal runner and its daily caps.
"""

import logging
import threading
import uuid
from statistics import mean

from rulestorm import config
from rulestorm.comparison import ROWS, ComparisonActive, _column, _run_one
from rulestorm.core.model import load_template
from rulestorm.counterfactual import LABEL
from rulestorm.policy import DailyCapReached, require_approved
from rulestorm.runner import FINISHED, RunActive
from rulestorm.store import _now

log = logging.getLogger("rulestorm.repeats")

MIN_TIMES, MAX_TIMES = 2, 5
NOTE = ("Every run uses exactly the same conditions, policy and people. The AI people decide afresh "
        "in each run, so the spread below is the spread of their choices, within this model.")


class RepeatNotFound(LookupError):
    pass


class RepeatRefused(ValueError):
    """`include_run` isn't a finished run of this blueprint (HTTP 422)."""


class RepeatActive(RuntimeError):
    def __init__(self, repeat_id: str) -> None:
        super().__init__(f"repeat {repeat_id} is still running")
        self.repeat_id = repeat_id


def start_repeats(store, blueprint_id: str, times: int, include_run: str | None = None,
                  agent_model=None, out_dir: str = "runs") -> dict:
    """Checks, saves the repeat as `running` and starts its runs in the background. Raises
    BlueprintNotFound, BlueprintNotApproved, ValueError, RepeatRefused, RepeatActive,
    ComparisonActive, RunActive or DailyCapReached."""
    parent = require_approved(store, blueprint_id)
    template = load_template(parent.template_id)
    if template.version != parent.template_version:
        raise ValueError(f"blueprint {blueprint_id} was made with {parent.template_id}@{parent.template_version}, "
                         f"but the template is now {template.ref}")
    if not MIN_TIMES <= times <= MAX_TIMES:
        raise RepeatRefused(f"times must be {MIN_TIMES}-{MAX_TIMES}")
    runs = []
    if include_run:
        run = store.get_run(include_run)
        if run is None or run["blueprint_id"] != blueprint_id or run["status"] not in FINISHED:
            raise RepeatRefused(f"{include_run} is not a finished run of blueprint {blueprint_id}")
        runs.append({"run_id": include_run, "status": run["status"], "included": True})
    if (active := store.running_repeat()):
        raise RepeatActive(active)
    if (active := store.running_search() or store.running_comparison()):
        raise ComparisonActive(active)
    if (running := store.running_run()):
        raise RunActive(running)
    left = config.max_runs_per_day() - store.daily_usage()["runs"]
    if left < times:
        raise DailyCapReached(f"{times} runs asked for; {max(left, 0)} left today")
    record = {
        "id": f"R-{uuid.uuid4().hex[:8]}", "blueprint_id": blueprint_id, "template": template.ref,
        "status": "running", "times": times, "label": LABEL, "note": NOTE, "error": None,
        "runs": runs + [{"run_id": None, "status": "waiting", "included": False} for _ in range(times)],
        "created_at": _now(), "finished_at": None,
    }
    store.save_repeat(record)
    threading.Thread(target=_run_all, args=(store, record, agent_model, out_dir),
                     name=f"repeat-{record['id']}", daemon=True).start()
    return record


def _run_all(store, record: dict, agent_model, out_dir: str) -> None:
    try:
        for entry in record["runs"]:
            if entry["status"] != "waiting":
                continue

            def started(run_id, entry=entry):
                entry.update(run_id=run_id, status="running")
                store.update_repeat(record)

            status, run_id = _run_one(store, record["blueprint_id"], agent_model, out_dir, started)
            entry.update(status=status, run_id=run_id)
            store.update_repeat(record)
            if run_id is None:  # the daily cap or the slot: the rest can't run either
                for rest in record["runs"]:
                    if rest["status"] == "waiting":
                        rest["status"] = status
                break
        record.update(status="completed", finished_at=_now())
    except Exception as exc:  # noqa: BLE001 - never stuck running
        log.exception("repeat %s failed", record["id"])
        from rulestorm.runner import public_error

        record.update(status="failed", error=public_error(exc), finished_at=_now())
    store.update_repeat(record)


def _spread(values: list) -> dict:
    nums = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    if not nums:
        return {"lowest": None, "mean": None, "highest": None}
    return {"lowest": min(nums), "mean": round(mean(nums), 2), "highest": max(nums)}


def summarise(store, template, run_ids: list[str]) -> dict:
    """How often, across finished runs of one blueprint: per person, per finding kind, per measure."""
    columns = {r: _column(store, template, r) for r in run_ids}
    people: dict[str, dict] = {}
    for r in run_ids:
        for c in columns[r]["run"]["checks"]:
            p = people.setdefault(c["person"], {"person": c["person"], "checked": 0, "failed": 0, "values": []})
            p["checked"] += 1
            p["failed"] += not c["passed"]
            p["values"].append({"run_id": r, "value": c["value"], "passed": c["passed"]})
    for p in people.values():
        p.update(_spread([v["value"] for v in p["values"]]))
    findings: dict[str, int] = {}
    for r in run_ids:
        for kind in {f["kind"] for f in store.run_findings(r)}:
            findings[kind] = findings.get(kind, 0) + 1
    measures = []
    for key, label in ROWS:
        if key == "check_failed":
            continue
        values = [columns[r][key] for r in run_ids]
        measures.append({"measure": key, "label": label, "values": values, **_spread(values)})
    return {
        "runs": len(run_ids),
        "people": sorted(people.values(), key=lambda p: (-p["failed"], p["person"])),
        "findings": [{"kind": k, "runs": n} for k, n in sorted(findings.items())],
        "measures": measures,
    }


def get_repeat(store, repeat_id: str) -> dict:
    record = store.get_repeat(repeat_id)
    if record is None:
        raise RepeatNotFound(repeat_id)
    parent = store.get_blueprint(record["blueprint_id"])
    finished = [r["run_id"] for r in record["runs"] if r["run_id"] and r["status"] in FINISHED]
    record["summary"] = summarise(store, load_template(parent.template_id), finished) if finished else None
    return record
