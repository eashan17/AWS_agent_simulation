"""Slice 18: correcting the AI's assumptions before approval (fake model; no Bedrock)."""

import json

import pytest
from fastapi.testclient import TestClient

from rulestorm.api import app, get_store
from rulestorm.llm import FakeModel
from rulestorm.policy import PolicyInput, create_blueprint
from rulestorm.store import Store
from test_blueprint import FILL, PICK


@pytest.fixture
def store(tmp_path) -> Store:
    return Store(str(tmp_path / "test.db"))


@pytest.fixture
def draft(store):
    policy = store.save_policy(PolicyInput(text="80% attendance", purpose="y", environment="strikes happen"))
    return create_blueprint(store, policy.id, FakeModel([PICK, json.dumps(FILL)]))


@pytest.fixture
def http(store):
    app.dependency_overrides[get_store] = lambda: store
    yield TestClient(app)
    app.dependency_overrides.clear()


def patch(http, bp_id, changes):
    return http.patch(f"/api/blueprints/{bp_id}/values", json={"changes": changes})


def test_a_correction_becomes_the_policymakers_fact_and_the_blueprint_stays_unapproved(http, draft) -> None:
    before = draft.blueprint.values
    assert before["office_capacity_per_week"] == 2 and before["slack_min"]["working"] == 15
    r = patch(http, draft.id, {"office_capacity_per_week": 4, "slack_min": {"working": 10}})
    assert r.status_code == 200, r.text
    bp = r.json()
    assert bp["status"] == "valid" and bp["approved"] is False
    values = bp["blueprint"]["values"]
    assert values["office_capacity_per_week"] == 4
    assert values["slack_min"] == {**before["slack_min"], "working": 10}  # the others are kept
    facts = {f["field"]: f["statement"] for f in bp["blueprint"]["facts"]}
    assert facts["office_capacity_per_week"] == "Corrected by you: office_capacity_per_week 2 -> 4"
    assert facts["slack_min"] == "Corrected by you: slack_min working 15 -> 10"
    assumed = {a["field"] for a in bp["blueprint"]["assumptions"]}
    assert "office_capacity_per_week" not in assumed and "slack_min" not in assumed
    assert http.get(f"/api/blueprints/{draft.id}").json()["blueprint"]["values"]["office_capacity_per_week"] == 4


@pytest.mark.parametrize("changes, message", [
    ({"office_capacity_per_week": 99}, "office_capacity_per_week: Input should be less than or equal to 50"),
    ({"nope": 1}, "attendance has no value nope"),
    ({"disruptions": []}, "disruptions is a list (disruptions); it isn't editable here"),
    ({"profiles": {}}, "profiles is a list (profiles); it isn't editable here"),
    ({"slack_min": {"nobody": 3}}, "slack_min has no person nobody"),
    ({"office_capacity_per_week": True}, "office_capacity_per_week takes a whole number"),
    ({"scope": "everywhere"}, "scope: Input should be 'per_course' or 'overall'"),
    ({"office_capacity_per_week": 2}, "nothing changed"),
    ({}, "no changes given"),
])
def test_a_value_the_template_refuses_is_422_with_its_reason(http, draft, changes, message) -> None:
    r = patch(http, draft.id, changes)
    assert r.status_code == 422 and message in r.json()["detail"], r.text
    assert http.get(f"/api/blueprints/{draft.id}").json()["blueprint"] == json.loads(draft.model_dump_json())["blueprint"]


def test_an_approved_blueprint_is_frozen_and_a_missing_one_is_404(http, draft) -> None:
    assert http.post(f"/api/blueprints/{draft.id}/approve").status_code == 200
    frozen = patch(http, draft.id, {"office_capacity_per_week": 4})
    assert frozen.status_code == 409 and "frozen" in frozen.json()["detail"]
    assert patch(http, "B-missing", {"office_capacity_per_week": 4}).status_code == 404


def test_a_text_value_can_be_reworded(http, draft) -> None:
    r = patch(http, draft.id, {"exception_rule": "documented illness or transport strikes are excused"})
    assert r.status_code == 200
    facts = {f["field"]: f["statement"] for f in r.json()["blueprint"]["facts"]}
    assert facts["exception_rule"] == "Corrected by you: exception_rule reworded"
