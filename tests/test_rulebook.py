"""26 Nov demo fix: every person is told how the rules work, generated from the template and the
approved values (rulestorm/rulebook.py), and a single check's result reaches the person checked.

Before, a student saw only "eligibility is checked in week 6": not that the check runs once at
the end of that week, that its result is final, or that a request still waiting then counts as
missed. The stress test's AI was told all of it; the people living the term were not."""

import pytest

from rulestorm.core.model import load_template
from rulestorm.core.term import simulate
from rulestorm.prompts import render_prompt
from rulestorm.rulebook import rule_lines
from test_core_term import VALUES, decider

HEADING = "How the rules work (the engine applies these exactly):"


@pytest.fixture(scope="module")
def attendance():
    return load_template("attendance")


def test_attendance_states_when_the_check_runs_that_it_is_final_and_what_counts(attendance) -> None:
    text = "\n".join(rule_lines(attendance, {**VALUES, "office_capacity_per_week": 5}))
    for fact in ["Exam eligibility (attendance >= 80%) is checked once, at the end of week 6",
                 "after session 12 is recorded",
                 "The result is final", "an exception request approved later",
                 "3 absences make a student not eligible",
                 "pending or rejected one still counts them as absences",
                 "at most 5 per week, at the end of each week",
                 "one still waiting at the check counts as absences"]:
        assert fact in text, fact


def test_the_figures_follow_the_approved_values(attendance) -> None:
    text = "\n".join(rule_lines(attendance, {**VALUES, "checkpoint_week": 8, "threshold_pct": 75,
                                             "office_capacity_per_week": 2}))
    assert "at the end of week 8, after session 16 is recorded" in text
    assert "attendance >= 75%" in text and "at most 2 per week" in text
    assert "5 absences make a student not eligible" in text  # 11/16 = 68.75% < 75; 12/16 = 75% passes


def test_a_ladder_template_gets_its_steps_from_its_own_values() -> None:
    curfew = load_template("hostel_curfew")
    values = {"warning_at": 3, "inform_guardian_at": 5, "disciplinary_at": 8, "warden_capacity_per_night": 4}
    text = "\n".join(rule_lines(curfew, values))
    assert ("Late-return penalties are checked at the end of every week, counting the whole term: "
            "at 3 late returns, 'warning'; at 5 late returns, 'guardian informed'; at 8 late returns, "
            "'disciplinary'. A step once reached stays.") in text
    assert "at most 4 per night, each night, before that night is recorded" in text
    assert "week 6" not in text and "attendance" not in text


def test_every_prompt_carries_the_block_after_the_request_rules(attendance) -> None:
    rendered = []

    def recording(contexts):
        rendered.extend(render_prompt(attendance, VALUES, c).splitlines() for c in contexts)
        return decider(contexts)

    simulate(attendance, VALUES, recording)
    assert rendered
    for lines in rendered:
        at = lines.index(HEADING)
        assert lines.index("Request rules:") < at < lines.index("What just happened (the events that triggered you):")
        assert any("is checked once, at the end of week 6" in line for line in lines[at:])


def test_a_single_checks_result_reaches_the_person_checked(attendance) -> None:
    seen = []

    def recording(contexts):
        seen.extend((c.person, c.period) for c in contexts for t in c.triggers if t.type == "check_evaluated")
        return decider(contexts)

    engine = simulate(attendance, VALUES, recording)
    checked = {e.payload["person"] for e in engine.events if e.type == "check_evaluated"}
    assert checked == {"commuter", "resident", "working", "family"}
    assert {p for p, _ in seen} == checked
    assert {w for _, w in seen} == {7}  # told at their next decision, the week after the week-6 check
