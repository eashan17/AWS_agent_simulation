"""Slice M4: the engine checks a claimed cause, and every person's prompt says what affects them now.

On both templates: a planned miss (attendance `skip`, curfew `stay_out_late`) may name its cause.
"none" or no cause is the person's own choice; a disruption hitting them this step (by its event ID
or kind) is accepted; one that has ended or hits someone else is refused `claim: not_affecting_you`,
and the person is asked once more in the same step. Free text is never matched.
"""

import pytest

from rulestorm.core.engine import Engine
from rulestorm.core.model import load_template
from rulestorm.core.term import DecisionContext, PhaseDecision, Proposal, Term
from rulestorm.prompts import render_prompt

# (template, the miss action, its step param, the person hit, someone not hit, a disruption kind,
#  a kind hitting nobody, base values)
SETUPS = {
    "attendance": ("skip", "session", "family", "commuter", "transport", "family_emergency", {
        "threshold_pct": 80, "scope": "per_course", "exception_rule": "documented reasons",
        "request_timing": "after_missed", "partial_at_submit": False, "partial_at_decide": False,
        "decision_rule": "approve_if_covered_missed", "office_capacity_per_week": 2, "checkpoint_week": 10,
        "slack_min": {"commuter": 60, "resident": 10, "working": 30, "family": 20},
        "disruptions": [{"kind": "transport", "period": 5, "steps": [1], "people": ["family"], "delay": 90,
                         "description": "train line disruption"}]}),
    "hostel_curfew": ("stay_out_late", "night", "researcher", "intern", "lab_overrun", "family_emergency", {
        "curfew_time": "22:00", "warning_at": 2, "inform_guardian_at": 3, "disciplinary_at": 4,
        "request_timing": "in_advance", "partial_at_submit": False, "partial_at_decide": False,
        "warden_capacity_per_night": 1,
        "slack_min": {"intern": 20, "researcher": 15, "athlete": 30, "local": 45, "fresher": 10, "volunteer": 25},
        "disruptions": [{"kind": "lab_overrun", "period": 2, "steps": [2], "people": ["researcher"], "delay": 60,
                         "description": "experiment overruns"}]}),
}


def _engine(name: str):
    action, step_param, hit, other, kind, unused, values = SETUPS[name]
    t = load_template(name)
    e = Engine(t, values)
    spp = t.calendar.steps_per_period
    d = values["disruptions"][0]
    step = (d["period"] - 1) * spp + d["steps"][0]
    for s in range(1, step + 1):
        e.current_step = s
        events = e.start_step(s)
        if s < step:
            e.record_step(s)
    obstacle = next(ev for ev in events if ev.type == "obstacle")
    return t, e, step, obstacle, action, step_param, hit, other, kind, unused


def _skip(e, person, action, step_param, step, period, cause=None):
    params = {step_param: step, **({"cause": cause} if cause is not None else {})}
    return e.propose(person, action, period, **params)


@pytest.mark.parametrize("name", list(SETUPS))
def test_no_cause_or_none_is_their_own_choice(name) -> None:
    t, e, step, _, action, sp, hit, other, *_ = _engine(name)
    period = e.period_of(step)
    done = _skip(e, other, action, sp, step, period)
    assert done.type == "duty_planned" and done.payload["cause"] == "none"
    done = _skip(e, hit, action, sp, step, period, "none")
    assert done.type == "duty_planned" and done.payload["cause"] == "none"


@pytest.mark.parametrize("name", list(SETUPS))
def test_a_disruption_hitting_them_now_is_accepted_by_id_or_kind(name) -> None:
    t, e, step, obstacle, action, sp, hit, other, kind, _ = _engine(name)
    period = e.period_of(step)
    assert e.valid_causes(hit, step) == ["none", obstacle.event_id, kind]
    done = _skip(e, hit, action, sp, step, period, kind)
    assert done.type == "duty_planned" and done.payload["cause"] == obstacle.event_id


@pytest.mark.parametrize("name", list(SETUPS))
def test_someone_elses_or_an_unused_disruption_is_refused_as_not_affecting_you(name) -> None:
    t, e, step, obstacle, action, sp, hit, other, kind, unused = _engine(name)
    period = e.period_of(step)
    for claim in (kind, obstacle.event_id, unused):
        done = _skip(e, other, action, sp, step, period, claim)
        assert done.type == "action_rejected" and done.payload["reason"] == "claim: not_affecting_you", claim
        assert f"nothing outside your control affects you this {t.calendar.step_label}" in done.payload["detail"]
        assert "Valid causes now: none" in done.payload["detail"]
    assert (t.duties[0].id, other, step) not in e.plans  # a refusal changes nothing


@pytest.mark.parametrize("name", list(SETUPS))
def test_an_ended_disruption_is_refused(name) -> None:
    t, e, step, obstacle, action, sp, hit, other, kind, _ = _engine(name)
    e.record_step(step)
    later = step + 1
    e.current_step = later
    e.start_step(later)
    done = _skip(e, hit, action, sp, later, e.period_of(later), obstacle.event_id)
    assert done.type == "action_rejected" and done.payload["reason"] == "claim: not_affecting_you"


@pytest.mark.parametrize("name", list(SETUPS))
def test_free_text_is_not_matched_and_the_valid_causes_are_listed(name) -> None:
    t, e, step, obstacle, action, sp, hit, *_ = _engine(name)
    done = _skip(e, hit, action, sp, step, e.period_of(step), "road closure")
    assert done.type == "action_rejected" and done.payload["reason"] == "bad parameters: cause"
    assert f"none, {obstacle.event_id}, " in done.payload["detail"] and "'road closure'" in done.payload["detail"]


@pytest.mark.parametrize("name", list(SETUPS))
def test_situation_says_what_hits_them_and_how(name) -> None:
    t, e, step, obstacle, action, sp, hit, other, kind, _ = _engine(name)
    [line] = e.situation(hit, step)
    assert obstacle.event_id in line and f"kind {kind}" in line and "keeps you from it" in line
    assert e.situation(other, step) == [f"nothing outside your control affects you this {t.calendar.step_label}"]


# --- the term asks a refused claimant once more, in the same step ---------------------------------


@pytest.mark.parametrize("name", list(SETUPS))
def test_a_refused_claim_is_asked_again_once_in_the_same_step(name) -> None:
    action, sp, hit, other, kind, unused, values = SETUPS[name]
    t = load_template(name)
    asked: list[tuple[str, int, list[str]]] = []

    def decider(contexts: list[DecisionContext]) -> list[PhaseDecision]:
        out = []
        for c in contexts:
            if c.person != hit:
                out.append(PhaseDecision(person=c.person))
                continue
            asked.append((c.person, c.step, [tr.type for tr in c.triggers]))
            # always lie: claim the disruption that hits nobody
            out.append(PhaseDecision(person=c.person, proposals=[Proposal(action=action, params={sp: c.step, "cause": unused})]))
        return out

    term = Term(t, values, decider)
    engine = term.run()
    step = next(e.step for e in engine.events if e.type == "obstacle")
    at_step = [a for a in asked if a[1] == step]
    assert len(at_step) == 2  # asked, refused, asked once more: never a third time
    assert "action_rejected" in at_step[1][2]  # the refusal is what they were asked about
    decisions = [e for e in engine.events if e.type == "decision" and e.actor == hit and e.step == step]
    rejected = [e for e in engine.events if e.type == "action_rejected" and e.actor == hit and e.step == step]
    assert len(decisions) == 2 and len(rejected) == 2
    assert all(r.payload["reason"] == "claim: not_affecting_you" for r in rejected)


@pytest.mark.parametrize("name", list(SETUPS))
def test_the_prompt_says_your_situation_now_after_the_triggers(name) -> None:
    action, sp, hit, other, kind, unused, values = SETUPS[name]
    t = load_template(name)
    seen: dict[str, str] = {}

    def decider(contexts):
        for c in contexts:
            if c.person == hit and c.triggers and c.triggers[0].type == "obstacle":
                seen.setdefault("prompt", render_prompt(t, values, c))
        return [PhaseDecision(person=c.person) for c in contexts]

    Term(t, values, decider).run()
    prompt = seen["prompt"]
    lines = prompt.split("\n")
    triggers = lines.index("What just happened (the events that triggered you):")
    situation = next(i for i, line in enumerate(lines) if line.startswith("Your situation now ("))
    assert situation > triggers and "keeps you from it" in lines[situation + 1]
    assert '"cause"' in prompt and "leave it out if nothing stops you: it is your own choice" in prompt


def test_the_template_check_refuses_a_cause_on_an_action_that_plans_no_miss() -> None:
    import copy
    import json

    from rulestorm.core.model import check_template, template_path

    raw = json.loads(template_path("attendance").read_text(encoding="utf-8"))
    bad = copy.deepcopy(raw)
    attend = next(a for a in bad["actions"] if a["id"] == "attend")
    attend["params"].append({"name": "cause", "type": "cause", "required": False})
    result = check_template(bad)
    assert not result.valid and any("cause parameter" in e for e in result.errors)
