"""Slice M9: every harm says why it happened, by rules over the records (no Bedrock)."""

import json
from pathlib import Path

import pytest

from rulestorm.cause import classify
from rulestorm.core.cases import case_variant, play_case
from rulestorm.core.model import load_template
from rulestorm.detect import detect, with_cause
from rulestorm.fixture import restore_demo
from rulestorm.ledger import ledger, lines
from rulestorm.runner import findings_of
from rulestorm.store import Store

CASES = Path(__file__).parent / "cases"


def case(name: str) -> dict:
    return json.loads((CASES / name).read_text(encoding="utf-8"))


def played(c: dict):
    t = load_template(c["template"])
    e = play_case(c, t)[1]
    events = [x.model_dump() for x in e.events]
    return t, e.values, events, [f.model_dump() for f in detect("T", events, t, e.values)]


def variant(label: str) -> dict:
    c = case("cause_classes.json")
    return case_variant(c, next(v for v in c["variants"] if v["label"] == label))


def harms(findings: list[dict]) -> list[tuple]:
    return [(f["kind"], f["person"], f["cause_class"]) for f in findings if f["harm"]]


@pytest.mark.parametrize("label, expected", [
    ("forced", [("check_failed", "commuter", "forced")]),
    ("chosen", [("check_failed", "working", "chosen")]),
    ("ai_mistake", [("check_failed", "working", "ai_mistake")]),
    ("process: refused past the deadline", [("check_failed", "commuter", "process")]),
    ("process: rejected for no documentation", [("check_failed", "commuter", "process")]),
    ("process: pending at the check", [("check_failed", "commuter", "process"),
                                       ("pending_at_check", "commuter", "process")]),
    ("trade_off", [("check_failed", "working", "trade_off")]),
])
def test_each_fixed_case_gives_its_cause_class(label, expected) -> None:
    assert harms(played(variant(label))[3]) == expected


def test_the_details_say_why_in_plain_words() -> None:
    by = {label: played(variant(label))[3][0]["cause_detail"] for label in
          ("forced", "chosen", "ai_mistake", "process: refused past the deadline")}
    assert by["forced"] == "3 misses from obstacles over commuter's slack fail the exam eligibility on their own " \
                           "(sessions 1, 2, 3)"
    assert by["chosen"] == "3 skips when nothing affected working were needed to fail the exam eligibility"
    assert by["ai_mistake"] == "a false claim of cause by working was refused at session 6"
    assert by["process: refused past the deadline"].startswith("excusing sessions 1, 2, which a request covered")


def test_a_failed_model_call_in_the_chain_gives_no_reply_and_the_call_cap_does_not() -> None:
    t, values, events, _ = played(variant("chosen"))
    seq = max(e["seq"] for e in events)
    check = next(e for e in events if e["type"] == "check_evaluated" and e["payload"]["person"] == "working")

    def with_decision(error: str) -> list[dict]:
        decision = {"event_id": "E-9999", "seq": check["seq"] - 0.5, "period": 2, "step": 4, "type": "decision",
                    "actor": "working", "payload": {"error": error, "proposals": []}, "caused_by": [],
                    "state_change": None}
        return sorted(events + [decision], key=lambda e: e["seq"]) if seq else events

    timed_out = detect("T", with_decision("ReadTimeoutError: the model took too long"), t, values)
    assert harms([f.model_dump() for f in timed_out]) == [("check_failed", "working", "no_reply")]
    assert timed_out[0].cause_detail == "the model gave no reply for working at session 4"
    capped = detect("T", with_decision("CallCapReached: daily cap"), t, values)
    assert harms([f.model_dump() for f in capped]) == [("check_failed", "working", "chosen")]


def test_a_lost_obligation_is_a_trade_off_shown_with_the_clash_recurrence_and_the_limit() -> None:
    t, values, events, found = played(case("shift_clash.json"))
    lost = next(f for f in found if f["kind"] == "obligation_lost")
    assert lost["cause_class"] == "trade_off"
    clash = lost["trade_off"]["clashes"][0]
    assert clash["kind"] == "work_shift_clash" and clash["limit"] == values["shift_limits"]["working"] == 2
    assert clash["recurs"]
    t2, values2, _, found2 = played(variant("trade_off"))
    failed = found2[0]["trade_off"]["clashes"][0]
    assert failed["recurs"] == [{"period": 1, "until_period": 3, "every": 1, "steps": [1]}]
    book = ledger(t2, values2, played(variant("trade_off"))[2], found2)
    text = "\n".join(lines(t2, book))
    assert "trade_off (3 misses for clashes the policy doesn't excuse fail the exam eligibility)" in text
    assert "work shift clash: recurs weeks 1 to 3, every week, session 1 of the week; limit 2" in text


def test_both_templates_classify_their_harms() -> None:
    assert harms(played(case("curfew_job_shift.json"))[3]) == [("obligation_lost", "intern", "trade_off")]
    assert harms(played(case("curfew_r2.json"))[3]) == [("check_failed", "researcher", "chosen")]
    assert harms(played(case("student_c.json"))[3]) == [("pending_at_check", "commuter", "process"),
                                                         ("check_failed", "working", "chosen")]


def test_a_finding_stored_before_m9_gets_its_class_when_read_and_a_later_approval_does_not_count() -> None:
    store = Store(":memory:")
    restore_demo(store)  # the demo's three misses were all approved, but only after the check
    found = findings_of(store, store.get_run("demo"))
    assert [(f["kind"], f.get("cause_class")) for f in found if f["harm"]] == [("check_failed", "chosen")]
    old = [{k: v for k, v in f.items() if k not in ("cause_class", "cause_detail", "trade_off")} for f in found]
    t = load_template("attendance")
    again = with_cause(old, t, store.get_blueprint(store.get_run("demo")["blueprint_id"]).blueprint.values,
                       store.run_events("demo"))
    assert [f.get("cause_class") for f in again if f["harm"]] == ["chosen"]


def test_without_the_values_only_the_record_rules_run() -> None:
    t, _, events, found = played(variant("forced"))
    assert [f.get("cause_class") for f in classify(t, None, events, found) if f["harm"]] == [None]
