"""Slice L5: prompts generated from the template reproduce the old engine's prompts (frozen in
tests/golden/ before any prompt code changed), plus a request-rules block."""

import json
from pathlib import Path

import pytest

from rulestorm.core.engine import CountResult, Event
from rulestorm.core.model import load_template
from rulestorm.core.term import DecisionContext
from rulestorm.prompts import render_prompt

GOLDEN = Path(__file__).parent / "golden"
DATA = json.loads((GOLDEN / "contexts.json").read_text(encoding="utf-8"))
# Test-only values: a hard-coded dict, not the L6b values model.
VALUES = {
    **DATA["policy"],
    "request_timing": "after_missed", "partial_at_submit": False, "partial_at_decide": False,
    "decision_rule": "approve_if_covered_missed", "office_capacity_per_week": 2,
}
REQUEST_RULES = [
    "",
    "Request rules:",
    "- Requests can cover only classes already recorded as missed.",
    "- A request that lists any class it can't cover is refused whole.",
    "- The attendance office approves or rejects each request whole.",
    "- The attendance office approves a request only if every class it covers is a recorded absence.",
]


@pytest.fixture(scope="module")
def template():
    return load_template("attendance")


def context(name: str) -> DecisionContext:
    c = DATA["contexts"][name]
    triggers = [Event(**{("period" if k == "week" else k): v for k, v in t.items()}) for t in c["triggers"]]
    ctx = DecisionContext(person=c["person"], role=c["role"], period=c["period"], step=c["step"],
                          triggers=triggers, profile=c["profile"], last_outcomes=c["last_outcomes"])
    if c["role"] == "student":
        a = c["attendance"]
        ctx.counts = {"attendance_pct": CountResult(
            count="attendance_pct", person=c["person"], kind="rate", met=a["attended"], due=a["countable"],
            missed=a["countable"] - a["attended"], value=a["pct"], pending=a["pending"],
            approved=a["approved"], rejected=a["rejected"])}
        ctx.attributes = {"slack_min": c["travel_buffer_min"]}
        ctx.pending_requests = a["pending"]
        ctx.uncovered_missed = c["uncovered"]
    else:
        ctx.pending_requests = c["pending_requests"]
    return ctx


def golden(name: str) -> list[str]:
    return (GOLDEN / f"{name}.txt").read_text(encoding="utf-8").splitlines()


def without_request_rules(lines: list[str]) -> list[str]:
    start = lines.index("Request rules:") - 1  # the blank line before it
    end = lines.index("", start + 1)
    return lines[:start] + lines[end:]


@pytest.mark.parametrize("name", ["commuter", "advisor", "faculty"])
def test_generated_prompt_reproduces_every_frozen_line(template, name: str) -> None:
    lines = render_prompt(template, VALUES, context(name), DATA["contexts"][name]["memory"]).splitlines()
    assert without_request_rules(lines) == golden(name)


@pytest.mark.parametrize("name", ["commuter", "advisor", "faculty"])
def test_request_rules_block_follows_the_policy_block(template, name: str) -> None:
    lines = render_prompt(template, VALUES, context(name), DATA["contexts"][name]["memory"]).splitlines()
    start = lines.index("Request rules:") - 1
    assert lines[start:start + len(REQUEST_RULES)] == REQUEST_RULES
    assert lines[start - 1] == "- eligibility is checked in week 6"  # right after the policy block


def test_request_rules_change_with_the_policy_values(template) -> None:
    values = {**VALUES, "request_timing": "in_advance", "partial_at_submit": True,
              "partial_at_decide": True, "decision_rule": "approve_all"}
    lines = render_prompt(template, values, context("commuter")).splitlines()
    start = lines.index("Request rules:")
    assert lines[start + 1:start + 5] == [
        "- Requests must be filed before the class; a class already held can't be covered.",
        "- A request that lists some classes it can't cover keeps the ones it can.",
        "- The attendance office can approve some classes of a request and reject the rest.",
        "- The attendance office approves every request it processes.",
    ]


def test_a_role_sees_only_its_own_actions_and_never_a_rule(template) -> None:
    rule_steps = ("record", "process", "evaluate", "check", "queue")
    for name in ("commuter", "advisor", "faculty"):
        ctx = context(name)
        lines = render_prompt(template, VALUES, ctx).splitlines()
        start = lines.index("Actions you may propose (0 to 3; an empty list means you do nothing):")
        offered = [line.split(":")[0].removeprefix("- ") for line in lines[start + 1:-1]]
        role = next(r for r in template.roles if r.id == ctx.role)
        assert offered == sorted(role.actions)
        assert not any(word in action for action in offered for word in rule_steps)


def test_every_context_of_a_real_term_renders(template) -> None:
    """Contexts from an L4 term (new event names, live counts) render with no missing value."""
    from rulestorm.core.term import simulate
    from test_core_term import VALUES as TERM_VALUES, decider

    rendered = []

    def recording(contexts):
        for c in contexts:
            rendered.append(render_prompt(template, {**TERM_VALUES, "exception_rule": "approved exceptions"}, c))
        return decider(contexts)

    simulate(template, TERM_VALUES, recording)
    assert rendered and all("Request rules:" in p for p in rendered)
    assert any("travel buffer: 30 min" in p and "obstacle" in p for p in rendered)
