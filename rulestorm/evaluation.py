"""The pre-registered evaluation report (slice M10; protocol and pass lines in docs/EVALUATION.md).

`report(store, job_id)` reads a finished repeat (R-…) or search (S-…) from the store and makes no
AI call. For every run of it: status, model calls, decisions, false claims (refused claims of a
cause, and refused untrue corrections), no-reply decisions, intentions stated and unmet, one ledger
line per person, and every harm with its cause class. Then 15 decisions sampled with a fixed seed
(the job's ID), and pass or fail on each pass line, set beforehand:

- integrity: false claims plus no-reply decisions are at most 10% of all decisions (pooled over
  the job's runs);
- calls: every run uses at most 150 model calls;
- failed runs: every run the job asked for ended `completed` (degraded, failed or never started
  counts as a miss);
- fill time: the blueprint's fill took under 40 s (a repeat only; a search's variants are filled
  by the search, not by the protocol's step 1).
"""

import random
from typing import Any

from rulestorm.cause import UNTRUE_CORRECTION
from rulestorm.ledger import run_ledger

MAX_SHARE = 0.10
MAX_CALLS = 150
MAX_FILL_SECONDS = 40.0
SAMPLE = 15


class JobNotFound(LookupError):
    pass


def _run_ids(node: Any) -> list[str]:
    """Every run ID in a job record, in order (a search nests them in rounds and scenarios)."""
    out: list[str] = []
    if isinstance(node, dict):
        if node.get("run_id"):
            out.append(node["run_id"])
        for v in node.values():
            if isinstance(v, (dict, list)):
                out += _run_ids(v)
    elif isinstance(node, list):
        for v in node:
            out += _run_ids(v)
    return list(dict.fromkeys(out))


def _asked(node: Any) -> list[dict]:
    """Every run slot of a job, started or not: entries with a `status` and a `run_id` key."""
    out: list[dict] = []
    if isinstance(node, dict):
        if "run_id" in node and "status" in node:
            out.append(node)
        for v in node.values():
            if isinstance(v, (dict, list)):
                out += _asked(v)
    elif isinstance(node, list):
        for v in node:
            out += _asked(v)
    return out


def _run_row(store, run_id: str) -> dict:
    run = store.get_run(run_id)
    s = run.get("summary") or {}
    rejected = s.get("rejected") or []
    row = {
        "run_id": run_id, "status": run["status"], "error": run.get("error"),
        "llm_calls": s.get("llm_calls"), "decisions": s.get("decisions", 0),
        "false_claims": s.get("false_claims", 0)
        + sum(1 for r in rejected if r.get("reason") == UNTRUE_CORRECTION),
        "no_reply": s.get("llm_errors", 0), "timeouts": s.get("timeouts", 0), "cap_hits": s.get("cap_hits", 0),
        "intentions_stated": s.get("intentions_stated", 0), "intentions_unmet": s.get("intentions_unmet", 0),
        "people": [], "harms": [],
    }
    if run["status"] not in ("completed", "degraded"):
        return row
    template, book = run_ledger(store, run_id)
    for p in book.people:
        spare = [m.spare for m in p.checks if m.spare is not None]
        row["people"].append({
            "person": p.person, "lowest_margin": min(spare) if spare else None,
            "excused": p.absences.excused, "pending": p.absences.pending, "unexcused": p.absences.unexcused,
            "obligations_missed": p.obligations.missed, "obligations_lost": p.obligations.lost})
    row["harms"] = [{k: f.get(k) for k in ("finding_id", "kind", "person", "cause_class", "cause_detail",
                                           "cause_shares")}
                    for f in book.findings if f.get("harm")]
    return row


def _sample(store, run_ids: list[str], seed: str) -> list[dict]:
    pool = []
    for r in run_ids:
        for e in store.run_events(r):
            p = e["payload"]
            if e["type"] == "decision" and not p.get("error") and p.get("reason"):
                acts = ", ".join(a.get("action", "?") for a in p.get("proposals") or []) or "no action"
                pool.append({"run_id": r, "event_id": e["event_id"], "who": e["actor"], "period": e["period"],
                             "step": e["step"], "action": acts, "reason": p["reason"]})
    picked = random.Random(seed).sample(pool, min(SAMPLE, len(pool)))
    order = {r: i for i, r in enumerate(run_ids)}
    return sorted(picked, key=lambda d: (order[d["run_id"]], int(d["event_id"].split("-")[1])))


def report(store, job_id: str) -> dict:
    job = store.get_repeat(job_id) if job_id.startswith("R-") else store.get_search(job_id)
    if job is None:
        raise JobNotFound(job_id)
    kind = "repeat" if job_id.startswith("R-") else "search"
    blueprint = store.get_blueprint(job["blueprint_id"])
    run_ids = _run_ids(job.get("runs") if kind == "repeat" else job.get("rounds"))
    rows = [_run_row(store, r) for r in run_ids]
    decisions = sum(r["decisions"] for r in rows)
    bad = sum(r["false_claims"] + r["no_reply"] for r in rows)
    share = bad / decisions if decisions else None
    slots = _asked(job.get("runs") if kind == "repeat" else job.get("rounds"))
    not_completed = [s.get("run_id") or s["status"] for s in slots if s["status"] != "completed"]
    lines = {
        "integrity": {"value": None if share is None else round(share, 4), "limit": MAX_SHARE,
                      "passed": share is not None and share <= MAX_SHARE},
        "calls": {"value": max((r["llm_calls"] or 0 for r in rows), default=None), "limit": MAX_CALLS,
                  "passed": bool(rows) and all(r["llm_calls"] is not None and r["llm_calls"] <= MAX_CALLS for r in rows)},
        "failed_runs": {"value": not_completed, "passed": bool(slots) and not not_completed
                        and job.get("status") != "failed"},
    }
    if kind == "repeat":
        seconds = blueprint.seconds if blueprint is not None else None
        lines["fill_time"] = {"value": seconds, "limit": MAX_FILL_SECONDS,
                              "passed": seconds is not None and seconds < MAX_FILL_SECONDS}
    return {
        "id": job_id, "kind": kind, "status": job.get("status"), "blueprint_id": job["blueprint_id"],
        "template": blueprint.template_id if blueprint else None,
        "fill_seconds": blueprint.seconds if blueprint else None,
        "runs": rows, "decisions": decisions, "false_claims": sum(r["false_claims"] for r in rows),
        "no_reply": sum(r["no_reply"] for r in rows), "ai_mistake_rate": None if share is None else round(share, 4),
        "intentions_stated": sum(r["intentions_stated"] for r in rows),
        "intentions_unmet": sum(r["intentions_unmet"] for r in rows),
        "sample": _sample(store, [r["run_id"] for r in rows if r["people"]], job_id),
        "pass_lines": lines, "passed": all(v["passed"] for v in lines.values()),
    }


def report_lines(rep: dict) -> list[str]:
    """The report as plain lines, for `eval report`."""
    out = [f"{rep['kind']} {rep['id']} ({rep['status']}) of blueprint {rep['blueprint_id']}, "
           f"template {rep['template']}, fill {rep['fill_seconds']} s"]
    rate = "n/a" if rep["ai_mistake_rate"] is None else f"{rep['ai_mistake_rate']:.1%}"
    out.append(f"AI-mistake rate: {rep['false_claims']} false claims of {rep['decisions']} decisions; "
               f"no-reply decisions apart: {rep['no_reply']}; together {rate}")
    out.append(f"intentions: {rep['intentions_stated']} stated, {rep['intentions_unmet']} unmet")
    out.append("runs:")
    for r in rep["runs"]:
        out.append(f"  {r['run_id']} {r['status']}: {r['llm_calls']} calls, {r['decisions']} decisions, "
                   f"{r['false_claims']} false claims, {r['no_reply']} no reply"
                   + (f", error: {r['error']}" if r["error"] else ""))
        for p in r["people"]:
            ob = (f"; obligations {p['obligations_missed']} missed, {p['obligations_lost']} lost"
                  if p["obligations_missed"] or p["obligations_lost"] else "")
            out.append(f"    {p['person']}: lowest margin {p['lowest_margin']}; excused {p['excused']}, "
                       f"pending {p['pending']}, unexcused {p['unexcused']}{ob}")
        for h in r["harms"]:
            shares = ", ".join(f"{n} {k}" for k, n in (h.get("cause_shares") or {}).items())
            out.append(f"    harm {h['finding_id']} {h['kind']} {h['person']}: {h['cause_class']}"
                       + (f" ({h['cause_detail']})" if h.get("cause_detail") else "")
                       + (f"; misses by cause: {shares}" if shares else ""))
        if r["people"] and not r["harms"]:
            out.append("    harms: none")
    out.append(f"sampled decisions ({len(rep['sample'])}, seed {rep['id']}):")
    for d in rep["sample"]:
        out.append(f"  {d['run_id']} {d['event_id']} {d['who']}, period {d['period']} step {d['step']}: "
                   f"{d['action']}. \"{d['reason']}\"")
    out.append("pass lines:")
    for name, v in rep["pass_lines"].items():
        limit = f" (limit {v['limit']})" if "limit" in v else ""
        out.append(f"  {name}: {'PASS' if v['passed'] else 'FAIL'}, {v['value']}{limit}")
    out.append(f"result: {'PASS' if rep['passed'] else 'FAIL'}")
    return out

