"""Slice M7a: a clash with an obligation has stakes on both sides, on both templates (no Bedrock)."""

import copy
import json
from pathlib import Path

import pytest

from rulestorm.blueprint import values_model
from rulestorm.core.cases import play_case
from rulestorm.core.engine import DEFAULT_OBLIGATION, Engine
from rulestorm.core.model import TEMPLATES_DIR, check_template, load_template
from test_core_term import VALUES as TERM_VALUES

CASES = Path(__file__).parent / "cases"
# (case file, the person, the clash kind, the steps the clash falls on)
TEMPLATES = [
    ("shift_clash.json", "working", "work_shift_clash", [4, 6, 8, 10, 12]),
    ("curfew_job_shift.json", "intern", "evening_job_shift", [3, 8, 13, 18, 23]),
]


def case(name: str) -> dict:
    return json.loads((CASES / name).read_text(encoding="utf-8"))


def played(name: str, **changes) -> Engine:
    c = case(name)
    for key, value in changes.items():
        c[key] = value
    return play_case(c, load_template(c["template"]))[1]


def of(engine: Engine, type_: str, person: str) -> list:
    return [e for e in engine.events if e.type == type_ and e.payload.get("person") == person]


@pytest.mark.parametrize("name,person,kind,steps", TEMPLATES)
def test_meeting_the_duty_during_the_clash_misses_the_obligation(name, person, kind, steps) -> None:
    engine = played(name)
    first, second = of(engine, "obligation_missed", person)
    assert (first.step, first.payload["missed"], first.payload["limit"]) == (steps[0], 1, 2)
    assert (second.step, second.payload["missed"]) == (steps[1], 2)
    duty = engine.t.duties[0].id
    assert engine.records[(duty, person, steps[0])] == "met"  # they kept the rule, at the obligation's cost
    clash = engine.event(first.caused_by[0])
    assert clash.type == "obstacle" and clash.payload["disruption"] == kind


@pytest.mark.parametrize("name,person,kind,steps", TEMPLATES)
def test_the_first_time_past_the_limit_loses_it_once_and_the_clash_then_skips_them(name, person, kind, steps) -> None:
    engine = played(name)
    [lost] = of(engine, "obligation_lost", person)
    assert (lost.step, lost.payload["missed"], lost.payload["limit"], lost.payload["lost"]) == (steps[3], 3, 2, "job lost")
    assert lost.state_change == {f"obligation.{kind}.{person}": {"from": "kept", "to": "lost"}}
    clash_steps = [e.step for e in engine.events if e.type == "obstacle" and person in e.payload["people"]]
    assert clash_steps == steps[:4]  # the fifth clash no longer hits them
    assert [e.step for e in of(engine, "obligation_missed", person)] == steps[:2]


@pytest.mark.parametrize("name,person,kind,steps", TEMPLATES)
def test_no_plan_during_the_clash_goes_to_the_obligation_with_a_routine_cause(name, person, kind, steps) -> None:
    engine = played(name)
    duty = engine.t.duties[0].id
    [record] = [e for e in of(engine, "duty_recorded", person) if e.step == steps[2]]
    assert record.payload["plan"] == DEFAULT_OBLIGATION and record.payload["outcome"] == "missed"
    assert record.payload["excusable"] is False  # routine: not a valid reason
    assert engine.event(record.payload["cause"]).payload["disruption"] == kind
    assert engine.record_cause[(duty, person, steps[2])] == (record.payload["cause"], False)
    assert not [e for e in engine.events if e.type.startswith("obligation_") and e.step == steps[2]]


def test_a_planned_miss_during_the_clash_costs_nothing_and_an_emergency_with_no_plan_is_excusable() -> None:
    emergency = {"kind": "family_emergency", "period": 3, "steps": [1], "people": ["family"], "description": "hospital"}
    c = case("shift_clash.json")
    c["values"]["disruptions"].append(emergency)
    c["outcomes"] = {"working": {"missed": [4]}}
    c["meets"] = {"working": [6]}
    engine = play_case(c, load_template("attendance"))[1]
    assert [e.step for e in of(engine, "obligation_missed", "working")] == [6]  # the planned miss at 4 cost nothing
    [family] = [e for e in of(engine, "duty_recorded", "family") if e.step == 5]
    assert family.payload["plan"] == DEFAULT_OBLIGATION and family.payload["excusable"] is True


def test_a_limit_of_zero_loses_it_at_the_first_clash() -> None:
    c = case("shift_clash.json")
    c["values"]["shift_limits"]["working"] = 0
    engine = play_case(c, load_template("attendance"))[1]
    [lost] = of(engine, "obligation_lost", "working")
    assert lost.step == 4 and not of(engine, "obligation_missed", "working")


def test_a_blueprint_without_limits_reads_the_default() -> None:
    template = load_template("attendance")
    c = case("shift_clash.json")
    del c["values"]["shift_limits"]
    engine = play_case(c, template)[1]
    assert of(engine, "obligation_missed", "working")[0].payload["limit"] == 2
    values = values_model(template).model_validate(TERM_VALUES).model_dump()  # no limits in it
    assert values["shift_limits"] == {"commuter": 2, "resident": 2, "working": 2, "family": 2}



def raw_attendance() -> dict:
    return json.loads((TEMPLATES_DIR / "attendance.json").read_text(encoding="utf-8"))


def kind(raw: dict, kind_id: str) -> dict:
    return next(d for d in raw["disruptions"] if d["id"] == kind_id)


def test_the_template_check_refuses_an_obligation_on_a_non_conflict_kind() -> None:
    raw = raw_attendance()
    kind(raw, "transport")["obligation"] = copy.deepcopy(kind(raw, "work_shift_clash")["obligation"])
    assert "disruption 'transport': only a conflict can carry an obligation" in check_template(raw).errors


def test_the_template_check_refuses_a_missing_limit_attribute() -> None:
    raw = raw_attendance()
    kind(raw, "work_shift_clash")["obligation"]["limit_attribute"] = "patience"
    assert "disruption 'work_shift_clash' refers to unknown limit attribute 'patience'" in check_template(raw).errors
    raw = raw_attendance()
    raw["parameters"] = [p for p in raw["parameters"] if p["name"] != "shift_limits"]
    assert ("disruption 'work_shift_clash': no parameter sets the limit attribute 'shift_miss_limit'"
            in check_template(raw).errors)
