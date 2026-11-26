"""Slice M6: routine disruptions recur (`until_period`, `every`) within caps (no Bedrock)."""

import copy
import json
import random

import pytest
from pydantic import ValidationError

from rulestorm import explore, search
from rulestorm.blueprint import fill_prompt, values_model
from rulestorm.cli import describe_blueprint
from rulestorm.core.engine import Engine, expand_disruptions
from rulestorm.core.model import load_template
from rulestorm.core.term import simulate
from rulestorm.llm import FakeModel
from rulestorm.policy import PolicyInput, create_blueprint
from rulestorm.store import Store
from test_blueprint import FILL, PICK, fill
from test_core_term import VALUES, decider

SHIFT = {"kind": "work_shift_clash", "period": 1, "until_period": 10, "steps": [2], "people": ["working"],
         "description": "weekly shift"}


@pytest.fixture
def template():
    return load_template("attendance")


def with_disruptions(*entries) -> dict:
    return {**copy.deepcopy(VALUES), "disruptions": list(entries)}


def obstacles(engine) -> list[tuple]:
    return [(e.period, e.step, e.payload["disruption"], tuple(e.payload["people"]))
            for e in engine.events if e.type == "obstacle"]


def test_an_entry_with_a_range_expands_to_per_period_copies() -> None:
    entry = {**SHIFT, "period": 2, "until_period": 8, "every": 3}
    copies = expand_disruptions([entry])
    assert [d.period for d in copies] == [2, 5, 8]
    assert all(d.until_period is None and d.every == 1 and d.steps == [2] for d in copies)
    assert [d.period for d in expand_disruptions([{**SHIFT, "until_period": None}])] == [1]


def test_a_range_runs_exactly_like_one_entry_per_period(template) -> None:
    ranged = simulate(template, with_disruptions({**SHIFT, "period": 2, "until_period": 4}), decider)
    listed = simulate(template, with_disruptions(*({**SHIFT, "period": w, "until_period": None} for w in (2, 3, 4))),
                      decider)
    assert obstacles(ranged) == obstacles(listed) == [(w, 2 * w, "work_shift_clash", ("working",)) for w in (2, 3, 4)]


def test_a_v1_entry_with_no_range_behaves_as_before(template) -> None:
    v1 = {"kind": "transport", "period": 3, "steps": [1], "people": ["commuter", "working"], "delay": 45,
          "description": "bus strike"}  # stored before M6: no until_period, no every
    values = values_model(template).model_validate(with_disruptions(v1)).model_dump()
    assert values["disruptions"][0] == {**v1, "until_period": None, "every": 1, "capacity": None}
    engine = simulate(template, with_disruptions(v1), decider)
    assert obstacles(engine) == [(3, 5, "transport", ("commuter", "working"))]


def test_more_than_24_occurrences_in_all_is_invalid_with_the_cap(template) -> None:
    family = {**SHIFT, "people": ["family"], "kind": "family_emergency"}
    strike = {"kind": "transport", "period": 1, "until_period": 4, "steps": [1], "people": ["commuter"],
              "delay": 45, "description": "strike"}
    values_model(template).model_validate(with_disruptions(SHIFT, family, strike))  # 10 + 10 + 4 = 24
    with pytest.raises(ValidationError, match="25 times in all; at most 24 week occurrences"):
        values_model(template).model_validate(with_disruptions(SHIFT, family, {**strike, "until_period": 5}))


def test_more_than_12_occurrences_on_one_person_is_invalid_with_the_cap(template) -> None:
    strike = {"kind": "transport", "period": 1, "until_period": 3, "steps": [1], "people": ["commuter", "working"],
              "delay": 45, "description": "strike"}
    with pytest.raises(ValidationError, match=r"working \(13\) too often; at most 12 week occurrences"):
        values_model(template).model_validate(with_disruptions(SHIFT, strike))
    values_model(template).model_validate(with_disruptions(SHIFT, {**strike, "until_period": 2}))  # 12: allowed


def test_a_range_must_end_inside_the_calendar_and_after_it_starts(template) -> None:
    with pytest.raises(ValidationError, match="until_period"):
        values_model(template).model_validate(with_disruptions({**SHIFT, "until_period": 11}))
    with pytest.raises(ValueError, match="before its period"):
        Engine(template, with_disruptions({**SHIFT, "period": 5, "until_period": 3}))


def test_the_fill_is_told_routine_kinds_recur_within_the_caps(template) -> None:
    prompt = fill_prompt(template, "p", "u", "e")
    assert "A routine kind (work_shift_clash) recurs as the person's profile implies" in prompt
    assert "At most 24 week occurrences in all and 12 on one person" in prompt


def test_the_blueprint_cli_shows_the_range_and_the_occurrences(tmp_path) -> None:
    store = Store(str(tmp_path / "test.db"))
    policy = store.save_policy(PolicyInput(text="80% attendance", purpose="y", environment="evening shifts"))
    reply = fill(disruptions=[SHIFT, FILL["values"]["disruptions"][1]])
    record = create_blueprint(store, policy.id, FakeModel([PICK, json.dumps(reply)]))
    text = "\n".join(describe_blueprint(record))
    assert record.status == "valid"
    assert "work_shift_clash weeks 1–10, session 2: working (weekly shift); admin_capacity week 5: capacity 1" in text
    assert "occurrences: 11 of 24" in text


def test_explore_queue_lines_and_the_variant_prompt_show_the_range(template) -> None:
    crunch = {"kind": "admin_capacity", "period": 4, "until_period": 6, "capacity": 0, "description": "staff away"}
    lines = explore.queue_lines(template, with_disruptions(crunch))
    assert "- In the approved environment, weeks 4–6 can decide only 0 (staff away)." in lines
    schema = explore.variants_schema(template).model_json_schema()
    assert "until_period" in json.dumps(schema)


def test_the_search_shows_the_range_and_its_random_scenarios_use_ranges_within_the_caps(template) -> None:
    base = values_model(template).model_validate(VALUES).model_dump()
    child = {**base, "disruptions": base["disruptions"] + [{**SHIFT, "every": 2}]}
    changed = search.changed_env(template, base, child)
    assert changed == [{"parameter": "disruptions", "added": ["weeks 1–10, every 2: weekly shift"], "removed": []}]
    scenarios = [search.random_scenario(template, base, random.Random(seed)) for seed in range(40)]
    assert any(d.get("until_period") for s in scenarios for d in s["disruptions"])
    assert all(len(expand_disruptions(s["disruptions"])) <= 24 for s in scenarios)
