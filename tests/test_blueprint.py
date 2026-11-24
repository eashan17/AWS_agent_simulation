import copy
import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from rulestorm.api import app, get_blueprint_model, get_store
from rulestorm.llm import FakeModel
from rulestorm.policy import Blueprint, PolicyInput, interpret
from rulestorm.store import Store

# Test-only values: a reply shaped like a real one, not numbers the app uses.
VALID = {
    "policy": {
        "threshold_pct": 80,
        "scope": "per_course",
        "exception_rule": "formally approved exceptions",
        "outcomes_to_monitor": ["attendance", "eligibility"],
    },
    "scenario": {
        "students": [
            {"archetype": "commuter", "description": "travels two hours by bus", "goals": ["keep eligibility"], "constraints": ["long commute"], "travel_buffer_min": 30},
            {"archetype": "resident", "description": "lives in the hostel", "goals": ["good grades"], "constraints": ["none"], "travel_buffer_min": 10},
            {"archetype": "working", "description": "works evening shifts", "goals": ["keep the job"], "constraints": ["fixed work hours"], "travel_buffer_min": 15},
            {"archetype": "family", "description": "cares for a parent", "goals": ["balance home and study"], "constraints": ["care duties"], "travel_buffer_min": 20},
        ],
        "admin_capacity_per_week": 2,
        "checkpoint_week": 6,
        "disruptions": [
            {"week": 3, "type": "transport", "description": "bus strike", "delay_min": 45,
             "affected": ["commuter", "working"]},
            {"week": 5, "type": "admin_capacity", "description": "staff away",
             "admin_capacity_during": 1},
        ],
    },
    "facts": [{"field": "policy.threshold_pct", "statement": "80% stated in the policy"}],
    "assumptions": [
        {"field": "scenario.admin_capacity_per_week", "statement": "a few a week -> 2"},
        {"field": "scenario.checkpoint_week", "statement": "mid-term check"},
        {"field": "scenario.disruptions", "statement": "transport disruptions happen"},
        {"field": "scenario.students", "statement": "buffers proposed"},
    ],
}


def with_threshold(value: int) -> str:
    reply = copy.deepcopy(VALID)
    reply["policy"]["threshold_pct"] = value
    return json.dumps(reply)


@pytest.fixture
def store(tmp_path) -> Store:
    return Store(str(tmp_path / "test.db"))


@pytest.fixture
def policy(store):
    return store.save_policy(PolicyInput(text="80% attendance", purpose="y", environment="z"))


def test_valid_reply_gives_valid_blueprint(policy) -> None:
    draft = interpret(policy, FakeModel([json.dumps(VALID)]))
    assert draft.status == "valid" and draft.errors == []
    assert draft.blueprint.policy.threshold_pct == 80


def test_threshold_150_rejected(policy) -> None:
    with pytest.raises(ValidationError, match="threshold_pct"):
        Blueprint.model_validate_json(with_threshold(150))
    draft = interpret(policy, FakeModel([with_threshold(150), with_threshold(150)]))
    assert draft.status == "invalid"
    assert "threshold_pct" in draft.errors[0]


def test_invalid_twice_gives_status_invalid_with_errors(policy, store) -> None:
    draft = interpret(policy, FakeModel(["not json", "{}"]))
    assert draft.status == "invalid" and draft.blueprint is None
    assert draft.attempts == 2 and draft.errors
    saved = store.save_blueprint(draft)
    assert store.get_blueprint(saved.id).status == "invalid"


def test_unlabelled_value_is_retried(policy) -> None:
    unlabelled = copy.deepcopy(VALID)
    unlabelled["assumptions"] = unlabelled["assumptions"][:1]
    model = FakeModel([json.dumps(unlabelled), json.dumps(VALID)])
    draft = interpret(policy, model)
    assert draft.status == "valid" and draft.attempts == 2
    assert "scenario.checkpoint_week" in model.prompts[1]


def test_post_blueprint_route(store, policy) -> None:
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_blueprint_model] = lambda: FakeModel([json.dumps(VALID)])
    try:
        http = TestClient(app)
        response = http.post("/api/blueprints", json={"policy_id": policy.id})
        assert response.status_code == 200
        assert response.json()["status"] == "valid"
        assert response.json()["id"].startswith("B-")
        assert http.post("/api/blueprints", json={"policy_id": "P-missing"}).status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_student_without_goals_rejected(policy) -> None:
    no_goals = copy.deepcopy(VALID)
    no_goals["scenario"]["students"][0]["goals"] = []
    with pytest.raises(ValidationError, match="goals"):
        Blueprint.model_validate(no_goals)
    missing = copy.deepcopy(VALID)
    del missing["scenario"]["students"][1]["description"]
    draft = interpret(policy, FakeModel([json.dumps(missing), json.dumps(missing)]))
    assert draft.status == "invalid" and "description" in draft.errors[0]


def test_prompt_asks_for_description_and_goals(policy) -> None:
    model = FakeModel([json.dumps(VALID)])
    interpret(policy, model)
    assert "description" in model.prompts[0] and "goals" in model.prompts[0]
