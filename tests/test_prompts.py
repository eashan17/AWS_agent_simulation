"""Slices L5 / L7: prompts generated from the template keep what the old engine's prompts gave
the real 6b runs (frozen in tests/golden/ before any prompt code changed), plus a request-rules
block.

Narrowed in slice L7 (docs/SLICES.md, general-feature rule): an exact match only for the lines
that carry the 6b fixes (the missed occurrences no request covers, what happened to the last
decision's actions, the slack line, the allowed-actions list); every other frozen line only has
to keep its facts (IDs, numbers, names and values), not its wording.

Updated on purpose on 26 Nov (demo fix), in the frozen files too: the slack line says a longer
delay makes you miss the class (not "late": late is recorded absent), an optional parameter says
leaving it out keeps it, and the reply asks for the reason before the actions."""

import json
import re
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
    "- The attendance office approves a request only if every class it covers is a recorded absence with a valid reason.",
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
        ctx.attributes = {"travel_buffer_min": c["travel_buffer_min"]}
        ctx.pending_requests = a["pending"]
        ctx.uncovered_missed = c["uncovered"]
    else:
        ctx.pending_requests = c["pending_requests"]
    return ctx


def golden(name: str) -> list[str]:
    return (GOLDEN / f"{name}.txt").read_text(encoding="utf-8").splitlines()


NAMES = ["commuter", "advisor", "faculty"]
# Facts in a frozen line: event and request IDs, numbers and percentages, backticked names and
# snake_case identifiers (types, payload keys, action names).
FACT = re.compile(r"E-\d{4}|\bR\d+\b|\d+(?:\.\d+)?%?|`\w+`|\b[a-z]+(?:_[a-z]+)+\b")


def generated(template, name: str) -> list[str]:
    return render_prompt(template, VALUES, context(name), DATA["contexts"][name]["memory"]).splitlines()


def fix_lines(lines: list[str]) -> list[str]:
    """The lines that carry the 6b fixes, in order."""
    keep, block = [], None
    for line in lines:
        if line.startswith("What happened to the actions of your last decision:"):
            block = "outcomes"
        elif line.startswith("Actions you may propose"):
            block = "actions"
        elif line == "":
            block = None if block == "outcomes" else block
        if block or line.startswith("Your recorded ") or line.startswith("- travel buffer:"):
            keep.append(line)
    return keep


@pytest.mark.parametrize("name", NAMES)
def test_the_6b_fix_lines_match_exactly(template, name: str) -> None:
    expected = fix_lines(golden(name))
    assert expected  # every fixture has at least its allowed-actions list
    assert fix_lines(generated(template, name)) == expected


@pytest.mark.parametrize("name", NAMES)
def test_every_other_frozen_line_keeps_its_facts(template, name: str) -> None:
    prompt = "\n".join(generated(template, name))
    fixed = set(fix_lines(golden(name)))
    for line in golden(name):
        if line in fixed:
            continue
        missing = [fact for fact in FACT.findall(line) if fact not in prompt]
        assert not missing, f"facts of {line!r} missing: {missing}"


@pytest.mark.parametrize("name", NAMES)
def test_the_blueprint_and_context_values_all_reach_the_prompt(template, name: str) -> None:
    c = DATA["contexts"][name]
    prompt = "\n".join(generated(template, name))
    facts = [c["person"], c["role"], str(c["period"]), str(c["step"]), c["profile"]["description"],
             *c["profile"]["goals"], *c["profile"].get("constraints", []), *c["memory"],
             *(t["event_id"] for t in c["triggers"]), *(t["type"] for t in c["triggers"]),
             str(DATA["policy"]["threshold_pct"]), DATA["policy"]["scope"], DATA["policy"]["exception_rule"],
             str(DATA["policy"]["checkpoint_week"])]
    if c["role"] == "student":
        facts += ["4/6 = 66.7%", *c["attendance"]["pending"], str(c["travel_buffer_min"])]
    else:
        facts += c["pending_requests"]
    assert [f for f in facts if f not in prompt] == []


@pytest.mark.parametrize("name", NAMES)
def test_request_rules_block_follows_the_policy_block(template, name: str) -> None:
    lines = generated(template, name)
    start = lines.index("Request rules:") - 1
    assert lines[start:start + len(REQUEST_RULES)] == REQUEST_RULES
    assert lines.index("Policy:") < start < lines.index("What just happened (the events that triggered you):")


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
