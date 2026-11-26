"""Slice M7c: every person keeps their own state, recomputed from the records, and decides from it
(both templates; fake models, no Bedrock)."""

import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rulestorm.api import app, get_agent_model, get_runs_dir, get_store
from rulestorm.core.cases import play_case
from rulestorm.core.margins import PersonState
from rulestorm.core.model import load_template
from rulestorm.core.term import simulate
from rulestorm.policy import PolicyInput, approve_blueprint, create_blueprint
from rulestorm.store import Store
from test_agents import RoutedModel
from test_blueprint import FILL, PICK
from test_core_term import VALUES, decider
from test_runner import wait_until_finished

CASES = Path(__file__).parent / "cases"


def case(name: str, **changes) -> dict:
    c = json.loads((CASES / name).read_text(encoding="utf-8"))
    c.update(changes)
    return c


def lines_of(name: str, **changes) -> list[str]:
    c = case(name, **changes)
    return play_case(c, load_template(c["template"]))[0]


def test_the_shift_case_states_the_tally_and_both_margins_before_each_clash() -> None:
    lines = [x for x in lines_of("shift_clash.json") if " state, " in x]
    assert [x.split("  [")[0] for x in lines] == [
        "working state, session 4: attendance 3/3 = 100.0%; absences 0; 4 left before exam eligibility; "
        "work shift missed 0 of 2, 2 left",
        "working state, session 6: attendance 5/5 = 100.0%; absences 0; 4 left before exam eligibility; "
        "work shift missed 1 of 2, 1 left",
        "working state, session 8: attendance 7/7 = 100.0%; absences 0; 4 left before exam eligibility; "
        "work shift missed 2 of 2, 0 left",
        "working state, session 10: attendance 8/9 = 88.9%; absences 1; 3 left before exam eligibility; "
        "work shift missed 2 of 2, 0 left",
    ]  # 80% of 20 sessions: the 5th absence fails eligibility; the session-8 absence went to the shift


def test_the_curfew_case_states_every_ladder_step() -> None:
    lines = [x.split("  [")[0] for x in lines_of("curfew_job_shift.json") if " state, " in x]
    assert lines[0] == ("intern state, night 3: late returns 0; 1 left before warning; 2 left before guardian "
                        "informed; 3 left before disciplinary; evening shift missed 0 of 2, 2 left")
    assert lines[-1] == ("intern state, night 18: late returns 1; 0 left before warning; 1 left before guardian "
                         "informed; 2 left before disciplinary; evening shift missed 2 of 2, 0 left")


def test_zero_left_means_the_next_miss_fails_the_check() -> None:
    c = case("shift_clash.json", outcomes={"working": {"missed": [1, 3, 5, 7]}}, meets={})
    c["values"]["disruptions"] = []
    t = load_template("attendance")
    e = play_case(c, t)[1]
    before = e.person_state("working", 9)  # recomputed after the term: the 4 misses are recorded
    [eligibility] = before.counts[0].checks
    assert (before.counts[0].missed, eligibility.misses_left, eligibility.failing) == (4, 0, False)
    c["outcomes"] = {"working": {"missed": [1, 3, 5, 7, 9]}}
    e = play_case(c, t)[1]
    [after] = e.person_state("working", 11).counts[0].checks
    assert after.failing and after.misses_left == 0


def test_ladder_steps_reached_and_excused_or_pending_misses_are_shown() -> None:
    c = case("curfew_r2.json")
    t = load_template("hostel_curfew")
    e = play_case(c, t)[1]
    state = e.person_state("researcher", 20)
    [late] = state.counts
    reached = [m.label for m in late.checks if m.done == "reached"]
    assert reached == ["warning", "guardian informed", "disciplinary"]
    assert (late.missed, late.excused) == (5, 1)  # nights 2, 4, 8, 9, 12; night 8 approved
    assert "(1 excused, 0 pending)" in state.lines(t)[0]


def test_every_decision_records_the_state_it_was_made_from() -> None:
    template = load_template("attendance")
    seen = {}

    def recording(contexts):
        for c in contexts:
            seen[(c.person, c.step)] = c.state
        return decider(contexts)

    engine = simulate(template, VALUES, recording)
    students = [e for e in engine.events if e.type == "decision" and e.actor in ("commuter", "working")]
    assert students
    for d in students:
        assert PersonState.model_validate(d.payload["state"]) == seen[(d.actor, d.step)]
    staff = [e for e in engine.events if e.type == "decision" and e.actor in ("faculty", "advisor")]
    assert staff and all("state" not in d.payload for d in staff)  # people who owe no duty have none


def test_the_people_route_returns_the_profile_limits_and_each_decisions_state(tmp_path) -> None:
    store = Store(str(tmp_path / "test.db"))
    fill = copy.deepcopy(FILL)
    fill["values"]["disruptions"].append({"kind": "work_shift_clash", "period": 1, "until_period": 3, "steps": [2],
                                          "people": ["working"], "description": "weekly shift"})
    policy = store.save_policy(PolicyInput(text="80% attendance", purpose="y", environment="shifts"))
    from rulestorm.llm import FakeModel

    record = approve_blueprint(store, create_blueprint(store, policy.id, FakeModel([PICK, json.dumps(fill)])).id)
    model = RoutedModel()
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_agent_model] = lambda: model
    app.dependency_overrides[get_runs_dir] = lambda: str(tmp_path / "runs")
    try:
        http = TestClient(app)
        run_id = http.post("/api/runs", json={"blueprint_id": record.id}).json()["run_id"]
        wait_until_finished(http, run_id)
        view = http.get(f"/api/runs/{run_id}/people/working").json()
        assert view["role"] == "student" and view["profile"]["description"] == "works evening shifts"
        assert view["attributes"]["shift_miss_limit"] == 1  # FILL's limit for the working student
        clash = [d for d in view["decisions"] if d["step"] == 2]
        assert clash and "work shift missed 0 of 1, 1 left" in clash[0]["state_lines"]
        assert http.get(f"/api/runs/{run_id}/people/dean").status_code == 404
        assert http.get("/api/runs/L-none/people/working").status_code == 404
    finally:
        app.dependency_overrides.clear()
