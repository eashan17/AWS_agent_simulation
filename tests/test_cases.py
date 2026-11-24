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


# --- slice L9d fixes: consent and decision in the same night, and room for every request -----------

STRUCK = ["intern", "athlete", "researcher", "local"]


def curfew_values(curfew) -> dict:
    from rulestorm.core.term import dry_run_values

    return {**dry_run_values(curfew), "warden_capacity_per_night": 4, "request_timing": "in_advance",
            "partial_at_submit": False, "partial_at_decide": False,
            "warning_at": 3, "inform_guardian_at": 5, "disciplinary_at": 8,
            "slack_min": {"intern": 30, "researcher": 15, "athlete": 25, "local": 40, "fresher": 60, "volunteer": 10},
            "disruptions": [{"kind": "transport_delay", "period": 3, "steps": [2], "people": STRUCK, "delay": 45,
                             "description": "roadworks"}]}


def test_four_requests_in_one_night_are_consented_and_decided_before_it_is_recorded(curfew) -> None:
    """Run L-7cd2c05d: four residents asked on night 12; the guardian could name only 3 (the old
    3-action cap) and was asked a night late. Now: the same night, all four, through the agents."""
    import re

    from rulestorm.agents import Agents
    from rulestorm.core.term import Term
    from test_agents import NOTHING, RoutedModel

    def ids(prompt: str, heading: str) -> list[str]:
        block = prompt.split(heading, 1)[1].split("\n\n", 1)[0] if heading in prompt else ""
        return re.findall(r"^- (R\d+) from", block, flags=re.MULTILINE)

    def reply(person, prompt):
        if person in STRUCK and '"type": "obstacle"' not in prompt and "obstacle:" in prompt:
            night = int(re.search(r"night (\d+)\)", prompt).group(1))
            return json.dumps({"actions": [{"action": "request_late_entry",
                                            "params": {"nights": [night], "reason": "roadworks"}}], "reason": "delay"})
        if person == "guardian":
            waiting = ids(prompt, "waiting for your consent:")
            return json.dumps({"actions": [{"action": "give_consent", "params": {"request": r, "consent": True}}
                                           for r in waiting], "reason": "credible delay"})
        if person == "warden":
            offered = ids(prompt, "waiting for your decision now")
            return json.dumps({"actions": [{"action": "decide_permission",
                                            "params": {"request": r, "decision": "approved"}} for r in offered],
                               "reason": "credible delay"})
        return NOTHING

    values = curfew_values(curfew)
    agents = Agents(curfew, values, model=RoutedModel(reply), cap=500)
    engine = Term(curfew, values, agents.decide_phase).run()
    filed = [e for e in engine.events if e.type == "request_filed"]
    assert len(filed) == 4 and {e.step for e in filed} == {12}
    guardian_prompt = next(p for p in agents.prompts["guardian"] if "waiting for your consent" in p)
    assert "Actions you may propose (0 to 4;" in guardian_prompt  # room for all four
    for f in filed:
        rid, person = f.payload["request_id"], f.payload["person"]
        endorsed = next(e for e in engine.events if e.type == "request_endorsed" and e.payload["request_id"] == rid)
        decided = next(e for e in engine.events if e.type == "request_decided" and e.payload["request_id"] == rid)
        recorded = next(e for e in engine.events if e.type == "duty_recorded" and e.step == 12
                        and e.payload["person"] == person)
        assert endorsed.step == decided.step == 12  # the same night it was asked for
        assert f.seq < endorsed.seq < decided.seq < recorded.seq  # all before security records the night
    assert all(engine.count("late_returns", p).value == 0 for p in STRUCK)  # every late night excused


def test_the_action_limit_follows_the_requests_waiting(curfew) -> None:
    from rulestorm.agents import AgentDecision, decision_schema
    from rulestorm.core.term import DecisionContext

    view = {"request_id": "R1", "person": "intern", "steps": [12], "reason": "x", "filed_period": 3}
    c = DecisionContext(person="guardian", role="guardian", period=3, step=12, triggers=[],
                        awaiting_consent=[dict(view, request_id=f"R{i}") for i in range(1, 6)])
    assert c.action_limit() == 5
    assert DecisionContext(person="intern", role="resident", period=1, step=1, triggers=[]).action_limit() == 3
    five = {"actions": [{"action": "give_consent", "params": {}}] * 5, "reason": "r"}
    assert len(decision_schema(5).model_validate(five).actions) == 5
    with pytest.raises(ValueError):
        AgentDecision.model_validate(five)  # everyone else keeps 3
