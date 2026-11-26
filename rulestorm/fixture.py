"""The seeded demo run (slice 10): one real run, saved to a file and restored with one command.

`export_run` bundles a finished run from the store with everything needed to show it on a fresh
server: its events and findings, its approved blueprint and its policy, which finding is the hero,
and a schema version. `restore_demo` puts it back as run `demo`, replacing any earlier `demo`, and
works its findings out again from the restored events with the current detector, so the demo shows
what the code finds, not a copy. Nothing calls Bedrock.

The file is UTF-8 without a byte-order mark. A file in another schema, or whose blueprint no
longer fits its template, is refused rather than half-restored.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rulestorm.blueprint import values_model
from rulestorm.core.model import load_template
from rulestorm.detect import detect
from rulestorm.policy import BlueprintRecord, Policy, TemplateVersionUnreadable, check_version

SCHEMA = 2  # 1 was the fixed attendance engine's run file
DEMO_RUN_ID = "demo"
DEFAULT_PATH = Path(__file__).parent / "fixtures" / "demo_run.json"
RUN_KEYS = ("blueprint_id", "template", "status", "period", "periods", "model_id", "summary", "error",
            "started_at", "finished_at")


class FixtureError(ValueError):
    """The run can't be exported, or the file can't be restored."""


def export_run(store, run_id: str, hero: str | None = None) -> dict[str, Any]:
    """A finished run with its blueprint and policy, ready to write. `hero` is a finding ID
    (default: the run's first finding)."""
    from rulestorm.runner import findings_of

    run = store.get_run(run_id)
    if run is None:
        raise FixtureError(f"run not found: {run_id}")
    if run["status"] not in ("completed", "degraded"):
        raise FixtureError(f"run {run_id} is {run['status']}; only a finished run can be the demo")
    findings = findings_of(store, run)
    if not findings:
        raise FixtureError(f"run {run_id} has no findings")
    wanted = hero or findings[0]["finding_id"]
    chosen = next((f for f in findings if f["finding_id"] == wanted), None)
    if chosen is None:
        raise FixtureError(f"run {run_id} has no finding {wanted}")
    blueprint = store.get_blueprint(run["blueprint_id"])
    if blueprint is None or not blueprint.approved:
        raise FixtureError(f"run {run_id}'s blueprint {run['blueprint_id']} is missing or not approved")
    policy = store.get_policy(blueprint.policy_id)
    if policy is None:
        raise FixtureError(f"blueprint {blueprint.id}'s policy {blueprint.policy_id} is missing")
    return {
        "schema": SCHEMA,
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_run_id": run_id,
        "hero": {k: chosen[k] for k in ("finding_id", "kind", "person", "check", "title")},
        "run": {k: run[k] for k in RUN_KEYS},
        "events": store.run_events(run_id),
        "findings": findings,
        "blueprint": blueprint.model_dump(mode="json"),
        "policy": policy.model_dump(),
    }


def write_fixture(bundle: dict[str, Any], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(bundle, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")  # no BOM
    return path


def read_fixture(path: str | Path = DEFAULT_PATH) -> dict[str, Any]:
    raw = Path(path).read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise FixtureError(f"{path} starts with a byte-order mark; save it as UTF-8 without one")
    bundle = json.loads(raw.decode("utf-8"))
    if bundle.get("schema") != SCHEMA:
        raise FixtureError(f"{path} is schema {bundle.get('schema')}, this code reads schema {SCHEMA}")
    return bundle


def check_blueprint(bundle: dict[str, Any]):
    """The bundled blueprint, checked against its template as it is now."""
    record = BlueprintRecord.model_validate(bundle["blueprint"])
    template = load_template(record.blueprint.template_id)
    try:
        record = check_version(template, record)
    except TemplateVersionUnreadable as exc:
        raise FixtureError(f"the demo {exc}") from exc
    values_model(template).model_validate(record.blueprint.values)
    return record, template


def hero_of(bundle: dict[str, Any], findings: list[dict[str, Any]]) -> str:
    """The restored hero's ID: the finding of the same kind, person and check (slice M2), not the
    same number, so findings added by a newer detector can't move it. A bundle exported before
    the hero carried its check matches on kind and person."""
    want = bundle["hero"]
    match = next((f for f in findings if f["kind"] == want["kind"] and f["person"] == want["person"]
                  and f["check"] == want.get("check", f["check"])), None)
    if match is None:
        raise FixtureError(f"the hero finding {want['finding_id']} is not found again in the bundled events")
    return match["finding_id"]


def restore_demo(store, path: str | Path = DEFAULT_PATH) -> dict[str, Any]:
    """Restores the bundled run as `demo`; returns what was restored, with the hero's new ID."""
    bundle = read_fixture(path)
    record, template = check_blueprint(bundle)
    events = bundle["events"]
    findings = [f.model_dump() for f in detect(DEMO_RUN_ID, events, template, record.blueprint.values)]
    hero = hero_of(bundle, findings)
    store.restore_policy(Policy.model_validate(bundle["policy"]))
    store.restore_blueprint(record)
    store.replace_run({"id": DEMO_RUN_ID, **bundle["run"]}, events, findings)
    return {"run_id": DEMO_RUN_ID, "schema": bundle["schema"], "source_run_id": bundle["source_run_id"],
            "hero": hero, "findings": len(findings), "events": len(events)}
