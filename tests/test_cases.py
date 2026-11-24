"""Slice L9c: the hostel curfew template and the general case-file format (core/cases.py)."""

import json
from pathlib import Path

import pytest

from rulestorm.core.cases import run_case
from rulestorm.core.model import load_template

CASES = Path(__file__).parent / "cases"


def case(name: str) -> dict:
    return json.loads((CASES / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def curfew():
    return load_template("hostel_curfew")


def test_curfew_is_a_different_structure_not_a_renamed_copy(curfew) -> None:
    attendance = load_template("attendance")
    roles = {r.id: r for r in curfew.roles}
    assert len(curfew.people) == 10 and len(attendance.people) == 8
    assert (curfew.calendar.periods, curfew.calendar.steps_per_period) == (8, 5)
    rt = curfew.request_types[0]
    assert rt.endorsed_by == "guardian" and rt.decided_by == "llm" and roles[rt.handled_by].llm
    assert roles[curfew.duties[0].recorded_by].llm is False  # security records, as a rule only
    check = curfew.checks[0]
    assert curfew.counts[0].kind == "tally" and [s.outcome for s in check.ladder] == [
        "warning", "guardian informed", "disciplinary"]
    assert check.ladder[1].notifies == ["guardian"]


def strip(lines: list[str]) -> list[str]:
    return [line.split("  [")[0] for line in lines]


def test_the_curfew_case_prints_the_ladder_and_the_failed_check_with_its_chain(curfew) -> None:
    lines = run_case(case("curfew_r2.json"), curfew)
    text = strip(lines)
    assert text[:4] == [
        "researcher late returns: 2 → warning",
        "researcher late returns: 3 → guardian informed",
        "researcher late returns: 4 → disciplinary",
        "check failed: late-return penalties for researcher (disciplinary)",
    ]
    assert text[5] == "resident decide_permission: rejected (permission)"
    chain = [step.split(" ") for step in text[4].removeprefix("chain: ").split(" → ")]
    types = [t for _, t in chain]
    assert types[0] == "obstacle" and types[-1] == "check_evaluated"  # from the disruption to the check
    assert types.count("obstacle") == 3 and types.count("duty_recorded") == 4  # nights 2, 4, 9, 12
    assert "duty_planned" in types  # night 9: consent refused, back late anyway
    assert chain[-1][0] == lines[3].split("[")[1].rstrip("]")  # the chain ends at the failed check


def test_the_attendance_case_still_prints_its_four_lines() -> None:
    assert strip(run_case(case("student_c.json"), load_template("attendance"))) == [
        "15/20 = 75.0% (2 exceptions pending)",
        "15/18 = 83.3% (if 2 approved)",
        "queue FIFO: R1,R2 processed, R3 pending (capacity 2)",
        "student edit_attendance: rejected (permission)",
    ]


def test_an_approved_night_is_excused_and_a_refused_consent_is_not(curfew) -> None:
    """Night 8 had consent and the warden's approval; night 9's consent was refused."""
    raw = case("curfew_r2.json")
    raw["requests"][1]["consent"] = True
    raw["requests"][1]["decision"] = "approved"
    # Both nights excused: only nights 2, 4 and 12 are late, so the ladder stops at guardian informed.
    text = strip(run_case(raw, curfew))
    assert text[:3] == ["researcher late returns: 2 → warning", "researcher late returns: 3 → guardian informed",
                        "check failed: none for researcher"]
