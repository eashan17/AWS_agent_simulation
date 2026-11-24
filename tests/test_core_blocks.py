"""Slices L9a and L9b: consent steps, escalation ladders and requests decided by an LLM person in
the general engine, on small fixed cases.

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
    """Nothing in core/ names a template's world, the case runner (core/cases.py) included."""
    assert (CORE / "cases.py").exists()
    for path in sorted(CORE.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        for words in (CURFEW_WORDS, ATTENDANCE_WORDS):
            found = re.findall(rf"\b({words})\b", text, flags=re.IGNORECASE)
            assert not found, (path.name, sorted(set(found)))


# --- requests decided by an LLM person (slice L9b) ----------------------------------------------


def raw_decider() -> dict:
    """Attendance with the office as an LLM person deciding each queued request itself."""
    raw = load_template("attendance").model_dump()
    raw["id"] = "decider_test"
    office = next(r for r in raw["roles"] if r["id"] == "attendance_admin")
    office.update(llm=True, rules=[], actions=["decide_exception"])
    raw["request_types"][0].update(decided_by="llm", decision_rule_param=None)
    raw["actions"].append({
        "id": "decide_exception", "label": "decide a queued request",
        "params": [{"name": "request", "type": "request", "hint": "<request id>"},
                   {"name": "decision", "type": "outcome", "hint": "<approved or rejected>"},
                   {"name": "sessions", "type": "step_list", "required": False, "hint": "<sessions approved>"},
                   {"name": "note", "type": "str", "required": False, "hint": "<why>"}],
        "effects": [{"kind": "decide_request", "request_type": "exception"}]})
    raw["triggers"].append({"kind": "decision_awaiting"})
    return raw


@pytest.fixture(scope="module")
def decider() -> Template:
    return Template.model_validate(raw_decider())


def two_requests(t: Template, capacity: int = 1) -> Engine:
    """working files for step 1, then commuter for step 2: R1 is first in the queue."""
    e = Engine(t, {**VALUES, "office_capacity_per_week": capacity})
    miss(e, "working", 1)
    miss(e, "commuter", 2)
    e.propose("working", "submit_exception_request", 1, sessions=[1], reason="shift")
    e.propose("commuter", "submit_exception_request", 1, sessions=[2], reason="bus")
    return e


def test_the_decider_shape_passes_the_template_check_and_dry_run() -> None:
    result = check_template(raw_decider())
    assert result.valid, result.errors


def test_an_llm_queue_needs_its_trigger_and_only_its_handler_may_decide() -> None:
    raw = raw_decider()
    raw["triggers"] = [t for t in raw["triggers"] if t["kind"] != "decision_awaiting"]
    raw["roles"][0]["actions"].append("decide_exception")
    errors = check_template(raw).errors
    assert any("needs the decision_awaiting trigger" in e for e in errors), errors
    assert any("only its handled_by role 'attendance_admin' may take it" in e for e in errors), errors


def test_the_engine_enforces_capacity_order_and_the_allowed_outcomes(decider) -> None:
    e = two_requests(decider, capacity=1)
    outside = e.propose("attendance_admin", "decide_exception", 1, request="R1", decision="approved")
    assert outside.payload["reason"] == "precondition: decision_slot"  # only at the queue's slot
    opened = e.open_decisions("exception", 1)
    assert opened.payload["offered"] == ["R1"] and opened.payload["held"] == ["R2"]  # first come, first served
    beyond = e.propose("attendance_admin", "decide_exception", 1, request="R2", decision="approved")
    assert beyond.type == "action_rejected" and beyond.payload["reason"] == "capacity"
    assert beyond.payload["detail"] == ("only 1 exception requests can be decided this week, first come "
                                        "first served; R2 is not among them")
    odd = e.propose("attendance_admin", "decide_exception", 1, request="R1", decision="maybe later")
    assert odd.payload["reason"] == "bad parameters: outcome"
    assert odd.payload["detail"] == "decision must be one of approved, rejected, not 'maybe later'"
    done = e.propose("attendance_admin", "decide_exception", 1, request="R1", decision="rejected", note="no proof")
    assert done.type == "request_decided" and done.payload["rule"] == "llm" and done.payload["reason"] == "no proof"
    assert opened.event_id in done.caused_by and e.requests["R1"].status == "rejected"
    twice = e.propose("attendance_admin", "decide_exception", 1, request="R1", decision="approved")
    assert twice.payload["reason"] == "precondition: awaiting_decision"
    closed = e.close_decisions("exception")
    assert closed.payload["processed"] == ["R1"] and closed.payload["pending"] == ["R2"]
    held = e.events[-1]
    assert held.type == "queue_over_capacity" and held.payload["held"] == ["R2"]
    assert e.requests["R2"].status == "pending"


def test_partial_approval_only_when_the_policy_allows_it(decider) -> None:
    for partial, expected in ((False, "precondition: partial_at_decide"), (True, None)):
        e = Engine(decider, {**VALUES, "office_capacity_per_week": 2, "partial_at_decide": partial})
        miss(e, "working", 1)
        miss(e, "working", 2)
        e.propose("working", "submit_exception_request", 1, sessions=[1, 2], reason="shift")
        e.open_decisions("exception", 1)
        out = e.propose("attendance_admin", "decide_exception", 1, request="R1", decision="approved", sessions=[2])
        if expected:
            assert out.payload["reason"] == expected
        else:
            assert out.type == "request_decided" and e.requests["R1"].approved_steps == [2]
            assert e.requests["R1"].rejected_steps == [1]


def scripted_term(t: Template, office, capacity: int = 2) -> tuple[Engine, list[DecisionContext]]:
    """Students file for each recorded absence (the L4 scripted people); the office decides by `office`."""
    from test_core_term import scripted

    seen: list[DecisionContext] = []

    def decide(contexts):
        seen.extend(contexts)
        students = [scripted(c) for c in contexts if c.role != "attendance_admin"]
        handlers = [c for c in contexts if c.role == "attendance_admin"]
        return students + (office(handlers) if handlers else [])

    engine = Term(t, {**VALUES, "office_capacity_per_week": capacity}, decide).run()
    return engine, seen


def test_the_deciders_prompt_lists_the_queued_requests_and_the_allowed_outcomes(decider) -> None:
    from rulestorm.prompts import render_prompt

    def approve_all(contexts):
        return [PhaseDecision(person=c.person, reason="covered", proposals=[
            Proposal(action="decide_exception", params={"request": r["request_id"], "decision": "approved"})
            for r in c.offered_requests]) for c in contexts]

    engine, seen = scripted_term(decider, approve_all, capacity=1)
    first = next(c for c in seen if c.role == "attendance_admin")
    assert [t.type for t in first.triggers] == ["decision_awaiting"]
    prompt = render_prompt(decider, {**VALUES, "office_capacity_per_week": 1}, first)
    offered = first.offered_requests[0]
    assert ("Exception requests waiting for your decision now, first come first served (you can decide at most "
            "1 now; the rest wait):") in prompt
    assert f"- {offered['request_id']} from {offered['person']}: session {offered['steps'][0]} " in prompt
    assert "Allowed outcomes: approved, rejected. Approve or reject each exception request whole." in prompt
    assert "- decide_exception: params" in prompt
    # the office decided, through its own decision, only requests it was offered
    decided = [ev for ev in engine.events if ev.type == "request_decided"]
    assert decided and all(engine.event(ev.caused_by[0]).actor == "attendance_admin" for ev in decided)
    # only the office was asked at its slot: nobody else decided in that phase
    for ev in engine.events:
        if ev.type == "decision_awaiting" and ev.payload["offered"]:
            phase = [d for d in engine.events if d.type == "decision" and ev.event_id in d.caused_by]
            assert [d.actor for d in phase] == ["attendance_admin"]


def test_a_failed_call_leaves_the_request_pending_as_no_action(decider) -> None:
    from rulestorm.agents import Agents
    from test_agents import NOTHING, RoutedModel

    def reply(person, prompt):
        if person == "attendance_admin":
            raise TimeoutError("read timeout")
        return NOTHING

    agents = Agents(decider, {**VALUES, "office_capacity_per_week": 2}, model=RoutedModel(reply), cap=100)
    engine, _ = scripted_term(decider, agents.decide_phase)
    slot = next(ev for ev in engine.events if ev.type == "decision_awaiting" and ev.payload["offered"])
    decision = next(ev for ev in engine.events if ev.type == "decision" and slot.event_id in ev.caused_by)
    assert decision.actor == "attendance_admin" and decision.payload["no_action"]
    assert "TimeoutError" in decision.payload["error"]
    assert not any(ev.type == "request_decided" for ev in engine.events)
    not_made = next(ev for ev in engine.events if ev.type == "decision_not_made")
    assert not_made.payload["held"] == slot.payload["offered"] and decision.event_id in not_made.caused_by
    assert all(engine.requests[r].status == "pending" for r in slot.payload["offered"])
    # the check links the still-pending requests back through the failed decision
    check = next(ev for ev in engine.events if ev.type == "check_evaluated" and ev.payload["pending_requests"])
    assert any(engine.event(c).type == "decision_not_made" for c in check.caused_by)
