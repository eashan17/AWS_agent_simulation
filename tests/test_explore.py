"""Slice L8 (6c ported): stress variants on any template (fake model; no Bedrock)."""

import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rulestorm import explore
from rulestorm.api import app, get_blueprint_model, get_store
from rulestorm.cli import variant_table
from rulestorm.core.model import Check, Count, load_template
from rulestorm.core.term import simulate
from rulestorm.llm import FakeModel
from rulestorm.policy import BlueprintDraft, PolicyInput, approve_blueprint, create_blueprint
from rulestorm.store import Store
from test_blueprint import FILL, PICK
from test_core_term import VALUES as TERM_VALUES
from test_core_term import decider

# Test-only variant replies. STRIKE also tries to lower the threshold: only environment values exist
# in a variant, so that key is ignored.
STRIKE = {
    "name": "Long strike, tiny office",
    "weak_point": "repeated absences meet a slow exception queue before the checkpoint",
    "values": {
        "office_capacity_per_week": 1,
        "checkpoint_week": 5,
        "disruptions": [{"kind": "transport", "period": w, "steps": [1], "people": ["commuter"], "delay": 60,
                         "description": "bus strike"} for w in (2, 3, 4)],
        "threshold_pct": 50,
    },
}
# The engine refuses this one: faculty don't owe the duty a transport disruption hits.
FACULTY_HIT = copy.deepcopy(STRIKE)
FACULTY_HIT["name"] = "Strike hits the lecturer"
FACULTY_HIT["values"]["disruptions"][0]["people"] = ["faculty"]
OUT_OF_RANGE = copy.deepcopy(STRIKE)
OUT_OF_RANGE["values"]["office_capacity_per_week"] = 99


@pytest.fixture
def template():
    return load_template("attendance")


@pytest.fixture
def store(tmp_path) -> Store:
    return Store(str(tmp_path / "test.db"))


@pytest.fixture
def parent(store):
    policy = store.save_policy(PolicyInput(text="80% attendance", purpose="y", environment="strikes happen"))
    record = create_blueprint(store, policy.id, FakeModel([PICK, json.dumps(FILL)]))
    return approve_blueprint(store, record.id)


def reply(*variants) -> str:
    return json.dumps({"variants": list(variants)})


def test_a_variant_changes_only_environment_values_and_labels_them(store, parent, template) -> None:
    result = explore.propose_variants(store, parent.id, FakeModel([reply(STRIKE)]))
    assert result.status == "valid" and len(result.variants) == 1
    v = result.variants[0]
    assert v.status == "valid" and v.parent_id == parent.id and v.variant == STRIKE["name"]
    assert not v.approved  # the policymaker approves each variant before it runs
    env = {p.name for p in template.parameters if p.kind == "environment"}
    before, after = parent.blueprint.values, v.blueprint.values
    assert {n for n in before if before[n] != after[n]} == env  # all three changed, nothing else
    assert after["threshold_pct"] == 80  # the policy is the parent's
    assert after["office_capacity_per_week"] == 1 and [d["period"] for d in after["disruptions"]] == [2, 3, 4]
    labelled = {x.field for x in v.blueprint.assumptions if x.statement.startswith("Stress variant")}
    assert labelled == env
    for name in env:  # the variant's own label wins over the parent's "environment" section label
        assert v.blueprint.label_for(template, name)[1].statement.startswith("Stress variant")
    assert v.blueprint.label_for(template, "threshold_pct") == parent.blueprint.label_for(template, "threshold_pct")
    assert store.list_variants(parent.id)[0].id == v.id


def test_a_variant_the_engine_refuses_is_stored_invalid_without_failing_the_others(store, parent) -> None:
    result = explore.propose_variants(store, parent.id, FakeModel([reply(STRIKE, FACULTY_HIT)]))
    good, bad = result.variants
    assert good.status == "valid"
    assert bad.status == "invalid" and bad.blueprint is None and "faculty" in bad.errors[0]


def test_an_out_of_range_value_is_retried_with_the_error(store, parent) -> None:
    model = FakeModel([reply(OUT_OF_RANGE), reply(STRIKE)])
    result = explore.propose_variants(store, parent.id, model)
    assert result.status == "valid" and result.attempts == 2
    assert "office_capacity_per_week" in model.prompts[1]


def test_the_prompt_holds_the_terms_the_misses_figure_and_the_queue_maths(store, parent) -> None:
    model = FakeModel([reply(STRIKE)])
    explore.propose_variants(store, parent.id, model)
    prompt = model.prompts[0]
    assert "strikes happen" in prompt  # the user's own environment text
    assert "10 weeks with 2 sessions each" in prompt
    # FILL: 80% checked in week 6 -> 12 sessions; 3 absences leave 75%, so 3 fail it
    assert "at the end of week 6. By then a Student has had 12 sessions: 3 absences make a Student not eligible" in prompt
    assert "at most 2 per week, at the end of each week" in prompt
    assert "4 Students can file. If each files one per week, that is 4 against 2 places: 2 wait" in prompt
    assert "week 5 can decide only 1 (staff away)" in prompt
    assert "commuter (Student: long-distance commuter); travel buffer (minutes of slack before class) 30" in prompt
    assert "Transport disruption hits the sessions it lists: a person it names whose travel buffer (minutes of "            "slack before class) is shorter than its delay misses that session" in prompt
    assert model.timeouts[0] == pytest.approx(55, abs=1)  # the 55 s blueprint budget


def test_explore_holds_no_template_words() -> None:
    """Everything a variant knows about attendance comes from the template."""
    source = Path(explore.__file__).read_text(encoding="utf-8").lower()
    for word in ("attendance", "student", "session", "week", "absence", "office"):
        assert word not in source.split('"""', 2)[2], word  # the module docstring may give examples


def old_absences_to_fall_below(threshold_pct: int, checkpoint_week: int) -> int:
    """Slice 6c's attendance-only formula, kept here as the reference."""
    allowed = int(checkpoint_week * 2 * (100 - threshold_pct) / 100 + 1e-9)
    return allowed + 1


def test_misses_to_fail_equals_the_6c_attendance_figure(template) -> None:
    assert old_absences_to_fall_below(80, 8) == 4 and old_absences_to_fall_below(100, 5) == 1
    for threshold in range(50, 101):
        for week in range(1, 11):
            values = {"threshold_pct": threshold, "checkpoint_week": week}
            (m,) = explore.misses_to_fail(template, values)
            assert m.misses == old_absences_to_fall_below(threshold, week), (threshold, week)
            assert m.due == 2 * week and m.period == week


def test_misses_to_fail_on_a_tally_ladder_gives_the_misses_left_before_each_step(template) -> None:
    """A curfew-like shape built from attendance: late returns tallied, checked every period on a
    ladder (pass while the tally is <= the step's threshold)."""
    tally = Count.model_validate({**template.counts[0].model_dump(), "kind": "tally", "label": "late returns"})
    ladder = Check.model_validate({
        "id": "curfew_ladder", "label": "Curfew record", "run_by": template.checks[0].run_by, "count": tally.id,
        "comparison": "<=", "ladder": [
            {"threshold_param": "warn_after", "outcome": "warning"},
            {"threshold_param": "inform_after", "outcome": "guardian informed"},
            {"threshold_param": "discipline_after", "outcome": "disciplinary"}]})
    shape = template.model_copy(update={"counts": [tally], "checks": [ladder]})
    values = {"warn_after": 1, "inform_after": 2, "discipline_after": 4}
    figures = explore.misses_to_fail(shape, values)
    assert [(m.outcome, m.misses, m.period) for m in figures] == [
        ("warning", 2, None), ("guardian informed", 3, None), ("disciplinary", 5, None)]
    lines = explore.misses_lines(shape, values)
    assert "Curfew record, checked every week: once late returns <= 1 no longer holds, the outcome is 'warning'; " \
           "2 absences make a Student warning" in lines[0]


def test_outcome_uses_general_event_types() -> None:
    template = load_template("attendance")
    # The L4 fixed-input term: the office processes nothing, so requests stay pending at the check.
    stuck = simulate(template, TERM_VALUES, decider)
    result = explore.outcome([e.model_dump() for e in stuck.events])
    assert result["requests_filed"] > 0 and result["pending_at_check"] > 0 and result["broke"] is True
    calm_values = {**TERM_VALUES, "office_capacity_per_week": 10,
                   "disruptions": [TERM_VALUES["disruptions"][0]]}
    calm = simulate(template, calm_values, decider)
    assert explore.outcome([e.model_dump() for e in calm.events])["broke"] is False


def test_unapproved_variants_are_not_run_and_the_table_counts_only_runs(store, parent, tmp_path) -> None:
    second = copy.deepcopy(STRIKE)
    second["name"] = "Early checkpoint"
    second["values"]["checkpoint_week"] = 3
    first, other = explore.propose_variants(store, parent.id, FakeModel([reply(STRIKE, second)])).variants
    approve_blueprint(store, first.id)
    rows = explore.run_variants(store, parent.id, out_dir=str(tmp_path / "runs"))
    by_id = {r.blueprint_id: r for r in rows}
    assert by_id[first.id].run_id and by_id[first.id].status in ("completed", "degraded")
    assert by_id[other.id].run_id is None and by_id[other.id].status == "not approved, not run"
    table = variant_table(rows)
    ran = by_id[first.id]
    assert table[-1] == f"broke the policy: {int(ran.broke)} of 1"
    assert sum("broke: yes" in line or "broke: no" in line for line in table) == 1  # one row per run variant


def test_variants_route(store, parent) -> None:
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_blueprint_model] = lambda: FakeModel([reply(STRIKE)])
    try:
        http = TestClient(app)
        response = http.post(f"/api/blueprints/{parent.id}/variants")
        assert response.status_code == 200
        assert response.json()["variants"][0]["variant"] == STRIKE["name"]
        assert http.post("/api/blueprints/B-missing/variants").status_code == 404
        unapproved = store.save_blueprint(BlueprintDraft(
            policy_id=parent.policy_id, model_id="fake", status="valid", blueprint=parent.blueprint,
            template_id=parent.template_id, template_version=parent.template_version, attempts=1, seconds=0.0))
        assert http.post(f"/api/blueprints/{unapproved.id}/variants").status_code == 409
    finally:
        app.dependency_overrides.clear()
