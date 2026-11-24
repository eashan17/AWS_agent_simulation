"""Slices 6a / L7: the LLM people decide when triggered, within a call cap and a phase deadline,
on the general engine with prompts generated from the template.

Uses a routed fake model (replies by person, safe across threads), never real Bedrock.
"""

import copy
import json
import re
import threading
import time
from pathlib import Path

import pytest

from rulestorm import llm
from rulestorm.agents import Agents, run_term
from rulestorm.core.engine import Event
from rulestorm.core.model import load_template
from rulestorm.core.term import DecisionContext, Term
from test_core_term import PROFILES, VALUES as TERM_VALUES

VALUES = {**TERM_VALUES, "exception_rule": "formally approved exceptions"}  # test-only
NOTHING = json.dumps({"actions": [], "reason": "waiting to see", "strategy": "keep going"})


class RoutedModel:
    """Replies by the person named in the prompt. `reply(person, prompt)` returns text or raises."""

    model_id = "fake"

    def __init__(self, reply=lambda person, prompt: NOTHING) -> None:
        self.reply = reply
        self.calls: list[str] = []
        self._lock = threading.Lock()

    def complete(self, prompt: str, max_tokens: int, timeout_s: float | None = None) -> llm.Reply:
        person = re.search(r"agent `(\w+)`", prompt).group(1)
        with self._lock:
            self.calls.append(person)
        return llm.Reply(self.reply(person, prompt), input_tokens=100, output_tokens=20)


@pytest.fixture(scope="module")
def template():
    return load_template("attendance")


def agents_for(template, model, values=VALUES, **kwargs) -> Agents:
    return Agents(template, values, model=model, **kwargs)


def context(person: str, role: str = "student") -> DecisionContext:
    trigger = Event(event_id="E-0001", seq=1, period=3, step=5, type="obstacle", actor="environment")
    return DecisionContext(person=person, role=role, period=3, step=5, triggers=[trigger],
                           profile=PROFILES.get(person))


def decisions(engine):
    return [e for e in engine.events if e.type == "decision"]


def test_decisions_only_for_triggered_people_each_caused_by_its_trigger(template) -> None:
    model = RoutedModel()
    agents = agents_for(template, model, cap=1000)
    seen: list[DecisionContext] = []
    decide = agents.decide_phase
    engine = Term(template, VALUES, lambda contexts: (seen.extend(contexts), decide(contexts))[1]).run()

    recorded = decisions(engine)
    assert seen and len(recorded) == len(seen) == len(model.calls)  # one call per triggered person
    for ctx, event in zip(seen, recorded):
        assert event.actor == ctx.person and event.step == ctx.step
        assert event.caused_by == [t.event_id for t in ctx.triggers] and event.caused_by
    assert all(e.period >= 3 for e in recorded)  # nothing triggers anyone before the week-3 disruption
    assert not {"attendance_admin", "exam_officer"} & set(model.calls)  # rule roles are never asked

    # directly: two triggered people -> exactly two calls and two decisions
    model2 = RoutedModel()
    out = agents_for(template, model2, cap=10).decide_phase([context("working"), context("commuter")])
    assert sorted(model2.calls) == ["commuter", "working"] and [d.person for d in out] == ["commuter", "working"]


def test_cap_of_5_stops_at_exactly_5_calls(template) -> None:
    model = RoutedModel()
    engine, summary = run_term(template, VALUES, agents_for(template, model, cap=5))
    assert len(model.calls) == 5 and summary.llm_calls == 5
    assert summary.cap_hits == 1 and summary.status == "degraded"
    recorded = decisions(engine)
    capped = [d for d in recorded if (d.payload["error"] or "").startswith("CallCapReached")]
    assert len(recorded) - len(capped) == 5  # every decision past the cap is a recorded no-action
    assert all(d.payload["no_action"] for d in capped)
    assert summary.llm_errors == 0  # cap refusals are not model errors


def test_each_llm_person_prompt_holds_its_own_blueprint_profile(template) -> None:
    agents = agents_for(template, RoutedModel(), cap=1000)
    run_term(template, VALUES, agents)
    assert {"commuter", "working", "advisor", "faculty"} <= set(agents.prompts)
    for person, prompts in agents.prompts.items():
        profile = PROFILES[person]
        others = [g for p, prof in PROFILES.items() if p != person for g in prof["goals"] if g not in profile["goals"]]
        for prompt in prompts:
            assert profile["description"] in prompt
            assert all(goal in prompt for goal in profile["goals"])
            assert not any(goal in prompt for goal in others)
            for constraint in profile.get("constraints", []):
                assert constraint in prompt

    # a different blueprint gives different goals in the prompt: they come from the blueprint
    changed = copy.deepcopy(VALUES)
    changed["profiles"]["commuter"]["goals"] = ["marker goal commuter"]
    agents2 = agents_for(template, RoutedModel(), values=changed, cap=1000)
    run_term(template, changed, agents2)
    assert all("marker goal commuter" in p for p in agents2.prompts["commuter"])

    # and no goals are written in the agent or prompt code
    for source in ("rulestorm/agents.py", "rulestorm/prompts.py"):
        text = Path(source).read_text(encoding="utf-8")
        assert not any(goal in text for prof in PROFILES.values() for goal in prof["goals"])


def test_proposals_sorted_by_person_id_whatever_the_finish_order(template) -> None:
    def reply(person, prompt):
        time.sleep({"advisor": 0.3, "commuter": 0.15}.get(person, 0))  # first in ID order finishes last
        return NOTHING

    agents = agents_for(template, RoutedModel(reply), cap=10)
    out = agents.decide_phase([context("working"), context("advisor", "advisor"), context("commuter")])
    assert [d.person for d in out] == ["advisor", "commuter", "working"]


def test_call_slower_than_phase_deadline_is_a_timeout_no_action(template) -> None:
    def reply(person, prompt):
        if person == "working":
            time.sleep(1.5)
        return NOTHING

    agents = agents_for(template, RoutedModel(reply), cap=10, phase_deadline_s=0.3)
    started = time.monotonic()
    out = {d.person: d for d in agents.decide_phase([context("working"), context("commuter")])}
    assert time.monotonic() - started < 1.0  # the phase does not wait for the slow call
    assert out["working"].error.startswith("timeout") and not out["working"].proposals
    assert out["commuter"].error is None and agents.timeouts == 1


def test_run_with_over_10_percent_error_no_actions_ends_degraded(template) -> None:
    def failing(person, prompt):
        if person == "commuter":
            raise RuntimeError("ThrottlingException: slow down")
        return NOTHING

    engine, summary = run_term(template, VALUES, agents_for(template, RoutedModel(failing), cap=1000))
    errors = [d for d in decisions(engine) if d.payload["error"]]
    assert errors and all(d.actor == "commuter" and d.payload["no_action"] for d in errors)
    assert summary.llm_errors == len(errors) and summary.llm_errors / summary.decisions > 0.10
    assert summary.cap_hits == 0 and summary.status == "degraded"

    _, clean = run_term(template, VALUES, agents_for(template, RoutedModel(), cap=1000))
    assert clean.status == "completed" and clean.llm_errors == 0 and clean.cap_hits == 0


def test_proposals_reach_the_engine_and_bad_ones_are_rejected(template) -> None:
    def reply(person, prompt):
        session = int(re.search(r"session (\d+)\)", prompt).group(1))
        if person == "commuter":  # a student trying to edit attendance: refused by permission
            return json.dumps({"actions": [{"action": "edit_attendance",
                                            "params": {"student": "commuter", "session": 1, "present": True}}],
                               "reason": "fix my record"})
        if person == "working":
            return json.dumps({"actions": [{"action": "skip", "params": {"session": session}}],
                               "reason": "the bus is on strike"})
        return NOTHING

    engine, summary = run_term(template, VALUES, agents_for(template, RoutedModel(reply), cap=1000))
    skips = [e for e in engine.events if e.type == "duty_planned" and e.payload["plan"] == "miss"]
    assert skips and all(e.actor == "working" and engine.event(e.caused_by[0]).type == "decision" for e in skips)
    assert summary.rejected and {r.reason for r in summary.rejected if r.agent == "commuter"} == {"permission"}


def test_person_is_told_their_refused_action_and_their_uncovered_absences(template) -> None:
    def early_request(person, prompt):  # asks for an exception before the class has taken place
        session = int(re.search(r"session (\d+)\)", prompt).group(1))
        if person == "commuter" and " obstacle: " in prompt:
            return json.dumps({"actions": [{"action": "submit_exception_request",
                                            "params": {"sessions": [session], "reason": "bus strike"}}],
                               "reason": "the bus is on strike"})
        return NOTHING

    agents = agents_for(template, RoutedModel(early_request), cap=1000)
    run_term(template, VALUES, agents)
    first, after = agents.prompts["commuter"][0], agents.prompts["commuter"][1]
    assert "What happened to the actions" not in first
    assert "refused: submit_exception_request" in after and "precondition: occurrence_recorded" in after
    assert "no exception request covers: session 5" in after  # the late arrival at session 5
    assert "Request rules:" in after and "- travel buffer: 30 min" in after
