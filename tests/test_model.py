"""Slice L1: templates are data, and the template check decides whether the engine can trust one."""

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from rulestorm.core.model import TEMPLATES_DIR, check_file, check_template, load_template

BROKEN = Path(__file__).parent / "cases" / "broken_template.json"


@pytest.fixture
def raw() -> dict:
    return json.loads((TEMPLATES_DIR / "attendance.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("path", sorted(TEMPLATES_DIR.glob("*.json")), ids=lambda p: p.stem)
def test_every_shipped_template_passes(path: Path) -> None:
    result = check_file(str(path))
    assert result.valid, result.errors


def test_attendance_has_todays_world() -> None:
    t = load_template("attendance")
    assert t.ref == "attendance@1"
    llm_actions = {a for r in t.roles for a in r.actions}
    assert llm_actions == {"attend", "skip", "submit_exception_request", "ask_advisor",
                           "edit_attendance", "cancel_session", "advise_student"}
    # recording, queue processing and the eligibility check are rules, not actions
    rules = {rule: r.id for r in t.roles for rule in r.rules}
    assert rules == {"recorder": "faculty", "queue_processor": "attendance_admin", "checker": "exam_officer"}
    assert "edit_attendance" not in next(r for r in t.roles if r.id == "student").actions
    assert check_file("attendance").lines()[1] == (
        "roles 5, people 8, duties 1, actions 7, request types 1, counts 1, checks 1")


def test_broken_reference_is_named(raw: dict) -> None:
    result = check_file(str(BROKEN))
    assert not result.valid
    assert result.lines() == ["invalid: action 'attend' refers to unknown duty 'lecture'"]


@pytest.mark.parametrize("break_it, error", [
    (lambda t: t["roles"][0]["actions"].append("fly"), "role 'student' refers to unknown action 'fly'"),
    (lambda t: t["roles"][3].update(actions=["attend"]),
     "role 'attendance_admin' is not an LLM role, so it cannot take actions"),
    (lambda t: t["checks"][0].update(count="grades"), "check 'exam_eligibility' refers to unknown count 'grades'"),
    (lambda t: t["checks"][0].update(run_by="advisor"),
     "check 'exam_eligibility' needs role 'advisor' to have the checker rule"),
    (lambda t: t["request_types"][0].update(capacity_param="threshold_pct"),
     "request type 'exception' needs a parameter of kind environment, but 'threshold_pct' is policy"),
    (lambda t: t["parameters"][5]["choices"].append("coin_flip"),
     "parameter 'decision_rule' has unknown choice 'coin_flip'"),
    (lambda t: t["people"].append({"id": "dean", "role": "dean"}), "person 'dean' refers to unknown role 'dean'"),
])
def test_each_broken_link_is_caught(raw: dict, break_it, error: str) -> None:
    t = copy.deepcopy(raw)
    break_it(t)
    result = check_template(t)
    assert not result.valid
    assert error in result.errors


def test_unknown_effect_is_a_schema_error(raw: dict) -> None:
    raw["actions"][0]["effects"][0]["kind"] = "teleport"
    result = check_template(raw)
    assert not result.valid and result.errors[0].startswith("actions.0.effects.0.kind")


def test_cli_exits_non_zero_on_invalid() -> None:
    cmd = [sys.executable, "-m", "rulestorm.cli", "template", "check", str(BROKEN)]
    done = subprocess.run(cmd, capture_output=True, text=True)
    assert done.returncode != 0
    assert done.stdout.startswith("invalid: ")
