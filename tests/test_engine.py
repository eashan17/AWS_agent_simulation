import json
from pathlib import Path

import pytest

from rulestorm.engine import Engine, run_case

CASE = Path(__file__).parent / "cases" / "student_c.json"
STUDENTS = ["commuter", "resident", "working", "family"]


def record(engine: Engine, week: int, session: int, absent: dict[str, set[int]] | None = None) -> None:
    absent = absent or {}
    for student in engine.students:
        engine.propose("faculty", "faculty", "record_attendance", week,
                       student=student, session=session, present=session not in absent.get(student, set()))


@pytest.fixture
def engine() -> Engine:
    """Weeks 1-2 recorded: 'working' misses sessions 1 and 3."""
    e = Engine(80, STUDENTS)
    for session in (1, 2, 3, 4):
        record(e, (session + 1) // 2, session, {"working": {1, 3}})
    return e


def test_student_c_case_prints_expected_lines() -> None:
    lines = run_case(json.loads(CASE.read_text(encoding="utf-8")))
    assert [line.split("  [")[0] for line in lines] == [
        "15/20 = 75.0% (2 exceptions pending)",
        "15/18 = 83.3% (if 2 approved)",
        "queue FIFO: R1,R2 processed, R3 pending (capacity 2)",
        "student edit_attendance: rejected (permission)",
    ]
    assert all(line.split("  [")[1].startswith("E-") for line in lines)


def test_formula_pending_counts_as_absence_approved_and_cancelled_excluded(engine) -> None:
    assert engine.attendance("working").text() == "2/4 = 50.0%"
    engine.propose("student", "working", "submit_exception_request", 2, sessions=[1], reason="shift")
    assert engine.attendance("working").text() == "2/4 = 50.0%"  # pending still counts
    engine.propose("attendance_admin", "attendance_admin", "process_exception_queue", 2, capacity=1)
    assert engine.attendance("working").text() == "2/3 = 66.7%"  # approved is excluded
    engine.propose("faculty", "faculty", "cancel_session", 3, session=5)
    record(engine, 3, 6)
    assert engine.attendance("working").text() == "3/4 = 75.0%"  # cancelled is excluded


def test_queue_is_fifo_within_capacity_and_records_what_it_holds(engine) -> None:
    for session in (1, 3):
        engine.propose("student", "working", "submit_exception_request", 2, sessions=[session], reason="r")
    first = engine.propose("attendance_admin", "attendance_admin", "process_exception_queue", 2, capacity=1)
    assert first.payload["processed"] == ["R1"] and first.payload["pending"] == ["R2"]
    held = engine.events[-1]
    assert held.type == "queue_over_capacity" and held.payload["held"] == ["R2"]
    assert engine.requests["R2"].submitted_event in held.caused_by
    again = engine.propose("attendance_admin", "attendance_admin", "process_exception_queue", 2, capacity=1)
    assert again.type == "action_rejected"  # capacity is per week
    nothing = engine.propose("attendance_admin", "attendance_admin", "process_exception_queue", 3, capacity=0)
    assert nothing.payload["processed"] == [] and engine.requests["R2"].status == "pending"


def test_request_for_an_attended_session_is_rejected_by_the_admin(engine) -> None:
    engine.propose("student", "resident", "submit_exception_request", 2, sessions=[2], reason="r")
    engine.propose("attendance_admin", "attendance_admin", "process_exception_queue", 2, capacity=5)
    assert engine.requests["R1"].status == "rejected"
    assert engine.attendance("resident").text() == "4/4 = 100.0%"


def test_permissions_block_students(engine) -> None:
    before = dict(engine.present)
    edit = engine.propose("student", "working", "edit_attendance", 2, student="working", session=1, present=True)
    approve = engine.propose("student", "working", "process_exception_queue", 2, capacity=5)
    assert (edit.type, edit.payload["reason"]) == ("action_rejected", "permission")
    assert (approve.type, approve.payload["reason"]) == ("action_rejected", "permission")
    assert engine.present == before
    allowed = engine.propose("faculty", "faculty", "edit_attendance", 2, student="working", session=1, present=True)
    assert allowed.type == "attendance_edited"


def test_bad_proposals_are_refused_not_raised(engine) -> None:
    future = engine.propose("faculty", "faculty", "record_attendance", 2, student="working", session=9, present=True)
    missing = engine.propose("faculty", "faculty", "cancel_session", 2)
    assert future.type == missing.type == "action_rejected"
    assert "bad parameters" in missing.payload["reason"]


def test_eligibility_records_figure_and_pending_requests(engine) -> None:
    submitted = engine.propose("student", "working", "submit_exception_request", 2, sessions=[1], reason="r")
    result = engine.propose("exam_officer", "exam_officer", "evaluate_eligibility", 2, student="working")
    assert result.payload["eligible"] is False
    assert result.payload["attendance"]["pct"] == 50.0
    assert result.payload["attendance_if_pending_approved"]["pct"] == 66.7
    assert result.payload["pending_requests"] == ["R1"]
    assert submitted.event_id in result.caused_by
    # the request itself links back to the absence it covers
    assert engine.record_event[("working", 1)] in submitted.caused_by


def test_event_ids_are_unique_and_sequential(engine) -> None:
    ids = [e.event_id for e in engine.events]
    assert ids == [f"E-{n:04d}" for n in range(1, len(ids) + 1)]
