import copy
import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from rulestorm.api import app, get_blueprint_model, get_store
from rulestorm.blueprint import TemplateBlueprint, fill_schema, values_model
from rulestorm.core.model import load_template
from rulestorm.llm import FakeModel
from rulestorm.policy import PolicyInput, create_blueprint, interpret
from rulestorm.store import Store

# Test-only values: replies shaped like real ones, not numbers the app uses.
# Call 1 of every blueprint (slice L6a): the template pick.
PICK = json.dumps({"template_id": "attendance", "reason": "the policy sets a minimum attendance"})
NONE = json.dumps({"template_id": "none", "reason": "the policy is about canteen food, not attendance"})

# Call 2 (slice L6b): the attendance template's values, labelled.
PROFILES = {
    "commuter": {"description": "travels two hours by bus", "goals": ["keep eligibility"], "constraints": ["long commute"]},
    "resident": {"description": "lives in the hostel", "goals": ["good grades"], "constraints": []},
    "working": {"description": "works evening shifts", "goals": ["keep the job"], "constraints": ["fixed work hours"]},
    "family": {"description": "cares for a parent", "goals": ["balance home and study"], "constraints": ["care duties"]},
    "faculty": {"description": "teaches the course", "goals": ["keep participation up"]},
    "advisor": {"description": "advises 40 students", "goals": ["keep advisees eligible"]},
}
FILL = {
    "values": {
        "threshold_pct": 80, "scope": "per_course", "exception_rule": "formally approved exceptions",
        "request_timing": "after_missed", "partial_at_submit": False, "partial_at_decide": False,
        "decision_rule": "approve_if_covered_missed", "office_capacity_per_week": 2, "checkpoint_week": 6,
        "disruptions": [
            {"kind": "transport", "period": 3, "steps": [1], "people": ["commuter", "working"], "delay": 45,
             "description": "bus strike"},
            {"kind": "admin_capacity", "period": 5, "capacity": 1, "description": "staff away"},
        ],
        "profiles": PROFILES,
        "slack_min": {"commuter": 30, "resident": 10, "working": 15, "family": 20},
        # Slice M7b: the fill sets each obligation limit from the profile, labelled an assumption.
        "shift_limits": {"commuter": 2, "resident": 3, "working": 1, "family": 2},
        "care_limits": {"commuter": 3, "resident": 3, "working": 2, "family": 1},
    },
    "facts": [{"field": "threshold_pct", "statement": "80% stated in the policy"}],
    "assumptions": [
        {"field": "shift_limits", "statement": "the working student's job allows few missed shifts"},
        {"field": "care_limits", "statement": "the family student can rarely leave care"},
        {"field": "request_timing", "statement": "the policy is silent; requests after the absence"},
        {"field": "policy", "statement": "the other policy rules are proposed"},
        {"field": "environment", "statement": "a few requests a week, a mid-term check, a strike"},
        {"field": "people", "statement": "profiles and buffers proposed"},
    ],
}

def fill(**changes) -> dict:
    """FILL with some values changed (or removed with None)."""
    reply = copy.deepcopy(FILL)
    for name, value in changes.items():
        if value is None:
            del reply["values"][name]
        else:
            reply["values"][name] = value
    return reply


@pytest.fixture(scope="module")
def template():
    return load_template("attendance")


@pytest.fixture
def store(tmp_path) -> Store:
    return Store(str(tmp_path / "test.db"))


@pytest.fixture
def policy(store):
    return store.save_policy(PolicyInput(text="80% attendance", purpose="y", environment="z"))


# --- slice L6b: the values model, built from the template's parameter specs ---------------------


def test_values_model_is_built_from_the_parameter_specs(template) -> None:
    model = values_model(template)
    assert list(model.model_fields) == [p.name for p in template.parameters]
    schema = model.model_json_schema()
    threshold = schema["properties"]["threshold_pct"]
    assert (threshold["minimum"], threshold["maximum"]) == (50, 100)  # the spec's range
    assert schema["properties"]["request_timing"]["enum"] == ["after_missed", "in_advance"]  # its choices
    profiles = schema["$defs"]["profiles_by_person"]["properties"]
    assert set(profiles) == {"commuter", "resident", "working", "family", "faculty", "advisor"}  # LLM people only
    slack = schema["$defs"]["slack_min_by_person"]["properties"]
    assert set(slack) == {"commuter", "resident", "working", "family"}  # the attribute's role
    assert model.model_validate(FILL["values"]).threshold_pct == 80


@pytest.mark.parametrize("changes, message", [
    ({"threshold_pct": 150}, "threshold_pct"),
    ({"request_timing": "whenever"}, "request_timing"),
    ({"checkpoint_week": 11}, "checkpoint_week"),
    ({"exception_rule": None}, "exception_rule"),
    ({"slack_min": {"commuter": 30}}, "resident"),
    ({"profiles": {**PROFILES, "advisor": {"description": "x", "goals": []}}}, "goals"),
    ({"profiles": {k: v for k, v in PROFILES.items() if k != "faculty"}}, "faculty"),
])
def test_values_outside_the_specs_are_rejected(template, changes, message) -> None:
    with pytest.raises(ValidationError, match=message):
        values_model(template).model_validate(fill(**changes)["values"])


def test_an_unknown_person_in_a_disruption_gives_invalid(template, policy) -> None:
    strike = {"kind": "transport", "period": 3, "steps": [1], "people": ["dean"], "delay": 45, "description": "x"}
    with pytest.raises(ValidationError, match="dean"):
        values_model(template).model_validate(fill(disruptions=[strike])["values"])
    bad = json.dumps(fill(disruptions=[strike]))
    draft = interpret(policy, FakeModel([PICK, bad, bad]))
    assert draft.status == "invalid" and "dean" in draft.errors[0]


def test_the_engine_checks_the_values_too(template) -> None:
    """Rules the schema alone can't express come from the engine: an obstacle may hit only
    people who owe its duty, and needs steps."""
    on_faculty = {"kind": "transport", "period": 3, "steps": [1], "people": ["faculty"], "delay": 45, "description": "x"}
    with pytest.raises(ValidationError, match="don't owe 'attend_class': faculty"):
        values_model(template).model_validate(fill(disruptions=[on_faculty])["values"])
    no_steps = {"kind": "transport", "period": 3, "people": ["commuter"], "delay": 45, "description": "x"}
    with pytest.raises(ValidationError, match="needs steps"):
        values_model(template).model_validate(fill(disruptions=[no_steps])["values"])


def test_labels_are_grouped_by_section_and_cover_every_value(template) -> None:
    schema = fill_schema(template)
    filled = schema.model_validate(FILL)
    bp = TemplateBlueprint(template_id="attendance", template_version=1, values=filled.values.model_dump(),
                           facts=filled.facts, assumptions=filled.assumptions)
    assert bp.label_for(template, "threshold_pct")[0] == "fact"
    assert bp.label_for(template, "request_timing")[1].statement.startswith("the policy is silent")  # its own label
    assert bp.label_for(template, "decision_rule")[1].field == "policy"  # covered by its section
    assert bp.label_for(template, "slack_min")[1].field == "people"

    no_people = copy.deepcopy(FILL)
    no_people["assumptions"] = [a for a in no_people["assumptions"] if a["field"] != "people"]
    with pytest.raises(ValidationError, match="profiles, slack_min"):
        schema.model_validate(no_people)
    unknown = copy.deepcopy(FILL)
    unknown["facts"].append({"field": "scenario.students", "statement": "old path"})
    with pytest.raises(ValidationError, match=r"facts\.1\.field\s+Input should be 'threshold_pct'"):  # slice M7d
        schema.model_validate(unknown)


def test_valid_reply_gives_a_valid_template_blueprint(policy) -> None:
    draft = interpret(policy, FakeModel([PICK, json.dumps(FILL)]))
    assert draft.status == "valid" and draft.errors == []
    assert isinstance(draft.blueprint, TemplateBlueprint)
    assert (draft.blueprint.template_id, draft.blueprint.template_version) == ("attendance", 2)
    assert draft.blueprint.values["request_timing"] == "after_missed"
    assert draft.blueprint.values["disruptions"][0]["people"] == ["commuter", "working"]


def test_unlabelled_value_is_retried_with_the_error(policy) -> None:
    unlabelled = copy.deepcopy(FILL)
    unlabelled["assumptions"] = unlabelled["assumptions"][:1]
    model = FakeModel([PICK, json.dumps(unlabelled), json.dumps(FILL)])
    draft = interpret(policy, model)
    assert draft.status == "valid" and draft.attempts == 3  # pick 1 + fill 2
    assert "checkpoint_week" in model.prompts[2]


def test_invalid_twice_gives_status_invalid_with_errors(policy, store) -> None:
    draft = interpret(policy, FakeModel([PICK, "not json", "{}"]))
    assert draft.status == "invalid" and draft.blueprint is None
    assert draft.attempts == 3 and draft.errors  # pick 1 + fill 2
    saved = store.save_blueprint(draft)
    assert store.get_blueprint(saved.id).status == "invalid"


def test_fill_prompt_comes_from_the_template(policy, template) -> None:
    model = FakeModel([PICK, json.dumps(FILL)])
    interpret(policy, model)
    prompt = model.prompts[1]
    for p in template.parameters:  # slice M7b: a rule reading (in_fill false) stays out of the fill
        assert (f"- {p.name} [{p.kind}]: {p.description}" in prompt) is p.in_fill, p.name
    assert "excused_counting" not in prompt
    assert ("Set each person's shift_limits and care_limits from their profile (how much that obligation matters "
            "to them and how much slack they have); they are labelled for you, so don't label them.") in prompt
    assert "- commuter (Student: long-distance commuter)" in prompt  # people and labels from the template
    assert "policy rules it is silent on" in prompt  # silent rules become labelled assumptions
    assert "Requests can cover only classes already recorded as missed." in prompt  # the choices' sentences


def test_filled_values_run_a_term_on_the_engine(template) -> None:
    from rulestorm.core.term import simulate
    from test_core_term import decider

    values = values_model(template).model_validate(FILL["values"]).model_dump()
    engine = simulate(template, values, decider)
    assert any(e.type == "obstacle" for e in engine.events)
    assert any(e.type == "check_evaluated" for e in engine.events)


def test_post_blueprint_route(store, policy) -> None:
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_blueprint_model] = lambda: FakeModel([PICK, json.dumps(FILL)])
    try:
        http = TestClient(app)
        response = http.post("/api/blueprints", json={"policy_id": policy.id})
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "valid" and body["id"].startswith("B-")
        assert body["blueprint"]["template_id"] == "attendance"
        assert http.post("/api/blueprints", json={"policy_id": "P-missing"}).status_code == 404
    finally:
        app.dependency_overrides.clear()


# --- slice L6a: the template pick, out of scope, the daily blueprint cap, the template list -----


def test_pick_none_gives_out_of_scope_with_the_reason_and_no_fill_call(policy) -> None:
    model = FakeModel([NONE])
    draft = interpret(policy, model)
    assert draft.status == "out_of_scope"
    assert draft.pick_reason == "the policy is about canteen food, not attendance"
    assert draft.blueprint is None and draft.template_id is None
    assert len(model.prompts) == 1  # no fill call
    assert "- attendance: Minimum attendance rules" in model.prompts[0]  # every template's scope line


def test_pick_records_the_template_and_fills_it(policy) -> None:
    model = FakeModel([PICK, json.dumps(FILL)])
    draft = interpret(policy, model)
    assert (draft.status, draft.template_id, draft.template_version) == ("valid", "attendance", 2)
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
        def complete(self, prompt, max_tokens, timeout_s=None, **kw):
            if not self.prompts:
                time.sleep(0.5)  # the pick takes half a second
            return super().complete(prompt, max_tokens, timeout_s, **kw)

    model = SlowPick([PICK, json.dumps(FILL)])
    interpret(policy, model)
    pick_budget, fill_budget = model.timeouts
    assert pick_budget == pytest.approx(55.0, abs=0.1)
    # The fill gets what's left: at most 55 - 0.5 (the pick's half second), and less if building the
    # fill prompt and schema took a moment (about 0.1-0.3 s the first time; the Windows clock is coarse).
    assert 53.5 <= fill_budget <= 54.55


def test_out_of_scope_cannot_be_approved(store, policy) -> None:
    from rulestorm.policy import BlueprintInvalid, approve_blueprint, create_blueprint

    record = create_blueprint(store, policy.id, FakeModel([NONE]))
    assert store.get_blueprint(record.id).status == "out_of_scope"
    with pytest.raises(BlueprintInvalid):
        approve_blueprint(store, record.id)


def test_daily_cap_zero_gives_429_before_any_model_call(store, policy, monkeypatch) -> None:
    monkeypatch.setenv("MAX_BLUEPRINT_CALLS_PER_DAY", "0")
    model = FakeModel([PICK, json.dumps(FILL)])
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
    assert attendance["version"] == 2 and attendance["scope"].startswith("Minimum attendance rules")
    assert "80%" in attendance["example_input"]["text"]
    assert set(attendance["example_input"]) == {"text", "purpose", "environment"}


def test_a_retried_reply_records_why_and_the_tokens(policy) -> None:
    unlabelled = copy.deepcopy(FILL)
    unlabelled["assumptions"] = unlabelled["assumptions"][:1]
    draft = interpret(policy, FakeModel([PICK, json.dumps(unlabelled), json.dumps(FILL)]))
    assert draft.status == "valid" and len(draft.retried) == 1
    assert "label these in facts or assumptions" in draft.retried[0]
    assert draft.input_tokens > 0 and draft.output_tokens > 0


def test_profiles_stay_short_so_a_fill_leaves_room_for_its_retry() -> None:
    """At most 2 goals and 2 constraints each: curfew fills with 8 profiles took 40-44 s before."""
    from pydantic import ValidationError

    from rulestorm.blueprint import PersonProfile

    PersonProfile(description="x", goals=["a", "b"], constraints=["c", "d"])
    for extra in ({"goals": ["a", "b", "c"]}, {"goals": ["a"], "constraints": ["c", "d", "e"]}):
        with pytest.raises(ValidationError):
            PersonProfile(description="x", **extra)


# --- slice M7b: obligation limits set from the profile, labelled assumptions ------------------------


def test_each_limit_must_be_set_by_the_fill_and_is_labelled_an_assumption_for_it(store, policy) -> None:
    with pytest.raises(ValidationError, match="set shift_limits for every person from their profile"):
        fill_schema(load_template("attendance")).model_validate(fill(shift_limits=None))
    unlabelled = copy.deepcopy(FILL)
    unlabelled["assumptions"] = [a for a in unlabelled["assumptions"] if not a["field"].endswith("_limits")]
    unlabelled["facts"].append({"field": "shift_limits", "statement": "two shifts"})  # replaced: no text states it
    record = create_blueprint(store, policy.id, FakeModel([PICK, json.dumps(unlabelled)]))
    bp = record.blueprint
    assert record.status == "valid" and not [x for x in bp.facts if x.field == "shift_limits"]
    assert [x.statement for x in bp.assumptions if x.field.endswith("_limits")] == [
        "AI-set from each profile: commuter 2, resident 3, working 1, family 2",
        "AI-set from each profile: commuter 3, resident 3, working 2, family 1"]


def test_the_blueprint_prints_each_persons_limits_labelled_an_assumption(store, policy) -> None:
    from rulestorm.cli import describe_blueprint

    record = create_blueprint(store, policy.id, FakeModel([PICK, json.dumps(FILL)]))
    text = "\n".join(describe_blueprint(record))
    assert ("  shift_limits: commuter 2, resident 3, working 1, family 2  "
            "[assumption: AI-set from each profile: commuter 2, resident 3, working 1, family 2]") in text
    assert "  care_limits: commuter 3, resident 3, working 2, family 1  [assumption: AI-set" in text
    assert record.blueprint.values["excused_counting"] == "remove"  # a reading: its default, not the fill's


def test_a_label_naming_the_limits_is_dropped_not_refused(store, policy) -> None:
    reply = copy.deepcopy(FILL)
    reply["assumptions"].append({"field": "shift_limits and care_limits", "statement": "from the profiles"})
    record = create_blueprint(store, policy.id, FakeModel([PICK, json.dumps(reply)]))
    assert record.status == "valid"
    assert [x.field for x in record.blueprint.assumptions if "limits" in x.field] == ["shift_limits", "care_limits"]
