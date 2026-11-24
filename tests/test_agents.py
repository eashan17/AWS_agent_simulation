"""Slice 6a: the LLM agents decide when triggered, within a call cap and a phase deadline.

Uses a routed fake model (replies by agent, safe across threads), never real Bedrock.
"""

import json
import re
import threading
import time
from pathlib import Path

from rulestorm import llm
from rulestorm.agents import Agents, run_term
from rulestorm.engine import Event
from rulestorm.simulation import DecisionContext, Term
from test_chain import SCENARIO, blueprint

NOTHING = json.dumps({"actions": [], "reason": "waiting to see", "strategy": "keep going"})


class RoutedModel:
    """Replies by the agent named in the prompt. `reply(agent, prompt)` returns text or raises."""

    model_id = "fake"

    def __init__(self, reply=lambda agent, prompt: NOTHING) -> None:
        self.reply = reply
        self.calls: list[str] = []
        self._lock = threading.Lock()

    def complete(self, prompt: str, max_tokens: int, timeout_s: float | None = None) -> llm.Reply:
        agent = re.search(r"agent `(\w+)`", prompt).group(1)
        with self._lock:
            self.calls.append(agent)
        return llm.Reply(self.reply(agent, prompt), input_tokens=100, output_tokens=20)


def context(agent: str, role: str = "student") -> DecisionContext:
    bp = blueprint()
    profiles = {s.archetype: s for s in bp.scenario.students}
    profiles.update(faculty=bp.scenario.faculty, advisor=bp.scenario.advisor)
    trigger = Event(event_id="E-0001", seq=1, week=3, type="transport_disruption", actor="environment")
    return DecisionContext(agent=agent, role=role, week=3, session=5, triggers=[trigger],
                           profile=profiles.get(agent))


def decisions(engine):
    return [e for e in engine.events if e.type == "decision"]


def test_decisions_only_for_triggered_agents_each_caused_by_its_trigger() -> None:
    model = RoutedModel()
    agents = Agents(blueprint(), model=model, cap=1000)
    seen: list[DecisionContext] = []
    decide = agents.decide_phase
    agents_decide = lambda contexts: (seen.extend(contexts), decide(contexts))[1]  # noqa: E731
    engine = Term(blueprint(), agents_decide).run()

    recorded = decisions(engine)
    assert seen and len(recorded) == len(seen) == len(model.calls)  # one call per triggered agent
    for ctx, event in zip(seen, recorded):
        assert event.actor == ctx.agent and event.payload["session"] == ctx.session
        assert event.caused_by == [t.event_id for t in ctx.triggers] and event.caused_by
    assert all(e.week >= 3 for e in recorded)  # nothing triggers anyone before the week-3 disruption
    assert not {"attendance_admin", "exam_officer"} & set(model.calls)

    # directly: two triggered agents -> exactly two calls and two decisions
    model2 = RoutedModel()
    out = Agents(blueprint(), model=model2, cap=10).decide_phase([context("working"), context("commuter")])
    assert sorted(model2.calls) == ["commuter", "working"] and [d.agent for d in out] == ["commuter", "working"]


def test_cap_of_5_stops_at_exactly_5_calls() -> None:
    model = RoutedModel()
    engine, summary = run_term(blueprint(), Agents(blueprint(), model=model, cap=5))
    assert len(model.calls) == 5 and summary.llm_calls == 5
    assert summary.cap_hits == 1 and summary.status == "degraded"
    recorded = decisions(engine)
    capped = [d for d in recorded if (d.payload["error"] or "").startswith("CallCapReached")]
    assert len(recorded) - len(capped) == 5  # every decision past the cap is a recorded no-action
    assert all(d.payload["no_action"] for d in capped)
    assert summary.llm_errors == 0  # cap refusals are not model errors


def test_each_llm_agent_prompt_holds_its_own_blueprint_profile() -> None:
    model = RoutedModel()
    agents = Agents(blueprint(), model=model, cap=1000)
    run_term(blueprint(), agents)
    bp = blueprint()
    profiles = {s.archetype: s for s in bp.scenario.students}
    profiles.update(faculty=bp.scenario.faculty, advisor=bp.scenario.advisor)
    assert {"commuter", "working", "advisor", "faculty"} <= set(agents.prompts)
    for agent, prompts in agents.prompts.items():
        profile = profiles[agent]
        others = [g for a, p in profiles.items() if a != agent for g in p.goals if g not in profile.goals]
        for prompt in prompts:
            assert profile.description in prompt
            assert all(goal in prompt for goal in profile.goals)
            assert not any(goal in prompt for goal in others)
            for constraint in getattr(profile, "constraints", []):
                assert constraint in prompt

    # a different blueprint gives different goals in the prompt: they come from the blueprint
    changed = [{**s, "goals": [f"marker goal {s['archetype']}"]} for s in SCENARIO["students"]]
    agents2 = Agents(blueprint(students=changed), model=RoutedModel(), cap=1000)
    run_term(blueprint(students=changed), agents2)
    assert all("marker goal commuter" in p for p in agents2.prompts["commuter"])

    # and no goals are written in the agent code
    source = Path("rulestorm/agents.py").read_text(encoding="utf-8")
    all_goals = [g for p in profiles.values() for g in p.goals]
    assert not any(goal in source for goal in all_goals)


def test_proposals_sorted_by_agent_id_whatever_the_finish_order() -> None:
    def reply(agent, prompt):
        time.sleep({"advisor": 0.3, "commuter": 0.15}.get(agent, 0))  # first in ID order finishes last
        return NOTHING

    agents = Agents(blueprint(), model=RoutedModel(reply), cap=10)
    out = agents.decide_phase([context("working"), context("advisor", "advisor"), context("commuter")])
    assert [d.agent for d in out] == ["advisor", "commuter", "working"]


def test_call_slower_than_phase_deadline_is_a_timeout_no_action() -> None:
    def reply(agent, prompt):
        if agent == "working":
            time.sleep(1.5)
        return NOTHING

    agents = Agents(blueprint(), model=RoutedModel(reply), cap=10, phase_deadline_s=0.3)
    started = time.monotonic()
    out = {d.agent: d for d in agents.decide_phase([context("working"), context("commuter")])}
    assert time.monotonic() - started < 1.0  # the phase does not wait for the slow call
    assert out["working"].error.startswith("timeout") and not out["working"].proposals
    assert out["commuter"].error is None and agents.timeouts == 1


def test_run_with_over_10_percent_error_no_actions_ends_degraded() -> None:
    def failing(agent, prompt):
        if agent == "commuter":
            raise RuntimeError("ThrottlingException: slow down")
        return NOTHING

    engine, summary = run_term(blueprint(), Agents(blueprint(), model=RoutedModel(failing), cap=1000))
    errors = [d for d in decisions(engine) if d.payload["error"]]
    assert errors and all(d.actor == "commuter" and d.payload["no_action"] for d in errors)
    assert summary.llm_errors == len(errors) and summary.llm_errors / summary.decisions > 0.10
    assert summary.cap_hits == 0 and summary.status == "degraded"

    _, clean = run_term(blueprint(), Agents(blueprint(), model=RoutedModel(), cap=1000))
    assert clean.status == "completed" and clean.llm_errors == 0 and clean.cap_hits == 0


def test_agent_proposals_reach_the_engine_and_bad_ones_are_rejected() -> None:
    def reply(agent, prompt):
        session = int(re.search(r"session (\d+)\)", prompt).group(1))
        if agent == "commuter":  # a student trying to edit attendance: refused by permission
            return json.dumps({"actions": [{"action": "edit_attendance",
                                            "params": {"student": "commuter", "session": 1, "present": True}}],
                               "reason": "fix my record"})
        if agent == "working":
            return json.dumps({"actions": [{"action": "skip", "params": {"session": session}}],
                               "reason": "the bus is on strike"})
        return NOTHING

    engine, summary = run_term(blueprint(), Agents(blueprint(), model=RoutedModel(reply), cap=1000))
    skips = [e for e in engine.events if e.type == "student_plans_skip"]
    assert skips and all(e.actor == "working" and engine.event(e.caused_by[0]).type == "decision" for e in skips)
    assert summary.rejected and {r.reason for r in summary.rejected if r.agent == "commuter"} == {"permission"}


def test_agent_is_told_its_refused_action_and_its_uncovered_absences() -> None:
    def early_request(agent, prompt):  # asks for an exception before the class has taken place
        session = int(re.search(r"session (\d+)\)", prompt).group(1))
        if agent == "commuter" and "transport_disruption" in prompt:
            return json.dumps({"actions": [{"action": "submit_exception_request",
                                            "params": {"sessions": [session], "reason": "bus strike"}}],
                               "reason": "the bus is on strike"})
        return NOTHING

    agents = Agents(blueprint(), model=RoutedModel(early_request), cap=1000)
    run_term(blueprint(), agents)
    first, after = agents.prompts["commuter"][0], agents.prompts["commuter"][1]
    assert "What happened to the actions" not in first
    assert "refused: submit_exception_request" in after and "is not a completed, countable session" in after
    assert "no exception request covers: session 5" in after  # the late arrival at session 5
