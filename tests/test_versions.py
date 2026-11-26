"""Slice M0: one version gate. An older blueprint the template still reads gets each missing value's
default and runs; any other version is a clear 409 from every start route, never a 500."""

import json

import pytest

from rulestorm import runner
from rulestorm.core.model import TEMPLATES_DIR, check_file, check_template, load_template
from rulestorm.policy import BlueprintDraft, TemplateVersionUnreadable, approve_blueprint, check_version
from test_agents import RoutedModel
from test_runner import approved, client, store  # noqa: F401 - pytest fixtures


def _attendance_raw() -> dict:
    return json.loads((TEMPLATES_DIR / "attendance.json").read_text(encoding="utf-8"))


def _attendance_v2():
    """attendance as it would be at @2: it still reads @1, and `checkpoint_week` (read by every
    run's check) has a default of week 4."""
    raw = _attendance_raw()
    raw["version"], raw["reads_versions"] = 2, [1, 2]
    next(p for p in raw["parameters"] if p["name"] == "checkpoint_week")["default"] = 4
    result = check_template(raw)
    assert result.valid, result.errors
    return result.template


def _saved(store, approved, version: int, values: dict) -> str:  # noqa: F811
    """A stored, approved blueprint made with `attendance@<version>` holding `values`."""
    bp = approved.blueprint.model_copy(update={"template_version": version, "values": values})
    draft = store.save_blueprint(BlueprintDraft(
        policy_id=approved.policy_id, model_id="fake", status="valid", blueprint=bp,
        template_id="attendance", template_version=version, attempts=1, seconds=0.0))
    return approve_blueprint(store, draft.id).id


def test_template_check_prints_the_versions_it_reads() -> None:
    assert "reads versions: 1, 2" in check_file("attendance").lines()
    assert "reads versions: 1, 2" in check_file("hostel_curfew").lines()


def test_a_template_must_read_its_own_version() -> None:
    raw = _attendance_raw()
    raw["version"], raw["reads_versions"] = 2, [1]
    result = check_template(raw)
    assert not result.valid and "must include the template's own version 2" in result.errors[0]


def test_a_v1_blueprint_missing_a_value_gets_its_default_and_runs(store, approved, monkeypatch, tmp_path) -> None:  # noqa: F811
    template = _attendance_v2()
    assert approved.blueprint.values["checkpoint_week"] != 4
    values = {k: v for k, v in approved.blueprint.values.items() if k != "checkpoint_week"}
    blueprint_id = _saved(store, approved, 1, values)

    filled = check_version(template, store.get_blueprint(blueprint_id))
    assert filled.blueprint.values["checkpoint_week"] == 4
    assert filled.blueprint.template_version == 1  # it stays what it was made with
    assert "checkpoint_week" not in store.get_blueprint(blueprint_id).blueprint.values  # stored record untouched

    monkeypatch.setattr(runner, "load_template", lambda name: template)
    run_id = runner.run_now(store, blueprint_id, model=RoutedModel(), out_dir=str(tmp_path / "runs"))
    run = store.get_run(run_id)
    assert run["status"] == "completed", run.get("error")
    checks = [e for e in store.run_events(run_id) if e["type"] == "check_evaluated"]
    assert checks and {e["period"] for e in checks} == {4}  # the check ran at the default's week


def test_a_version_the_template_does_not_read_is_refused_by_name() -> None:
    from rulestorm.policy import BlueprintRecord

    template = load_template("attendance")
    record = BlueprintRecord.model_validate({
        "id": "B-old", "created_at": "x", "policy_id": "P-1", "model_id": "fake", "status": "valid",
        "template_id": "attendance", "template_version": 0, "attempts": 1, "seconds": 0.0,
        "blueprint": {"template_id": "attendance", "template_version": 0, "values": {}, "facts": [], "assumptions": []},
    })
    with pytest.raises(TemplateVersionUnreadable) as exc:
        check_version(template, record)
    assert str(exc.value) == "blueprint B-old was made with attendance@0; this server reads attendance@1, attendance@2"


def test_every_start_route_answers_409_for_an_unreadable_version(client, store, approved) -> None:  # noqa: F811
    http, _ = client
    old = _saved(store, approved, 0, approved.blueprint.values)
    store.create_run("L-old", old, "attendance@0", 10, "fake")
    store.update_run("L-old", status="completed")
    message = f"blueprint {old} was made with attendance@0; this server reads attendance@1, attendance@2"

    starts = {
        "run": ("/api/runs", {"blueprint_id": old}),
        "counterfactual": ("/api/runs/L-old/counterfactual", {"parameter": "office_capacity_per_week", "value": 3}),
        "comparison": ("/api/comparisons", {"blueprint_id": old}),
        "search": (f"/api/blueprints/{old}/search", {"max_runs": 3}),
        "repeats": (f"/api/blueprints/{old}/repeats", {"times": 2}),
        "variants": (f"/api/blueprints/{old}/variants", None),
    }
    for name, (path, body) in starts.items():
        response = http.post(path, json=body) if body is not None else http.post(path)
        assert (name, response.status_code) == (name, 409), response.text
        assert response.json()["detail"] == message, name
    assert store.get_run("L-old")["status"] == "completed" and store.running_run() is None
