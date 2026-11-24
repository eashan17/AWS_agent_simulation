"""Slice 6c: stress variants of an approved blueprint (fake model; no Bedrock)."""

import copy
import json

import pytest
from fastapi.testclient import TestClient

from rulestorm import explore
from rulestorm.api import app, get_blueprint_model, get_store
from rulestorm.llm import FakeModel
from rulestorm.policy import Blueprint, BlueprintDraft, PolicyInput, approve_blueprint
from rulestorm.simulation import simulate
from rulestorm.store import Store
from test_blueprint import VALID
from test_chain import blueprint as chain_blueprint
from test_chain import decider

# Test-only variant replies: a long strike with a tiny office, and one out of range.
STRIKE = {
    "name": "Long strike, tiny office",
    "weak_point": "repeated absences meet a slow exception queue before the checkpoint",
    "admin_capacity_per_week": 1,
    "checkpoint_week": 5,
    "disruptions": [
        {"week": w, "type": "transport", "description": "bus strike", "delay_min": 60, "affected": ["commuter"]}
        for w in (2, 3, 4)
    ],
}
OUT_OF_RANGE = {**copy.deepcopy(STRIKE), "name": "Impossible office", "admin_capacity_per_week": 99}


@pytest.fixture
def store(tmp_path) -> Store:
    return Store(str(tmp_path / "test.db"))


@pytest.fixture
def parent(store):
    policy = store.save_policy(PolicyInput(text="80% attendance", purpose="y", environment="strikes happen"))
    draft = BlueprintDraft(policy_id=policy.id, model_id="fake", status="valid",
                           blueprint=Blueprint.model_validate(VALID), attempts=1, seconds=0.0)
    record = store.save_blueprint(draft)
    return approve_blueprint(store, record.id)


def reply(*variants) -> str:
    return json.dumps({"variants": list(variants)})


def test_variant_changes_only_the_environment_and_labels_it(store, parent) -> None:
    result = explore.propose_variants(store, parent.id, FakeModel([reply(STRIKE)]))
    assert result.status == "valid" and len(result.variants) == 1
    v = result.variants[0]
    assert v.status == "valid" and v.parent_id == parent.id and v.variant == STRIKE["name"]
    assert not v.approved  # the policymaker approves each variant before it runs
    p, b = parent.blueprint, v.blueprint
    assert b.policy == p.policy
    assert b.scenario.students == p.scenario.students
    assert (b.scenario.faculty, b.scenario.advisor) == (p.scenario.faculty, p.scenario.advisor)
    assert b.scenario.admin_capacity_per_week == 1 and b.scenario.checkpoint_week == 5
    assert [d.week for d in b.scenario.disruptions] == [2, 3, 4]
    labelled = {a.field for a in b.assumptions if a.statement.startswith("Stress variant")}
    assert labelled == {"scenario.admin_capacity_per_week", "scenario.checkpoint_week", "scenario.disruptions"}
    assert store.list_variants(parent.id)[0].id == v.id


def test_out_of_range_variant_stored_invalid_with_the_error(store, parent) -> None:
    result = explore.propose_variants(store, parent.id, FakeModel([reply(STRIKE, OUT_OF_RANGE)]))
    good, bad = result.variants
    assert good.status == "valid"
    assert bad.status == "invalid" and bad.blueprint is None and "admin_capacity_per_week" in bad.errors[0]


def test_prompt_carries_the_approved_scenario_and_the_users_environment(store, parent) -> None:
    model = FakeModel([reply(STRIKE)])
    explore.propose_variants(store, parent.id, model)
    assert "strikes happen" in model.prompts[0]
    assert '"travel_buffer_min": 30' in model.prompts[0]
    assert model.timeouts[0] == pytest.approx(55, abs=1)  # the 55 s blueprint budget


def test_unapproved_variants_are_not_run(store, parent, tmp_path) -> None:
    second = {**copy.deepcopy(STRIKE), "name": "Early checkpoint", "checkpoint_week": 3}
    first, other = explore.propose_variants(store, parent.id, FakeModel([reply(STRIKE, second)])).variants
    approve_blueprint(store, first.id)
    rows = explore.run_variants(store, parent.id, out_dir=str(tmp_path / "runs"))
    by_id = {r.blueprint_id: r for r in rows}
    assert by_id[first.id].run_id and by_id[first.id].status in ("completed", "degraded")
    assert by_id[other.id].run_id is None and by_id[other.id].status == "not approved, not run"


def test_outcome_flags_a_request_pending_at_the_checkpoint() -> None:
    # The slice-5 fixed-input term: the admin can process nothing, so requests stay pending.
    engine = simulate(chain_blueprint(), decider)
    result = explore.outcome([e.model_dump() for e in engine.events])
    assert result["requests_filed"] > 0 and result["pending_at_checkpoint"] > 0
    assert result["broke"] is True
    calm = simulate(chain_blueprint(admin_capacity_per_week=10, disruptions=[
        {"week": 9, "type": "admin_capacity", "description": "staff away", "admin_capacity_during": 5}]), decider)
    assert explore.outcome([e.model_dump() for e in calm.events])["broke"] is False


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
            policy_id=parent.policy_id, model_id="fake", status="valid",
            blueprint=parent.blueprint, attempts=1, seconds=0.0))
        assert http.post(f"/api/blueprints/{unapproved.id}/variants").status_code == 409
    finally:
        app.dependency_overrides.clear()


def test_absences_to_fall_below_follows_the_attendance_formula() -> None:
    # 80% at week 8: 16 sessions, 3 absences leave 81.25%, 4 leave 75%.
    assert explore.absences_to_fall_below(80, 8) == 4
    # 75% at week 6: 12 sessions, 3 absences leave exactly 75% (still eligible), 4 fall below.
    assert explore.absences_to_fall_below(75, 6) == 4
    assert explore.absences_to_fall_below(100, 5) == 1
