"""Slice M1: a check's figure is counted one way everywhere, and how an excused occurrence counts
is a policy reading (`remove` or `count_as_met`), on both templates.

The engine, the evidence's recomputation and the search's closeness must give the same figure
under each reading, and the sentences that tell people (rulebook) and the stress test (explore)
how counting works must follow the reading.
"""

import copy
import json
from pathlib import Path

import pytest

from rulestorm import evidence, explore, rulebook, search
from rulestorm.blueprint import values_model
from rulestorm.core.cases import play_case
from rulestorm.core.engine import count_records
from rulestorm.core.model import check_template, load_template, template_path

CASES = Path(__file__).parent / "cases"
READINGS = ("remove", "count_as_met")


def _case(name: str, reading: str) -> dict:
    case = json.loads((CASES / name).read_text(encoding="utf-8"))
    case = copy.deepcopy(case)
    case["values"]["excused_counting"] = reading
    return case


def _checks(engine, person: str) -> list[dict]:
    return [ev.model_dump() for ev in engine.events if ev.type == "check_evaluated" and ev.payload["person"] == person]


# --- the one counting function --------------------------------------------------------------------


def test_count_records_reads_excused_as_the_policy_says():
    records = {s: "missed" for s in range(1, 9)} | {s: "met" for s in range(9, 17)}
    records |= {10: "missed", 12: "missed", 14: "missed"}
    excused = set(range(1, 9))
    removed = count_records("rate", records, set(), excused, "remove")
    counted = count_records("rate", records, set(), excused, "count_as_met")
    assert (removed.met, removed.due, removed.value) == (5, 8, 62.5)
    assert (counted.met, counted.due, counted.value) == (13, 16, 81.2)
    # a cancelled step leaves the count under either reading
    assert count_records("rate", records, {16}, excused, "count_as_met").due == 15
    with pytest.raises(ValueError):
        count_records("rate", records, set(), excused, "ignore")


# --- attendance: engine, evidence and search agree -------------------------------------------------


@pytest.mark.parametrize("reading,figure", [("remove", (5, 8, 62.5)), ("count_as_met", (13, 16, 81.2))])
def test_attendance_engine_evidence_and_search_agree(reading, figure):
    t = load_template("attendance")
    case = _case("excused_reading.json", reading)
    _, engine = play_case(case, t)
    [check] = _checks(engine, "working")
    recorded = check["payload"]["count"]
    assert (recorded["met"], recorded["due"], recorded["value"]) == figure
    assert recorded["reading"] == reading
    assert engine.count("attendance_pct", "working").reading == reading

    events = [ev.model_dump() for ev in engine.events]
    calc = evidence.calculation(check, events, t)
    assert calc.matches_recorded is True
    assert (calc.recorded.met, calc.recorded.due, calc.recorded.value) == figure

    # the search's closeness counts the records itself when a run has no check yet
    values = values_model(t).model_validate(_full_values(t, case["values"])).model_dump()
    no_check = [e for e in events if e["type"] != "check_evaluated"]
    near = next(c for c in search.closeness(t, values, no_check)["checks"] if c["person"] == "working")
    assert near["value"] == figure[2]


def test_the_reading_changes_the_check_result():
    t = load_template("attendance")
    outcomes = {}
    for reading in READINGS:
        _, engine = play_case(_case("excused_reading.json", reading), t)
        [check] = _checks(engine, "working")
        outcomes[reading] = check["payload"]["passed"] if "passed" in check["payload"] else check["payload"]["outcome"]
    assert outcomes["remove"] != outcomes["count_as_met"]


def test_case_without_the_value_reads_as_the_default():
    t = load_template("attendance")
    case = json.loads((CASES / "excused_reading.json").read_text(encoding="utf-8"))
    assert "excused_counting" not in case["values"]
    _, engine = play_case(case, t)
    [check] = _checks(engine, "working")
    assert check["payload"]["count"]["reading"] == "remove"
    assert check["payload"]["count"]["value"] == 62.5


# --- curfew: the same on a tally --------------------------------------------------------------------


@pytest.mark.parametrize("reading", READINGS)
def test_curfew_engine_evidence_and_search_agree(reading):
    t = load_template("hostel_curfew")
    case = _case("curfew_r2.json", reading)
    _, engine = play_case(case, t)
    checks = _checks(engine, "researcher")
    assert checks
    events = [ev.model_dump() for ev in engine.events]
    for check in checks:
        calc = evidence.calculation(check, events, t)
        assert calc.matches_recorded is True
        assert check["payload"]["count"]["reading"] == reading
    final = engine.count("late_returns", "researcher")
    # late on nights 2, 4, 9 and 12; night 8 is excused: it leaves the count, or counts as back on
    # time, so it is never a late return
    assert final.missed == 4
    assert final.due == (len(engine.recorded_steps["return_by_curfew"]) - (1 if reading == "remove" else 0))

    values = values_model(t).model_validate(_full_values(t, case["values"])).model_dump()
    near = [c for c in search.closeness(t, values, events)["checks"] if c["person"] == "researcher"]
    assert near and all(c["value"] == final.value for c in near)


# --- the sentences follow the reading ---------------------------------------------------------------


@pytest.mark.parametrize("name,case,met", [("attendance", "excused_reading.json", "present"),
                                           ("hostel_curfew", "curfew_r2.json", "back on time")])
def test_rulebook_and_explore_sentences_follow_the_reading(name, case, met):
    t = load_template(name)
    lines = {}
    for reading in READINGS:
        values = values_model(t).model_validate(_full_values(t, _case(case, reading)["values"])).model_dump()
        lines[reading] = ("\n".join(rulebook.rule_lines(t, values)), "\n".join(explore.misses_lines(t, values)))
    rules_removed, explore_removed = lines["remove"]
    rules_met, explore_met = lines["count_as_met"]
    assert "excuses its" in rules_removed and f"count as {met}" not in rules_removed
    assert f"count as {met}" in rules_met and "excuses its" not in rules_met
    assert "excuses the" in explore_removed
    assert f"covers as {met}" in explore_met and "excuses the" not in explore_met


# --- the template check and versions -----------------------------------------------------------------


def test_both_templates_are_at_2_and_still_read_1():
    for name in ("attendance", "hostel_curfew"):
        t = load_template(name)
        assert t.version == 2 and t.reads_versions == [1, 2]
        assert all(c.excused_param == "excused_counting" for c in t.counts)


def test_template_check_refuses_a_bad_excused_param():
    raw = json.loads(template_path("attendance").read_text(encoding="utf-8"))
    bad = copy.deepcopy(raw)
    bad["counts"][0]["excused_param"] = "threshold_pct"
    result = check_template(bad)
    assert not result.valid
    assert any("excused_param 'threshold_pct' must be a choice" in e for e in result.errors)


def test_fill_may_leave_the_reading_out():
    t = load_template("attendance")
    case = json.loads((CASES / "excused_reading.json").read_text(encoding="utf-8"))
    values = values_model(t).model_validate(_full_values(t, case["values"])).model_dump()
    assert values["excused_counting"] == "remove"


def _full_values(t, values: dict) -> dict:
    """A case's values plus what the values model needs that a case leaves out."""
    full = dict(values)
    full.setdefault("scope", "per_course")
    full.setdefault("exception_rule", "documented reasons")
    names = {p.name: p for p in t.parameters}
    if "profiles" in names and "profiles" not in full:
        llm = {r.id for r in t.roles if r.llm}
        full["profiles"] = {x.id: {"description": "a person", "goals": ["get by"], "constraints": []}
                            for x in t.people if x.role in llm}
    if "slack_min" in names and "slack_min" not in full:
        attr = next(a for a in t.attributes if a.id == names["slack_min"].attribute)
        full["slack_min"] = {x.id: attr.min for x in t.people if x.role == attr.role}
    return {k: v for k, v in full.items() if k in names}
