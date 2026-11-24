"""Slice L9a: consent steps and escalation ladders in the general engine, on small fixed cases.

The test template is attendance with two additions (written here, not shipped): a consenting
role whose consent every exception request needs, and, in the ladder cases, a tally of missed
records checked every period on a three-step ladder (test thresholds 2/3/4)."""

import copy
import re
from pathlib import Path

import pytest

from rulestorm.core.engine import Engine
from rulestorm.core.model import Template, check_template, load_template
from rulestorm.core.term import DecisionContext, PhaseDecision, Proposal, Term
from test_core_term import VALUES

CORE = Path(__file__).resolve().parent.parent / "rulestorm" / "core"
LADDER_VALUES = {"first_at": 2, "second_at": 3, "third_at": 4}


def raw_shape(ladder: bool = False) -> dict:
    raw = load_template("attendance").model_dump()
    raw["id"] = "blocks_test"
    raw["roles"].append({"id": "consenter", "label": "Consenter", "llm": True, "rules": [],
                         "actions": ["give_consent"]})
    raw["people"].append({"id": "consenter", "role": "consenter", "label": "gives consent to requests"})
    raw["actions"].append({
        "id": "give_consent", "label": "give or refuse consent to a request",
        "params": [{"name": "request", "type": "request", "hint": "<request id>"},
                   {"name": "consent", "type": "bool", "hint": "<true or false>"},
                   {"name": "note", "type": "str", "required": False, "hint": "<why>"}],
        "effects": [{"kind": "endorse", "request_type": "exception"}]})
    raw["request_types"][0]["endorsed_by"] = "consenter"
    raw["triggers"] += [{"kind": "endorsement_awaiting"}, {"kind": "escalation_outcome"}]
    if ladder:
        raw["counts"] = [{"id": "missed_tally", "label": "missed records", "kind": "tally",
                          "duty": raw["duties"][0]["id"], "exclude": ["approved_request"]}]
        raw["checks"] = [{
            "id": "record", "label": "Missed-record ladder", "run_by": "exam_officer", "count": "missed_tally",
            "comparison": "<", "ladder": [
                {"threshold_param": "first_at", "outcome": "warning"},
                {"threshold_param": "second_at", "outcome": "consenter informed", "notifies": ["consenter"]},
                {"threshold_param": "third_at", "outcome": "disciplinary"}]}]
        raw["triggers"] = [t for t in raw["triggers"] if t["kind"] != "count_near_threshold"]
        raw["parameters"] += [{"name": name, "kind": "policy", "type": "int", "min": 1, "max": 20,
                               "description": f"missed records that reach ladder step {i}"}
                              for i, name in enumerate(LADDER_VALUES, 1)]
    return raw


@pytest.fixture(scope="module")
def consent() -> Template:
    return Template.model_validate(raw_shape())


@pytest.fixture(scope="module")
def ladder() -> Template:
    return Template.model_validate(raw_shape(ladder=True))


def miss(engine: Engine, person: str, step: int) -> None:
    engine.current_step = step
    engine.propose(person, "skip", engine.period_of(step), session=step)
    engine.record_step(step)
    engine.current_step = None


# --- consent ------------------------------------------------------------------------------------


def test_both_shapes_pass_the_template_check_and_dry_run() -> None:
    for raw in (raw_shape(), raw_shape(ladder=True)):
        result = check_template(raw)
        assert result.valid, result.errors


def test_only_the_endorsed_by_role_may_take_the_consent_action() -> None:
    raw = raw_shape()
    raw["roles"][0]["actions"].append("give_consent")  # the students too
    errors = check_template(raw).errors
    assert any("only its endorsed_by role 'consenter' may take it" in e for e in errors), errors


def test_a_refused_endorsement_ends_the_request(consent) -> None:
    e = Engine(consent, {**VALUES, "office_capacity_per_week": 2})
    miss(e, "working", 1)
    filed = e.propose("working", "submit_exception_request", 1, sessions=[1], reason="shift")
    assert filed.type == "request_filed" and filed.payload["awaiting_endorsement_by"] == "consenter"
    queued = e.process_queue("exception", 1)
    assert queued.payload["processed"] == [] and queued.payload["pending"] == []  # not queued before consent

    refused = e.propose("consenter", "give_consent", 1, request="R1", consent=False, note="not a good reason")
    assert refused.type == "request_endorsement_refused"
    assert refused.state_change == {"request.R1.endorsement": {"from": "awaiting", "to": "refused"},
                                    "request.R1": {"from": "pending", "to": "rejected"}}
    assert filed.event_id in refused.caused_by
    assert e.requests["R1"].status == "rejected"
    assert e.count("attendance_pct", "working").rejected == ["R1"]  # still counts as missed
    e.process_queue("exception", 2)
    assert not any(ev.type == "request_decided" for ev in e.events)  # ended: never decided

    again = e.propose("consenter", "give_consent", 2, request="R1", consent=True)
    assert again.type == "action_rejected" and again.payload["reason"] == "precondition: awaiting_endorsement"
    assert again.payload["detail"] == "exception request R1 is not waiting for consent"


def test_consent_given_lets_the_request_join_its_queue(consent) -> None:
    e = Engine(consent, {**VALUES, "office_capacity_per_week": 2})
    miss(e, "working", 1)
    e.propose("working", "submit_exception_request", 1, sessions=[1], reason="shift")
    given = e.propose("consenter", "give_consent", 1, request="R1", consent=True)
    assert given.type == "request_endorsed"
    assert given.state_change == {"request.R1.endorsement": {"from": "awaiting", "to": "given"}}
    e.process_queue("exception", 1)
    decided = next(ev for ev in e.events if ev.type == "request_decided")
    assert decided.payload["decision"] == "approved" and e.requests["R1"].status == "approved"


def test_others_cannot_consent_and_unknown_requests_are_refused(consent) -> None:
    e = Engine(consent, VALUES)
    miss(e, "working", 1)
    e.propose("working", "submit_exception_request", 1, sessions=[1], reason="shift")
    student = e.propose("working", "give_consent", 1, request="R1", consent=True)
    assert student.payload["reason"] == "permission"
    unknown = e.propose("consenter", "give_consent", 1, request="R9", consent=True)
    assert unknown.payload["reason"] == "bad parameters: unknown exception request 'R9'"


def test_a_filed_request_asks_the_consenter_in_the_term(consent) -> None:
    """endorsement_awaiting: the filing triggers the endorsed_by person at the next phase."""
    seen: list[DecisionContext] = []

    def decide(contexts: list[DecisionContext]) -> list[PhaseDecision]:
        out = []
        for c in contexts:
            seen.append(c)
            proposals = []
            for t in c.triggers:
                if c.person == "working" and t.type == "duty_recorded":
                    proposals.append(Proposal(action="submit_exception_request",
                                              params={"sessions": [t.step], "reason": "bus strike"}))
                if c.person == "consenter" and t.type == "request_filed":
                    proposals.append(Proposal(action="give_consent",
                                              params={"request": t.payload["request_id"], "consent": False}))
            out.append(PhaseDecision(person=c.person, proposals=proposals, reason="scripted"))
        return out

    engine = Term(consent, {**VALUES, "office_capacity_per_week": 2}, decide).run()
    filed = next(ev for ev in engine.events if ev.type == "request_filed")
    asked = next(c for c in seen if c.person == "consenter")
    assert [t.event_id for t in asked.triggers] == [filed.event_id]
    refused = next(ev for ev in engine.events if ev.type == "request_endorsement_refused")
    decision = engine.event(refused.caused_by[0])
    assert decision.type == "decision" and decision.actor == "consenter" and filed.event_id in decision.caused_by


# --- escalation ladder --------------------------------------------------------------------------


def test_the_ladder_fires_each_step_once_in_order(ladder) -> None:
    e = Engine(ladder, {**VALUES, **LADDER_VALUES})
    fired = []
    for period, misses in ((1, [1, 2]), (2, [3]), (3, [5]), (4, [7])):
        for step in range((period - 1) * 2 + 1, period * 2 + 1):
            if step in misses:
                miss(e, "working", step)
            else:
                e.record_step(step)
        fired += [ev for ev in e.run_checks(period) if ev.payload["person"] == "working"]
    assert [(ev.period, ev.payload["outcome"], ev.payload["count"]["value"]) for ev in fired] == [
        (1, "warning", 2.0), (2, "consenter informed", 3.0), (3, "disciplinary", 4.0)]  # nothing again in period 4
    assert [ev.payload["passed"] for ev in fired] == [True, True, False]  # failed only at the last step
    assert [ev.state_change["check.record.working"] for ev in fired] == [
        {"from": None, "to": "warning"}, {"from": "warning", "to": "consenter informed"},
        {"from": "consenter informed", "to": "disciplinary"}]
    assert all(ev.type == "check_evaluated" for ev in fired)
    # the check links back to the missed records behind it
    missed = {ev.event_id for ev in e.events if ev.type == "duty_recorded" and ev.payload["person"] == "working"
              and ev.payload["outcome"] == "missed" and ev.seq < fired[-1].seq}
    assert set(fired[-1].caused_by) == missed


def test_a_jump_past_several_steps_records_each_in_order(ladder) -> None:
    e = Engine(ladder, {**VALUES, **LADDER_VALUES})
    for step in (1, 2, 3, 4):
        miss(e, "working", step)
    e.record_step(5), e.record_step(6)
    fired = [ev for ev in e.run_checks(3) if ev.payload["person"] == "working"]
    assert [ev.payload["outcome"] for ev in fired] == ["warning", "consenter informed", "disciplinary"]


def test_consenter_informed_triggers_the_consenter(ladder) -> None:
    """A strike makes the working student miss steps 1-4; the second step's outcome lists the
    consenter, so they are asked to decide; the first and last steps list nobody."""
    values = {**VALUES, **LADDER_VALUES, "office_capacity_per_week": 2, "disruptions": [
        {"kind": "transport", "period": p, "steps": [1, 2], "people": ["working"], "delay": 60,
         "description": "strike"} for p in (1, 2)]}
    seen: list[DecisionContext] = []

    def decide(contexts):
        seen.extend(contexts)
        return [PhaseDecision(person=c.person, reason="scripted") for c in contexts]

    engine = Term(ladder, values, decide).run()
    informed = next(ev for ev in engine.events if ev.payload.get("outcome") == "consenter informed")
    told = [c.person for c in seen if informed.event_id in [t.event_id for t in c.triggers]]
    assert told == ["consenter", "working"]  # the role the step lists, and the person concerned
    warning = next(ev for ev in engine.events if ev.payload.get("outcome") == "warning")
    assert [c.person for c in seen if warning.event_id in [t.event_id for t in c.triggers]] == ["working"]


def test_without_the_trigger_in_the_template_an_outcome_triggers_nobody(ladder) -> None:
    raw = raw_shape(ladder=True)
    raw["triggers"] = [t for t in raw["triggers"] if t["kind"] != "escalation_outcome"]
    quiet = Template.model_validate(raw)
    values = {**VALUES, **LADDER_VALUES, "disruptions": [
        {"kind": "transport", "period": 1, "steps": [1, 2], "people": ["working"], "delay": 60, "description": "x"}]}
    seen = []
    Term(quiet, values, lambda cs: seen.extend(cs) or [PhaseDecision(person=c.person) for c in cs]).run()
    assert any(ev.type == "check_evaluated" for ev in Term(quiet, values, lambda cs: [
        PhaseDecision(person=c.person) for c in cs]).run().events)  # the ladder still fired
    assert not any(t.type == "check_evaluated" for c in seen for t in c.triggers)


# --- the general-feature rule --------------------------------------------------------------------

CURFEW_WORDS = r"curfew|hostel|guardian|warden|residents?|nights?|late returns?"
ATTENDANCE_WORDS = r"attendance|exam|students?|absent|absences?|sessions?|weeks?|eligib\w*"


def test_core_has_no_curfew_or_attendance_words() -> None:
    """The case-file loader (`run_case`) keeps attendance keys until slice L9c makes the case
    format general and moves it to core/cases.py; nothing else in core may name a template's world."""
    for path in sorted(CORE.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        if path.name == "engine.py":
            text = text.split("def run_case(", 1)[0]
        for words in (CURFEW_WORDS, ATTENDANCE_WORDS):
            found = re.findall(rf"\b({words})\b", text, flags=re.IGNORECASE)
            assert not found, (path.name, sorted(set(found)))
