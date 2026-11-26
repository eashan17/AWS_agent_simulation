"""Slice M8a: what counts as exceptional, proof and the filing deadline are the policy's own readings,
on both templates (no Bedrock)."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from rulestorm import llm, structured
from rulestorm.blueprint import fill_schema, values_model
from rulestorm.core.cases import case_variant, play_case, run_case
from rulestorm.core.engine import Engine
from rulestorm.core.model import check_template, load_template
from rulestorm.core.term import dry_run_values
from rulestorm.rulebook import rule_lines

CASES = Path(__file__).parent / "cases"
READINGS = ("exceptional_causes", "proof_required", "filing_deadline")


def case(name: str) -> dict:
    return json.loads((CASES / name).read_text(encoding="utf-8"))


def variant(label_start: str) -> dict:
    c = case("readings.json")
    return case_variant(c, next(v for v in c["variants"] if v["label"].startswith(label_start)))


def decided(engine: Engine, request_id: str):
    return next(e for e in engine.events if e.type == "request_decided" and e.payload["request_id"] == request_id)


# --- attendance: the office decides by rule -------------------------------------------------------


def test_a_routine_shift_miss_is_rejected_by_default_and_approved_under_any_documented() -> None:
    t = load_template("attendance")
    by_default = play_case(variant("exceptional_causes unforeseen_only"), t)[1]
    rejected = decided(by_default, "R1")
    assert rejected.payload["decision"] == "rejected"
    assert rejected.payload["reason"] == "session 3: not exceptional: work shift clash is routine and could be planned around"
    lenient = play_case(variant("exceptional_causes any_documented"), t)[1]
    assert decided(lenient, "R1").payload["decision"] == "approved"


def test_with_proof_required_a_cause_that_leaves_no_proof_is_rejected_and_one_that_does_is_approved() -> None:
    e = play_case(variant("proof_required"), load_template("attendance"))[1]
    transport, family = decided(e, "R1"), decided(e, "R2")
    assert transport.payload["decision"] == "rejected"
    assert transport.payload["reason"] == "session 1: no documentation: transport disruption leaves no proof"
    assert family.payload["decision"] == "approved"
    # Without proof required, the same transport absence is a valid reason.
    off = play_case({**variant("proof_required"), "values": {**variant("proof_required")["values"],
                                                             "proof_required": False}}, load_template("attendance"))[1]
    assert decided(off, "R1").payload["decision"] == "approved"


def test_a_request_filed_past_the_deadline_is_refused_with_a_plain_detail() -> None:
    lines = run_case({**case("readings.json"), "variants": [v for v in case("readings.json")["variants"]
                                                             if v["label"].startswith("filing_deadline")]},
                     load_template("attendance"))
    assert lines == ["filing_deadline 1 week: commuter exception request for session 1: refused (precondition: "
                     "within_deadline: session 1 was in week 1, 2 weeks ago; exception requests must be filed "
                     "within 1 week of the session they cover)  [E-0022]"]
    on_time = variant("filing_deadline")
    on_time["requests"] = [dict(on_time["requests"][0], filed_at=3)]  # week 2: 1 week after
    e = play_case(on_time, load_template("attendance"))[1]
    assert decided(e, "R1").payload["decision"] == "approved"


def test_the_readings_case_prints_one_line_per_reading_with_its_decision_and_event_id() -> None:
    lines = run_case(case("readings.json"), load_template("attendance"))
    assert len(lines) == 5 and all(line.rstrip().endswith("]") and "[E-" in line for line in lines)
    assert [line.split(": ", 2)[1].split(" for ")[0] for line in lines] == [
        "working exception request", "working exception request", "commuter exception request",
        "family exception request", "commuter exception request"]


# --- curfew: the warden (an LLM) decides -----------------------------------------------------------


def curfew_case(reading: str | None, steps: list[int] = [3], decision: str = "approved") -> Engine:
    c = case("curfew_job_shift.json")
    c["meets"] = {}
    c["report"] = []
    if reading:
        c["values"]["exceptional_causes"] = reading
    c["requests"] = [{"person": "intern", "steps": steps, "reason": "my evening shift", "consent": True,
                      "decision": decision}]
    return play_case(c, load_template("hostel_curfew"))[1]


def test_by_default_the_warden_still_weighs_a_routine_late_entry() -> None:
    e = curfew_case(None)
    assert e.values["exceptional_causes"] == "decider_judges"
    offered = next(ev for ev in e.events if ev.type == "decision_awaiting" and ev.payload["offered"])
    assert offered.payload["offered"] == ["R1"]
    assert decided(e, "R1").payload["decision"] == "approved" and decided(e, "R1").actor == "warden"


def test_under_unforeseen_only_the_engine_rejects_a_routine_late_entry_without_asking_the_warden() -> None:
    e = curfew_case("unforeseen_only")
    rejected = decided(e, "R1")
    assert rejected.actor == "engine" and rejected.payload["rule"] == "policy_reading"
    assert rejected.payload["reason"] == "night 3: not exceptional: evening job shift is routine and could be planned around"
    assert not any(ev.type == "decision_awaiting" and "R1" in ev.payload["offered"] for ev in e.events)


def test_the_warden_cannot_approve_a_night_the_policy_does_not_excuse() -> None:
    # Night 3 has the shift (excused under any_documented); night 4 has nothing behind it.
    e = curfew_case("any_documented", steps=[3, 4])
    refused = next(ev for ev in e.events if ev.type == "action_rejected" and ev.actor == "warden")
    assert refused.payload["reason"] == "precondition: policy_reading"
    assert refused.payload["detail"] == "this policy doesn't excuse night 4: not exceptional: no disruption stopped them"
    # Approved only once night 4 is recorded on time (nothing left to excuse there), not before.
    assert decided(e, "R1").step > 4


# --- the readings stay readings ----------------------------------------------------------------------


@pytest.mark.parametrize("name", ["student_c.json", "curfew_r2.json", "excused_reading.json", "shift_clash.json",
                                  "curfew_job_shift.json", "claim_false.json"])
def test_the_defaults_give_the_same_result_as_leaving_the_readings_out(name) -> None:
    c = case(name)
    t = load_template(c["template"])
    defaults = {p.name: p.default for p in t.parameters if p.name in READINGS}
    assert run_case({**c, "values": {**c["values"], **defaults}}, t) == run_case(c, t)


def test_out_of_order_ladder_thresholds_are_invalid() -> None:
    t = load_template("hostel_curfew")
    values = {**dry_run_values(t), "warning_at": 3, "inform_guardian_at": 2, "disciplinary_at": 4}
    with pytest.raises(ValueError, match="steps are out of order .*warning_at 3, inform_guardian_at 2"):
        Engine(t, values)
    values_model(t).model_validate({**values, "warning_at": 1})  # in order: valid
    with pytest.raises(ValidationError, match="out of order"):
        values_model(t).model_validate(values)


def test_the_template_check_refuses_decider_judges_on_a_rule_queue_and_a_kind_without_proof() -> None:
    raw = load_template("attendance").model_dump()
    p = next(p for p in raw["parameters"] if p["name"] == "exceptional_causes")
    p["choices"].append("decider_judges")
    raw["disruptions"][0].pop("leaves_proof")
    errors = check_template(raw).errors
    assert any("decided by rule, so 'exceptional_causes' can't offer decider_judges" in e for e in errors), errors
    assert any("an obstacle needs 'leaves_proof'" in e for e in errors), errors


def test_the_readings_stay_out_of_the_fill_and_its_schemas() -> None:
    for name in ("attendance", "hostel_curfew"):
        text = json.dumps(llm.strict_schema(fill_schema(load_template(name))))
        assert not any(r in text for r in READINGS), name
    assert all(line.endswith("-> ok") for line in structured.schema_lines())


def test_the_people_are_told_the_readings_in_force_and_their_filing_window() -> None:
    t = load_template("attendance")
    c = variant("proof_required")
    values = {**c["values"], "filing_deadline": 1}
    lines = rule_lines(t, values, "commuter")
    assert "- Proof is required: transport disruption leaves no proof, so an exception request for one is rejected " \
           "for no documentation." in lines
    assert "- An exception request must be filed within 1 week of the session it covers; a later one is refused." in lines
    assert not any("Proof is required" in line or "filed within" in line for line in rule_lines(t, c["values"] | {
        "proof_required": False}, "commuter"))
    e = play_case({**c, "values": values, "requests": []}, t)[1]
    assert e.person_state("commuter", 3).counts[0].can_file == {1: 4}  # week 1's miss: file by week 2's end
    assert "can still file for session 1 (until session 4)" in "; ".join(e.person_state("commuter", 3).lines(t))
    assert e.person_state("commuter", 5).counts[0].can_file == {}
    curfew = load_template("hostel_curfew")
    strict = rule_lines(curfew, {**case("curfew_job_shift.json")["values"], "exceptional_causes": "unforeseen_only"})
    assert ("- A late-entry request for an evening job shift, or when nothing stopped you, is rejected at once, "
            "before the warden sees it.") in strict
