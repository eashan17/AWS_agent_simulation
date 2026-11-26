"""Slice 8: findings found in a run's events on their own, on any template (fixed inputs, no model)."""

import pytest
from fastapi.testclient import TestClient

from rulestorm.api import app, get_store
from rulestorm.core.model import load_template
from rulestorm.core.term import DecisionContext, PhaseDecision, Proposal, simulate
from rulestorm.detect import detect
from rulestorm.policy import PolicyInput
from rulestorm.store import Store
from test_core_term import STUDENTS, VALUES, decider


@pytest.fixture(scope="module")
def attendance():
    return load_template("attendance")


def events_of(engine) -> list[dict]:
    return [e.model_dump() for e in engine.events]


def assert_own_chain(by_id, finding, person) -> None:
    """From a disruption to the check, and never through another student's own events."""
    chain = finding.chain
    assert chain[-1] == finding.check_event_id and by_id[chain[-1]]["type"] == "check_evaluated"
    assert by_id[chain[0]]["type"] == "obstacle" and person in by_id[chain[0]]["payload"]["people"]
    assert finding.disruptions and finding.disruptions[0] == chain[0]
    assert [by_id[i]["seq"] for i in chain] == sorted(by_id[i]["seq"] for i in chain)
    others = STUDENTS - {person}
    for i in chain:
        e = by_id[i]
        assert e["actor"] not in others and e["payload"].get("person") not in others, (i, e["type"])


# --- (1) the L4 fixed-input term: requests still pending at the checkpoint ----------------------

@pytest.fixture(scope="module")
def l4(attendance):
    events = events_of(simulate(attendance, VALUES, decider))
    return events, detect("L-test", events, attendance)


def test_the_l4_term_has_a_bottleneck_finding_titled_in_the_templates_terms(l4) -> None:
    events, findings = l4
    by_id = {e["event_id"]: e for e in events}
    pending = [f for f in findings if f.kind == "pending_at_check"]
    assert [f.person for f in pending] == ["commuter", "working"]  # the two the strike hit
    assert not [f for f in findings if f.kind == "check_failed"]  # 11 of 12 sessions: still eligible
    for f in pending:
        assert f.title == "Exception-processing bottleneck creates an eligibility risk"
        assert f.check_label == "exam eligibility" and f.outcome == "eligible" and f.period == 6
        assert len(f.pending_requests) == 1 and f.count_if_pending_approved["value"] > f.count["value"]
        assert_own_chain(by_id, f, f.person)
        types = [by_id[i]["type"] for i in f.chain]
        assert "request_filed" in types and "duty_recorded" in types
        assert "queue_over_capacity" in types  # the queue that held the request is in the chain
    working = [by_id[i]["type"] for i in pending[1].chain]
    assert "decision" in working and "duty_planned" in working  # they chose to skip because of it
    assert [f.finding_id for f in findings] == [f"L-test-F{n}" for n in range(1, len(findings) + 1)]


# --- (2) a case built like the 6c run: a strike in weeks 1–3, same-day requests refused ---------

STRIKE = {**VALUES, "checkpoint_week": 3, "office_capacity_per_week": 2,
          "disruptions": [{"kind": "transport", "period": w, "steps": [1], "people": ["commuter", "working"],
                           "delay": 45, "description": "transport strike"} for w in (1, 2, 3)]}


def strike_decider(contexts: list[DecisionContext]) -> list[PhaseDecision]:
    """Hit by the strike, a student skips and asks for an exception the same day, before the
    session is recorded; under `timing: after_missed` that is refused, and they never re-file."""
    out = []
    for c in contexts:
        proposals = []
        if any(t.type == "obstacle" for t in c.triggers) and c.role == "student":
            proposals = [Proposal(action="skip", params={"session": c.step}),
                         Proposal(action="submit_exception_request", params={"sessions": [c.step], "reason": "strike"})]
        out.append(PhaseDecision(person=c.person, proposals=proposals, reason="scripted"))
    return out


def test_the_strike_case_has_a_check_failed_finding_for_each_student_it_hit(attendance) -> None:
    events = events_of(simulate(attendance, STRIKE, strike_decider))
    by_id = {e["event_id"]: e for e in events}
    refused = [e for e in events if e["type"] == "action_rejected"]
    assert len(refused) == 6 and {e["payload"]["reason"] for e in refused} == {"precondition: occurrence_recorded"}
    findings = detect("L-strike", events, attendance)
    failed = [f for f in findings if f.kind == "check_failed"]
    assert [f.person for f in failed] == ["commuter", "working"]  # only the strike-hit students
    assert not [f for f in findings if f.kind == "pending_at_check"]  # nothing waited: it was refused
    for f in failed:
        assert f.title == "Students fall below the attendance threshold and lose exam eligibility"
        assert f.outcome == "not eligible" and f.period == 3 and f.count["value"] == 50.0
        assert_own_chain(by_id, f, f.person)
        assert len(f.disruptions) == 3  # all three strike days
        assert [by_id[i]["type"] for i in f.chain].count("duty_recorded") == 3


def test_a_curfew_ladder_failure_uses_the_curfew_terms() -> None:
    from rulestorm.detect import title

    curfew = load_template("hostel_curfew")
    assert title(curfew, "check_failed") == "Repeated late returns escalate to disciplinary action"
    assert title(curfew, "pending_at_check") == "Late-entry backlog leaves residents facing curfew penalties"


# --- (3) the route: stored at the end of a run, or found from a stored run's events -------------

def test_the_findings_route_finds_a_stored_runs_problems_once(tmp_path, l4) -> None:
    events, _ = l4
    store = Store(str(tmp_path / "test.db"))
    policy = store.save_policy(PolicyInput(text="x", purpose="y", environment="z"))
    store._conn().execute("INSERT INTO blueprints (id, policy_id, model_id, status, record, created_at) "
                          "VALUES ('B-x', ?, 'fake', 'valid', '{}', 'now')", (policy.id,))
    store.create_run("L-old", "B-x", "attendance@1", 10, "fake")
    store.add_events("L-old", events)
    app.dependency_overrides[get_store] = lambda: store
    try:
        http = TestClient(app)
        assert http.get("/api/runs/L-old/findings").json()["findings"] == []  # still running: none yet
        store.update_run("L-old", status="completed")
        first = http.get("/api/runs/L-old/findings").json()
        again = http.get("/api/runs/L-old/findings").json()
        assert first == again and len(first["findings"]) == 2  # worked out once, then read back
        ids = {e["event_id"] for e in events}
        for f in first["findings"]:
            assert set(f["chain"]) <= ids and f["chain"][-1] == f["check_event_id"]
        assert store.get_finding("L-old-F1")["kind"] == "pending_at_check"
        assert http.get("/api/runs/L-missing/findings").status_code == 404
    finally:
        app.dependency_overrides.clear()


# --- (4) a curfew ladder: a request still waiting with no new penalty step is seen at the check --

def curfew_decider(contexts: list[DecisionContext]) -> list[PhaseDecision]:
    """The researcher, hit by a lab overrun, asks for late entry; the guardian consents; the warden
    takes no action, so the request is still waiting after the night is recorded."""
    out = []
    for c in contexts:
        proposals = []
        for t in c.triggers:
            if t.type == "obstacle" and c.person == "researcher":
                proposals.append(Proposal(action="request_late_entry", params={"nights": [c.step], "reason": "lab"}))
            elif t.type == "request_filed" and c.role == "guardian":
                proposals.append(Proposal(action="give_consent", params={"request": t.payload["request_id"],
                                                                         "consent": True}))
        out.append(PhaseDecision(person=c.person, proposals=proposals, reason="scripted"))
    return out


def test_a_curfew_request_still_waiting_before_any_penalty_is_a_bottleneck_finding() -> None:
    import json
    from pathlib import Path

    curfew = load_template("hostel_curfew")
    values = json.loads((Path(__file__).parent / "cases" / "curfew_r2.json").read_text(encoding="utf-8"))["values"]
    values = {**values, "disruptions": [{"kind": "lab_overrun", "period": 1, "steps": [2], "people": ["researcher"],
                                         "delay": 60, "description": "experiment overruns"}]}
    engine = simulate(curfew, values, curfew_decider)
    events = events_of(engine)
    by_id = {e["event_id"]: e for e in events}
    checks = [e for e in events if e["type"] == "check_evaluated"]
    assert checks and {e["payload"]["person"] for e in checks} == {"researcher"}  # only the one who waits
    first = checks[0]["payload"]
    assert checks[0]["period"] == 1 and first["standing"] is None and first["ladder_step"] == 0
    assert "outcome" not in first and first["count"]["value"] == 1 and first["pending_requests"] == ["R1"]
    # where they stand notifies nobody: no decision is ever caused by a check event
    assert not [e for e in events if e["type"] == "decision" and set(e["caused_by"]) & {c["event_id"] for c in checks}]
    findings = detect("L-curfew", events, curfew)
    assert [(f.kind, f.person, f.period) for f in findings] == [("pending_at_check", "researcher", 1)]
    f = findings[0]
    assert f.title == "Late-entry backlog leaves residents facing curfew penalties" and f.outcome == "in good standing"
    types = [by_id[i]["type"] for i in f.chain]
    assert types[0] == "obstacle" and types[-1] == "check_evaluated"
    assert {"request_filed", "decision_not_made"} <= set(types)  # filed, then nobody decided it
    # (the late night itself links to the check through the pending request, which was filed
    # before that night was recorded, so it is not on the chain: IDEAS, linking a record to the
    # request that covers it)


# --- slice M2: near misses and harm ------------------------------------------------------------

NEAR_CASE = {
    "template": "attendance", "focus_person": "working", "count": "attendance_pct",
    # by the week-8 check (16 sessions): commuter 11 / 16 fails; working 13 / 16 passes with 1
    # absence to spare (a 4th would make it 12 / 16 = 75%); family 15 / 16 has 3 to spare
    "outcomes": {"commuter": {"missed": [1, 3, 5, 7, 9]}, "working": {"missed": [10, 12, 14]},
                 "family": {"missed": [2]}},
    "values": {"threshold_pct": 80, "request_timing": "after_missed", "partial_at_submit": False,
               "partial_at_decide": False, "decision_rule": "approve_if_covered_missed",
               "office_capacity_per_week": 2, "checkpoint_week": 8,
               "disruptions": [{"kind": "admin_capacity", "period": 9, "capacity": 2, "description": "usual"}]},
    "report": [],
}


def test_a_pass_with_one_absence_to_spare_is_a_near_miss_not_harm_numbered_after_the_rest(attendance) -> None:
    from rulestorm.core.cases import play_case
    from rulestorm.evidence import evidence

    _, engine = play_case(NEAR_CASE, attendance)
    events = events_of(engine)
    findings = detect("L-near", events, attendance)
    assert [(f.finding_id, f.kind, f.person, f.harm) for f in findings] == [
        ("L-near-F1", "check_failed", "commuter", True),
        ("L-near-F2", "near_threshold", "working", False),
    ]
    near = findings[1]
    assert near.spare == 1 and near.outcome == "eligible" and near.count["value"] == 81.2
    assert near.title == "A student keeps exam eligibility with one absence to spare"
    assert near.chain[-1] == near.check_event_id
    shown = evidence(near.model_dump(), events, attendance)
    assert shown.steps[-1].calculation.matches_recorded is True


def test_a_ladder_near_miss_needs_the_values_and_counts_the_records(attendance) -> None:
    import json
    from pathlib import Path

    from rulestorm.core.cases import play_case

    curfew = load_template("hostel_curfew")
    case = json.loads((Path(__file__).parent / "cases" / "curfew_r2.json").read_text(encoding="utf-8"))
    case["values"]["disruptions"] = case["values"]["disruptions"][:1]  # no night-12 overrun: 3 late returns
    _, engine = play_case(case, curfew)
    events = events_of(engine)
    assert not [f for f in detect("L-c", events, curfew) if f.kind == "near_threshold"]  # no values given
    found = detect("L-c", events, curfew, case["values"])
    near = [f for f in found if f.kind == "near_threshold"]
    assert [(f.person, f.spare, f.harm) for f in near] == [("researcher", 1, False)]
    assert near[0].outcome == "guardian informed"  # where they stand: one before disciplinary
    assert not [f for f in found if f.kind == "check_failed"]


def test_stored_findings_get_harm_when_read() -> None:
    from rulestorm.detect import with_harm

    assert with_harm({"kind": "check_failed"})["harm"] is True
    assert with_harm({"kind": "pending_at_check"})["harm"] is True
    assert with_harm({"kind": "near_threshold"})["harm"] is False


# --- slice M7b: the obligation_lost finding ------------------------------------------------------


@pytest.mark.parametrize("case_file,person", [("shift_clash.json", "working"), ("curfew_job_shift.json", "intern")])
def test_an_obligation_lost_finding_has_no_check_fields_and_ends_at_the_loss(case_file, person) -> None:
    import json
    from pathlib import Path

    from rulestorm.core.cases import play_case

    case = json.loads((Path(__file__).parent / "cases" / case_file).read_text(encoding="utf-8"))
    template = load_template(case["template"])
    events = events_of(play_case(case, template)[1])
    by_id = {e["event_id"]: e for e in events}
    found = detect("L-test", events, template)
    [lost] = [f for f in found if f.kind == "obligation_lost"]
    assert found[-1] is lost  # numbered after the older kinds, so their IDs don't move
    assert lost.person == person and lost.harm and (lost.obligation, lost.lost) == (lost.obligation, "job lost")
    assert (lost.check, lost.check_label, lost.check_event_id, lost.outcome, lost.count) == (None,) * 5
    assert lost.chain[-1] == lost.obligation_event_id and by_id[lost.chain[-1]]["type"] == "obligation_lost"
    assert by_id[lost.chain[0]]["type"] == "obstacle" and lost.disruptions[0] == lost.chain[0]
