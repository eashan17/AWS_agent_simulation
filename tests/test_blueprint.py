import copy
import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from rulestorm.api import app, get_blueprint_model, get_store
from rulestorm.llm import FakeModel
from rulestorm.policy import Blueprint, PolicyInput, interpret
from rulestorm.store import Store

# Test-only values: replies shaped like real ones, not numbers the app uses.
# Call 1 of every blueprint (slice L6a): the template pick.
PICK = json.dumps({"template_id": "attendance", "reason": "the policy sets a minimum attendance"})
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
        "faculty": {"description": "teaches the course", "goals": ["keep participation up"]},
        "advisor": {"description": "advises 40 students", "goals": ["keep advisees eligible"]},
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
        {"field": "scenario.faculty", "statement": "faculty profile proposed"},
        {"field": "scenario.advisor", "statement": "advisor profile proposed"},
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
    draft = interpret(policy, FakeModel([PICK, json.dumps(VALID)]))
    assert draft.status == "valid" and draft.errors == []
    assert draft.blueprint.policy.threshold_pct == 80


def test_threshold_150_rejected(policy) -> None:
    with pytest.raises(ValidationError, match="threshold_pct"):
        Blueprint.model_validate_json(with_threshold(150))
    draft = interpret(policy, FakeModel([PICK, with_threshold(150), with_threshold(150)]))
    assert draft.status == "invalid"
    assert "threshold_pct" in draft.errors[0]


def test_invalid_twice_gives_status_invalid_with_errors(policy, store) -> None:
    draft = interpret(policy, FakeModel([PICK, "not json", "{}"]))
    assert draft.status == "invalid" and draft.blueprint is None
    assert draft.attempts == 3 and draft.errors  # pick 1 + fill 2
    saved = store.save_blueprint(draft)
    assert store.get_blueprint(saved.id).status == "invalid"


def test_unlabelled_value_is_retried(policy) -> None:
    unlabelled = copy.deepcopy(VALID)
    unlabelled["assumptions"] = unlabelled["assumptions"][:1]
    model = FakeModel([PICK, json.dumps(unlabelled), json.dumps(VALID)])
    draft = interpret(policy, model)
    assert draft.status == "valid" and draft.attempts == 3  # pick 1 + fill 2
    assert "scenario.checkpoint_week" in model.prompts[2]


def test_post_blueprint_route(store, policy) -> None:
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_blueprint_model] = lambda: FakeModel([PICK, json.dumps(VALID)])
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
    draft = interpret(policy, FakeModel([PICK, json.dumps(missing), json.dumps(missing)]))
    assert draft.status == "invalid" and "description" in draft.errors[0]


def test_prompt_asks_for_description_and_goals(policy) -> None:
    model = FakeModel([PICK, json.dumps(VALID)])
    interpret(policy, model)
    assert "description" in model.prompts[1] and "goals" in model.prompts[1]


def test_faculty_and_advisor_profiles_required_and_labelled(policy) -> None:
    missing = copy.deepcopy(VALID)
    del missing["scenario"]["advisor"]
    with pytest.raises(ValidationError, match="advisor"):
        Blueprint.model_validate(missing)
    unlabelled = copy.deepcopy(VALID)
    unlabelled["assumptions"] = [a for a in unlabelled["assumptions"] if a["field"] != "scenario.faculty"]
    with pytest.raises(ValidationError, match="scenario.faculty"):
        Blueprint.model_validate(unlabelled)
    model = FakeModel([PICK, json.dumps(VALID)])
    interpret(policy, model)
    assert "Faculty and advisor" in model.prompts[1]


# --- slice L6a: the template pick, out of scope, the daily blueprint cap, the template list -----

NONE = json.dumps({"template_id": "none", "reason": "the policy is about canteen food, not attendance"})


def test_pick_none_gives_out_of_scope_with_the_reason_and_no_fill_call(policy) -> None:
    model = FakeModel([NONE])
    draft = interpret(policy, model)
    assert draft.status == "out_of_scope"
    assert draft.pick_reason == "the policy is about canteen food, not attendance"
    assert draft.blueprint is None and draft.template_id is None
    assert len(model.prompts) == 1  # no fill call
    assert "- attendance: Minimum attendance rules" in model.prompts[0]  # every template's scope line


def test_pick_records_the_template_and_fills_it(policy) -> None:
    model = FakeModel([PICK, json.dumps(VALID)])
    draft = interpret(policy, model)
    assert (draft.status, draft.template_id, draft.template_version) == ("valid", "attendance", 1)
    assert draft.pick_reason == "the policy sets a minimum attendance"
    assert draft.attempts == 2 and len(model.prompts) == 2


def test_unknown_template_in_the_pick_is_retried_then_invalid(policy) -> None:
    model = FakeModel([json.dumps({"template_id": "canteen", "reason": "x"}), NONE])
    assert interpret(policy, model).status == "out_of_scope"  # the retry named a known one
    assert "canteen" in model.prompts[1]  # the retry carried the error
    bad = FakeModel([json.dumps({"template_id": "canteen", "reason": "x"})] * 2)
    draft = interpret(policy, bad)
    assert draft.status == "invalid" and draft.errors[0].startswith("template pick:")
    assert len(bad.prompts) == 2  # no fill after a failed pick


def test_fill_gets_what_is_left_of_the_shared_budget(policy) -> None:
    import time

    class SlowPick(FakeModel):
        def complete(self, prompt, max_tokens, timeout_s=None):
            if not self.prompts:
                time.sleep(0.5)  # the pick takes half a second
            return super().complete(prompt, max_tokens, timeout_s)

    model = SlowPick([PICK, json.dumps(VALID)])
    interpret(policy, model)
    pick_budget, fill_budget = model.timeouts
    assert pick_budget == pytest.approx(55.0, abs=0.1)
    assert fill_budget == pytest.approx(54.5, abs=0.1)


def test_out_of_scope_cannot_be_approved(store, policy) -> None:
    from rulestorm.policy import BlueprintInvalid, approve_blueprint, create_blueprint

    record = create_blueprint(store, policy.id, FakeModel([NONE]))
    assert store.get_blueprint(record.id).status == "out_of_scope"
    with pytest.raises(BlueprintInvalid):
        approve_blueprint(store, record.id)


def test_daily_cap_zero_gives_429_before_any_model_call(store, policy, monkeypatch) -> None:
    monkeypatch.setenv("MAX_BLUEPRINT_CALLS_PER_DAY", "0")
    model = FakeModel([PICK, json.dumps(VALID)])
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_blueprint_model] = lambda: model
    try:
        response = TestClient(app).post("/api/blueprints", json={"policy_id": policy.id})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 429
    assert model.prompts == []  # refused before any model call
    assert store.daily_usage()["blueprint_calls"] == 0


def test_daily_cap_counts_each_request_and_stops_at_the_cap(store, policy, monkeypatch) -> None:
    from rulestorm.policy import DailyCapReached, create_blueprint

    monkeypatch.setenv("MAX_BLUEPRINT_CALLS_PER_DAY", "2")
    for _ in range(2):
        create_blueprint(store, policy.id, FakeModel([NONE]))
    with pytest.raises(DailyCapReached):
        create_blueprint(store, policy.id, FakeModel([NONE]))
    assert store.daily_usage()["blueprint_calls"] == 2


def test_daily_cap_is_atomic_across_threads(store) -> None:
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=8) as pool:
        taken = list(pool.map(lambda _: store.take_daily("blueprint_calls", 5), range(20)))
    assert sum(taken) == 5 and store.daily_usage()["blueprint_calls"] == 5


def test_templates_route_lists_scope_and_example_input() -> None:
    response = TestClient(app).get("/api/templates")
    assert response.status_code == 200
    attendance = next(t for t in response.json() if t["id"] == "attendance")
    assert attendance["version"] == 1 and attendance["scope"].startswith("Minimum attendance rules")
    assert "80%" in attendance["example_input"]["text"]
    assert set(attendance["example_input"]) == {"text", "purpose", "environment"}
