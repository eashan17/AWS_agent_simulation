"""26 Nov demo fix: every person is told how the rules work, generated from the template and the
approved values (rulestorm/rulebook.py), and a single check's result reaches the person checked.
Second round the same day, after a critique: what a valid exception is, personal clashes, doing
nothing, the last step before a check, consent, a short-staffed period, "approve all" only when
stated, and what each decider sees. Every rule is checked on both templates, not one scenario.

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
                 "after session 12.", "It is final", "an exception request approved later",
                 "3 absences make a student not eligible",
                 "pending or rejected one still counts them as absences",
                 "up to 5 exception requests per week, first come, first served, at the end of each week",
                 "one still waiting at the check counts as absences"]:
        assert fact in text, fact


def test_the_figures_follow_the_approved_values(attendance) -> None:
    text = "\n".join(rule_lines(attendance, {**VALUES, "checkpoint_week": 8, "threshold_pct": 75,
                                             "office_capacity_per_week": 2}))
    assert "at the end of week 8, after session 16." in text
    assert "attendance >= 75%" in text and "up to 2 exception requests per week" in text
    assert "5 absences make a student not eligible" in text  # 11/16 = 68.75% < 75; 12/16 = 75% passes


def test_a_ladder_template_gets_its_steps_from_its_own_values() -> None:
    curfew = load_template("hostel_curfew")
    values = {"warning_at": 3, "inform_guardian_at": 5, "disciplinary_at": 8, "warden_capacity_per_night": 4}
    text = "\n".join(rule_lines(curfew, values))
    assert ("Late-return penalties are checked at the end of every week, counting the whole term: "
            "at 3 late returns, 'warning'; at 5 late returns, 'guardian informed'; at 8 late returns, "
            "'disciplinary'. A step once reached stays.") in text
    assert "up to 4 late-entry requests per night, first come, first served, each night, before it is recorded" in text
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


# --- second round: general rules, checked on both templates ---------------------------------------

import copy  # noqa: E402

from rulestorm.blueprint import fill_schema  # noqa: E402
from rulestorm.core.term import PhaseDecision, Proposal, Term, dry_run_values  # noqa: E402
from test_blueprint import FILL  # noqa: E402

CURFEW_VALUES = {"warning_at": 3, "inform_guardian_at": 5, "disciplinary_at": 8, "warden_capacity_per_night": 4,
                 "request_timing": "in_advance"}


def test_attendance_tells_what_a_valid_exception_is_and_what_doing_nothing_means(attendance) -> None:
    text = "\n".join(rule_lines(attendance, {**VALUES, "office_capacity_per_week": 5}))
    assert ("The attendance office excuses only absences caused by transport disruption or family emergency; one by "
            "choice when nothing stopped you, or for a work shift clash, is rejected.") in text
    assert "No action for a session means your plan stays: attend class." in text
    assert ("Transport disruption: a delay longer than your travel buffer means you can't attend class in time "
            "(arriving late counts as absent)") in text
    assert "Work shift clash or family emergency: you miss the session only if you choose to." in text
    assert "So a miss in session 12 can't be excused before the check." in text
    assert "never the session in progress (file for it from the next session)" in text
    assert "recorded automatically from what happened (the faculty need not record it), after everyone decides" in text
    assert "A change to your travel buffer applies from the next session." in text


def test_curfew_gets_the_same_rules_in_its_own_words() -> None:
    curfew = load_template("hostel_curfew")
    text = "\n".join(rule_lines(curfew, CURFEW_VALUES))
    assert "A late-entry request needs the guardian's consent before it reaches the warden" in text
    assert "The warden decides each late-entry request seeing what caused each late return it covers." in text
    assert "Family emergency or evening job shift: you miss the night only if you choose to." in text
    assert "can't be back by curfew in time; a shorter one" in text and "counts as late)" not in text
    assert "one still waiting at a check counts as late returns" in text
    assert "can't be excused before the check" not in text  # in_advance: nothing to say about the last step
    for word in ("absence", "attendance office", "exam", "class"):  # (its own "lab session" is fine)
        assert word not in text


def test_edge_values_read_correctly(attendance) -> None:
    one = "\n".join(rule_lines(attendance, {**VALUES, "threshold_pct": 100, "office_capacity_per_week": 0}))
    assert "1 absence makes a student not eligible" in one
    assert "decides no exception requests" in one and "up to 0" not in one


def test_a_short_staffed_period_and_the_causes_reach_the_prompt(attendance) -> None:
    values = {**VALUES, "office_capacity_per_week": 5}
    term = Term(attendance, values, decider)
    term.engine.start_period(5)  # VALUES: the office can process nothing in week 5
    student = term.context("working", 5, 9)
    assert student.capacity_now == {"exception": 0}
    prompt = render_prompt(attendance, values, student)
    assert "- This week the attendance office can decide at most 0 exception requests (normally 5)." in prompt
    assert term.context("working", 4, 7).capacity_now == {}
    faculty = term.context("faculty", 5, 9)
    assert "edit_attendance" in faculty.unavailable_actions  # every mark matches what happened
    assert "- edit_attendance:" not in render_prompt(attendance, values, faculty)
    assert "- cancel_session:" in render_prompt(attendance, values, faculty)


def test_an_llm_decider_sees_what_caused_each_covered_step() -> None:
    curfew = load_template("hostel_curfew")
    values = dry_run_values(curfew)
    term = Term(curfew, values, lambda contexts: [PhaseDecision(person=c.person, reason="test") for c in contexts])
    e = term.engine
    e.start_step(1)
    e.current_step = 1
    resident = next(p.id for p in curfew.people if p.role == "resident")
    e.propose(resident, "request_late_entry", 1, nights=[1], reason="bus")
    e.record_step(1)
    request = next(iter(e.requests.values()))
    covers = e.request_types[request.request_type].covers
    assert e.cause_text(covers, resident, 1).startswith("recorded")
    assert e.cause_text(covers, resident, 2) == "not yet happened"


def test_a_reply_round_still_shows_what_hit_the_step(attendance) -> None:
    seen = []

    def recording(contexts):
        seen.extend(contexts)
        out = []
        for c in contexts:
            hit = any(t.type == "obstacle" for t in c.triggers)
            if c.role == "student" and hit and c.person == "working":
                out.append(PhaseDecision(person=c.person, reason="ask", proposals=[
                    Proposal(action="ask_advisor", params={"message": "can I be excused?"})]))
            elif c.role == "advisor":
                out.append(PhaseDecision(person=c.person, reason="answer", proposals=[
                    Proposal(action="advise_student", params={"student": "working", "advice": "file after it is recorded"})]))
            else:
                out.append(PhaseDecision(person=c.person, reason="nothing"))
        return out

    engine = Term(attendance, VALUES, recording).run()
    hit_steps = {e.step for e in engine.events if e.type == "obstacle" and "working" in e.payload["people"]}
    answers = [c for c in seen if c.person == "working" and c.step in hit_steps
               and any(t.type == "response_given" for t in c.triggers)]
    assert answers, "the advice reached the student in the step the disruption hit"
    assert all(any(t.type == "obstacle" for t in c.triggers) for c in answers)  # the disruption is still shown


def test_approve_all_only_when_the_text_states_it(attendance) -> None:
    schema = fill_schema(attendance)
    assumed = copy.deepcopy(FILL)
    assumed["values"]["decision_rule"] = "approve_all"
    with pytest.raises(Exception, match="only if the user's text states it"):
        schema.model_validate(assumed)
    stated = copy.deepcopy(assumed)
    stated["facts"].append({"field": "decision_rule", "statement": "the text says every request is approved"})
    assert schema.model_validate(stated).values.decision_rule == "approve_all"


def test_the_comparison_measures_count_what_their_labels_say() -> None:
    from rulestorm.comparison import ROWS

    labels = dict(ROWS)
    assert "staff_decisions" not in labels
    assert labels["requests_decided"].startswith("requests decided") and "requests_rejected" in labels
