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
