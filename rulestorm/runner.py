"""Background runs (slice 7a): one simulated term at a time, in a thread, followed by polling.

`start_run` checks the blueprint, records a `running` run and returns its ID at once; the term
runs in a background thread. After each period the new events and the period number are saved,
so `GET /api/runs/{id}` can show the timeline while the run is still going. When it ends, the
run's status (`completed` or `degraded`, from the same summary as `run local`), its summary and
the run file (runs/<run_id>.json, as `run local` writes it) are saved. An exception ends it
`failed` with the error's class and a short message.

Only one run at a time: the store inserts a new running run only if none is running, in one
statement, so a second request gets the running run's ID (HTTP 409) instead.

Spend and failure guards (slice 7b): a run takes one unit of today's run cap (after the 409
check, so a refused duplicate costs nothing), and each model call one unit of today's call cap.
A run still marked running when the server starts was cut off by a restart: it becomes failed
(interrupted). A failed run shows only the error's class and a short, cleaned message; the full
error goes to the server log.

Findings (slice 8): when a run ends, its problems are found from its events and saved before its
status changes, so a finished run always has them. A run that finished before slice 8 gets them the
first time they are asked for (`findings_of`).

Metrics (slice 14): every run that ends, failed or not, reports its model calls, tokens and
duration through `telemetry.report_run` (CloudWatch on the server; never breaks the run).
"""

import logging
import threading
import time
import uuid

from rulestorm import llm
from rulestorm.agents import Agents, summarise, write_run_file
from rulestorm.core.model import load_template
from rulestorm.core.term import Term
from rulestorm import config
from rulestorm.detect import detect
from rulestorm.telemetry import report_run
from rulestorm.policy import DailyCapReached, require_approved
from rulestorm.store import _now

log = logging.getLogger("rulestorm.runner")


class RunActive(RuntimeError):
    """A run is already going; `run_id` is that run."""

    def __init__(self, run_id: str) -> None:
        super().__init__(f"run {run_id} is still running")
        self.run_id = run_id


def start_run(store, blueprint_id: str, model: llm.Model | None = None, out_dir: str = "runs",
              cap: int | None = None) -> str:
    """Starts a run of an approved blueprint in a background thread and returns its run ID at once.
    Raises BlueprintNotFound / BlueprintNotApproved, ValueError (template changed), RunActive or
    DailyCapReached."""
    run_id, args = _begin(store, blueprint_id, model, cap)
    thread = threading.Thread(target=_run, args=(store, run_id, *args, out_dir), name=f"run-{run_id}", daemon=True)
    thread.start()
    return run_id


def run_now(store, blueprint_id: str, model: llm.Model | None = None, out_dir: str = "runs",
            cap: int | None = None) -> str:
    """The same run, in this thread (for the terminal, e.g. `explore hunt`): it is saved, capped
    and has its findings detected exactly as a background run. Returns its run ID once it ends."""
    run_id, args = _begin(store, blueprint_id, model, cap)
    _run(store, run_id, *args, out_dir)
    return run_id


def _begin(store, blueprint_id, model, cap):
    """The checks, in order (the 409 before the cap, so a refused duplicate costs nothing), then
    the `running` row."""
    record = require_approved(store, blueprint_id)
    bp = record.blueprint
    template = load_template(bp.template_id)
    if template.version != bp.template_version:
        raise ValueError(f"blueprint {blueprint_id} was made with {bp.template_id}@{bp.template_version}, "
                         f"but the template is now {template.ref}")
    running = store.running_run()
    if running:
        raise RunActive(running)
    if not store.take_daily("runs", config.max_runs_per_day()):
        raise DailyCapReached(f"daily run cap of {config.max_runs_per_day()} reached")
    agents = Agents(template, bp.values, model=model, cap=cap, store=store)
    run_id = f"L-{uuid.uuid4().hex[:8]}"
    running = store.create_run(run_id, blueprint_id, template.ref, template.calendar.periods, agents.model.model_id)
    if running:
        raise RunActive(running)
    return run_id, (record, template, agents)


def _run(store, run_id, record, template, agents, out_dir) -> None:
    started = time.monotonic()
    bp = record.blueprint
    term = Term(template, bp.values, agents.decide_phase)
    saved = 0

    def save_new_events() -> None:
        nonlocal saved
        new = term.engine.events[saved:]
        if new:
            store.add_events(run_id, [e.model_dump() for e in new])
            saved += len(new)

    def on_period(period: int) -> None:
        save_new_events()
        store.update_run(run_id, period=period)

    try:
        engine = term.run(on_period)
        save_new_events()
        summary = summarise(engine, agents)
        seconds = round(time.monotonic() - started, 1)
        write_run_file(out_dir, run_id, record.id, template.ref, seconds, summary, bp, engine.events)
        findings = detect(run_id, [e.model_dump() for e in engine.events], template)
        store.add_findings(run_id, [f.model_dump() for f in findings])
        store.update_run(run_id, status=summary.status, summary=summary.model_dump(), finished_at=_now())
        report_run(run_id, template.ref, summary.status, seconds, summary.model_dump())
    except Exception as exc:  # noqa: BLE001 - any failure ends the run `failed`, never stuck `running`
        log.exception("run %s failed", run_id)
        try:
            save_new_events()
        finally:
            store.update_run(run_id, status="failed", error=public_error(exc), finished_at=_now())
            report_run(run_id, template.ref, "failed", time.monotonic() - started, None)


FINISHED = ("completed", "degraded")


def findings_of(store, run: dict) -> list[dict]:
    """A finished run's findings; worked out from its stored events if it has none saved yet
    (it ended before slice 8, or had none). A running or failed run has none."""
    if run["status"] not in FINISHED:
        return []
    saved = store.run_findings(run["id"])
    if saved:
        return saved
    template = load_template(run["template"].split("@")[0])
    found = [f.model_dump() for f in detect(run["id"], store.run_events(run["id"]), template)]
    store.add_findings(run["id"], found)
    return store.run_findings(run["id"])


SHORT_ERROR_CHARS = 120
INTERRUPTED = "Interrupted: the server stopped while the run was going"


def public_error(exc: BaseException) -> str:
    """What the API may show: the class and a short message, with ARNs, account IDs and access
    keys removed. The full error is in the server log (log.exception above)."""
    message = llm.redact(str(exc)).strip()
    if len(message) > SHORT_ERROR_CHARS:
        message = message[:SHORT_ERROR_CHARS].rsplit(" ", 1)[0] + "…"
    return f"{type(exc).__name__}: {message}" if message else type(exc).__name__


def recover_interrupted(store) -> list[str]:
    """At server start: runs still marked running were cut off by a restart, so they fail."""
    ids = store.fail_running_runs(INTERRUPTED)
    for run_id in ids:
        log.warning("run %s was still running at startup: marked failed (interrupted)", run_id)
    for comparison_id in store.fail_running_comparisons(INTERRUPTED):  # slice 15
        log.warning("comparison %s was still running at startup: marked failed (interrupted)", comparison_id)
    for search_id in store.fail_running_searches(INTERRUPTED):  # slice 16
        log.warning("search %s was still running at startup: marked failed (interrupted)", search_id)
    for repeat_id in store.fail_running_repeats(INTERRUPTED):  # slice 21
        log.warning("repeat %s was still running at startup: marked failed (interrupted)", repeat_id)
    return ids

