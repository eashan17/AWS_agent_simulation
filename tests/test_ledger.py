"""Slice M3: the ledger of who carried the rule, on both templates, from a run's records alone."""

import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rulestorm import search
from rulestorm.api import app, get_store
from rulestorm.core.cases import play_case
from rulestorm.core.engine import count_value
from rulestorm.core.model import load_template
from rulestorm.fixture import restore_demo
from rulestorm.ledger import ledger, lines, margins, run_ledger
from rulestorm.rulebook import _first_failing
from rulestorm.store import Store

CASES = Path(__file__).parent / "cases"
LADDER_VALUES = {"warning_at": 2, "inform_guardian_at": 3, "disciplinary_at": 4}

RECORDED = CASES / "recorded_demo_L-ff6f0ca8.json"  # the slice-10 demo, kept as known data (slice M11)


def _case(name: str) -> dict:
    return json.loads((CASES / name).read_text(encoding="utf-8"))


def _played(name: str):
    case = _case(name)
    t = load_template(case["template"])
    _, engine = play_case(case, t)
    return t, case["values"], [e.model_dump() for e in engine.events]


@pytest.fixture()
def demo(tmp_path):
    store = Store(str(tmp_path / "ledger.db"))
    restore_demo(store, RECORDED)
    return store


# --- the old closeness, as it was before M3 (the reference the margins must match) -----------------


def _old_closeness_checks(t, values, events) -> list[tuple]:
    counts = {c.id: c for c in t.counts}
    out = []
    for check in t.checks:
        count = counts[check.count]
        exclude = "approved_request" in count.exclude
        records = {}
        for e in events:
            for key, change in (e.get("state_change") or {}).items():
                parts = key.split(".")
                if len(parts) == 4 and parts[0] == "record" and parts[1] == count.duty:
                    records[(parts[2], int(parts[3]))] = change["to"]
        filer = {e["payload"]["request_id"]: e["payload"].get("person") or e["actor"]
                 for e in events if e["type"] == "request_filed"}
        excused = {(filer.get(e["payload"]["request_id"]), s) for e in events if e["type"] == "request_decided"
                   for s in e["payload"].get("approved_steps", [])} if exclude else set()

        def counted(last):
            tally = {}
            for (person, step), outcome in records.items():
                if last is not None and step > last:
                    continue
                if outcome == "missed" and (person, step) in excused:
                    continue
                m = tally.setdefault(person, [0, 0])
                m[0 if outcome == "met" else 1] += 1
            return {p: tuple(v) for p, v in tally.items()}

        if check.ladder is None:
            period, threshold = values[check.at_param], values[check.threshold_param]
            recorded = {e["payload"]["person"]: (e["payload"]["count"]["met"], e["payload"]["count"]["missed"])
                        for e in events if e["type"] == "check_evaluated" and e["payload"]["check"] == check.id}
            tallies = recorded or counted(period * t.calendar.steps_per_period)
        else:
            threshold = values[check.ladder[0].threshold_param]
            tallies = counted(None)
        for person, (met, missed) in tallies.items():
            fails_at = _first_failing(count.kind, check.comparison, threshold, met + missed)
            if fails_at is not None:
                out.append((check.id, person, fails_at - missed, count_value(count.kind, met, missed)))
    return out


@pytest.mark.parametrize("name", ["student_c.json", "excused_reading.json", "curfew_r2.json"])
def test_margins_match_the_old_closeness_on_every_stored_case(name) -> None:
    t, values, events = _played(name)
    values = {**LADDER_VALUES, **values}
    new = [(m.check, m.person, m.spare, m.value) for m in margins(t, values, events)
           if m.ladder_step in (None, 1) and m.spare is not None]
    assert new == _old_closeness_checks(t, values, events)
    assert [(c["check"], c["person"], c["spare"]) for c in search.closeness(t, values, events)["checks"]] == \
        sorted([(c, p, s) for c, p, s, _ in new], key=lambda x: x[2])[:5]


def test_margins_match_the_old_closeness_on_the_demo_run(demo) -> None:
    run = demo.get_run("demo")
    t = load_template("attendance")
    values = demo.get_blueprint(run["blueprint_id"]).blueprint.values
    events = demo.run_events("demo")
    new = [(m.check, m.person, m.spare, m.value) for m in margins(t, values, events) if m.spare is not None]
    assert new == _old_closeness_checks(t, values, events)


# --- the demo: one line per student ------------------------------------------------------------------


def test_the_demo_ledger_has_a_line_per_student(demo) -> None:
    template, book = run_ledger(demo, "demo")
    assert [p.person for p in book.people] == ["commuter", "resident", "working", "family"]
    text = lines(template, book)
    working = next(line for line in text if line.startswith("working: "))
    assert working.startswith("working: 72.7% at week 6 (needs >= 80), 0 to spare; absences 3 (excused 3, "
                              "unexcused 0, pending 0); requests 1 filed, 0 refused, 0 rejected, waited 0 weeks")
    assert [(f["finding_id"], f["harm"]) for f in book.findings] == [("demo-F1", True), ("demo-F2", False),
                                                                     ("demo-F3", False)]
    w = next(p for p in book.people if p.person == "working")
    assert w.checks[0].spare == 0 and w.checks[0].value == 72.7
    assert w.obligations.missed == 0 and w.obligations.lost == 0  # no obligations before M7


# --- absences, requests and integrity ----------------------------------------------------------------


def test_absences_split_into_excused_unexcused_and_pending() -> None:
    t, values, events = _played("excused_reading.json")
    working = next(p for p in ledger(t, values, events).people if p.person == "working")
    assert working.absences.model_dump() == {"total": 11, "excused": 8, "unexcused": 3, "pending": 0}
    assert working.requests.filed == 1 and working.requests.approved == 1

    t, values, events = _played("student_c.json")  # R3 (commuter) still pending at the end
    commuter = next(p for p in ledger(t, values, events).people if p.person == "commuter")
    assert commuter.absences.model_dump() == {"total": 1, "excused": 0, "unexcused": 0, "pending": 1}
    assert commuter.requests.pending == 1 and commuter.requests.waited_max > 0


def test_refusals_are_counted_as_ai_mistakes_with_their_reason() -> None:
    t, values, events = _played("curfew_r2.json")  # the case ends with a refused decide attempt by the intern
    values = {**LADDER_VALUES, **values}
    intern = next(p for p in ledger(t, values, events).people if p.person == "intern")
    assert intern.integrity.refused_actions == 1 and intern.integrity.refused_by_reason == {"permission": 1}
    assert intern.integrity.false_claims == 0
    researcher = next(p for p in ledger(t, values, events).people if p.person == "researcher")
    # R1 approved; R2's consent refused by the guardian, so it counts as rejected
    assert (researcher.requests.filed, researcher.requests.approved, researcher.requests.rejected) == (2, 1, 1)


# --- the curfew: a margin to every ladder step ------------------------------------------------------


def test_the_curfew_ledger_gives_a_margin_to_every_ladder_step() -> None:
    t, values, events = _played("curfew_r2.json")
    values = {**LADDER_VALUES, **values}
    book = ledger(t, values, events)
    text = lines(t, book)
    fresher = next(line for line in text if line.startswith("fresher: "))
    assert "0 late returns counted; 2 to warning, 3 to guardian informed, 4 to disciplinary" in fresher
    researcher = next(p for p in book.people if p.person == "researcher")
    assert [(m.outcome, m.spare) for m in researcher.checks] == [("warning", -2), ("guardian informed", -1),
                                                                  ("disciplinary", 0)]
    assert "reached disciplinary" in next(line for line in text if line.startswith("researcher: "))


def test_the_ledger_reads_the_excused_reading() -> None:
    case = _case("excused_reading.json")
    t = load_template("attendance")
    for reading, value in (("remove", 62.5), ("count_as_met", 81.2)):
        c = copy.deepcopy(case)
        c["values"]["excused_counting"] = reading
        _, engine = play_case(c, t)
        events = [e.model_dump() for e in engine.events]
        working = next(p for p in ledger(t, c["values"], events).people if p.person == "working")
        assert working.checks[0].value == value


# --- the route ---------------------------------------------------------------------------------------


def test_the_ledger_route(demo) -> None:
    app.dependency_overrides[get_store] = lambda: demo
    try:
        http = TestClient(app)
        body = http.get("/api/runs/demo/ledger").json()
        assert set(body) >= {"people", "findings"} and len(body["people"]) == 4
        assert set(body["people"][0]) >= {"checks", "absences", "requests", "obligations", "integrity"}
        assert http.get("/api/runs/L-missing/ledger").status_code == 404
        demo.create_run("L-going", demo.get_run("demo")["blueprint_id"], "attendance@2", 10, "fake")
        assert http.get("/api/runs/L-going/ledger").status_code == 409
    finally:
        app.dependency_overrides.clear()
