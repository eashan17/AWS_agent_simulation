"""Slice 15: strict, flexible and progressive versions of an approved policy, run under the same
environment and people, compared as a trade-off table with no overall score (fake models)."""

import json
import time

import pytest
from fastapi.testclient import TestClient

from rulestorm import comparison
from rulestorm.api import app, get_agent_model, get_blueprint_model, get_runs_dir, get_store
from rulestorm.llm import FakeModel
from rulestorm.runner import recover_interrupted
from test_agents import RoutedModel
from test_blueprint import FILL
from test_runner import GatedModel, approved, store  # noqa: F401 - fixtures

POLICY = {k: FILL["values"][k] for k in ("threshold_pct", "scope", "exception_rule", "request_timing",
                                          "partial_at_submit", "partial_at_decide", "decision_rule")}


def version(approach: str, **changed) -> dict:
    return {"approach": approach, "values": {**POLICY, **changed}}


VERSIONS = json.dumps({
    "strict": version("the rule to the letter", threshold_pct=85, decision_rule="approve_if_filed_before_occurrence",
                      request_timing="in_advance"),
    "flexible": version("provisions for disruptions", partial_at_submit=True, partial_at_decide=True,
                        exception_rule="disruptions outside a student's control are excused once verified"),
    # tries to change the environment too; the reply has no such field, so it can't
    "progressive": version("early warnings and advisor support", decision_rule="approve_all",
                           office_capacity_per_week=40, checkpoint_week=2),
})


@pytest.fixture
def http(store, tmp_path):  # noqa: F811
    agents = RoutedModel()
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_blueprint_model] = lambda: FakeModel([VERSIONS])
    app.dependency_overrides[get_agent_model] = lambda: agents
    app.dependency_overrides[get_runs_dir] = lambda: str(tmp_path / "runs")
    yield TestClient(app)
    app.dependency_overrides.clear()


def wait_until_done(http, cid: str, timeout: float = 60) -> dict:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        c = http.get(f"/api/comparisons/{cid}").json()
        if c["status"] != "running":
            return c
        time.sleep(0.1)
    raise AssertionError(f"comparison {cid} still running")


def test_three_versions_differ_only_in_policy_and_give_a_table_with_no_score(http, store, approved) -> None:  # noqa: F811
    started = http.post("/api/comparisons", json={"blueprint_id": approved.id})
    assert started.status_code == 200, started.text
    body = started.json()
    assert body["status"] == "running" and [v["name"] for v in body["versions"]] == ["strict", "flexible", "progressive"]
    # the 80% threshold is a fact from the policy text, so the strict version's 85 can't land
    assert {c["parameter"] for c in body["versions"][0]["changed"]} == {"decision_rule", "request_timing"}
    assert body["kept"] == [{"parameter": "threshold_pct", "value": 80, "why": "stated in the policy (a fact)"}]

    done = wait_until_done(http, body["id"])
    assert done["status"] == "completed", done
    assert done["matched"]["same_environment_and_people"] is True
    parent = approved.blueprint.values
    for v in done["versions"]:
        assert v["status"] == "completed" and v["run_id"]
        child = store.get_blueprint(v["blueprint_id"])
        assert child.approved and child.comparison_of == approved.id and child.parent_id is None
        for name in ("threshold_pct", "office_capacity_per_week", "checkpoint_week", "disruptions", "profiles",
                     "slack_min"):
            assert child.blueprint.values[name] == parent[name], (v["name"], name)
        assert all(a.statement.startswith(f"Policy version '{v['name']}'") for a in child.blueprint.assumptions
                   if a.field in {c["parameter"] for c in v["changed"]})

    table = done["table"]
    assert table["columns"] == ["strict", "flexible", "progressive"]
    measures = {row["measure"] for row in table["rows"]}
    assert {"check_failed", "requests_filed", "refused_actions", "queue_longest", "staff_decisions"} <= measures
    assert all(set(row) >= {"strict", "flexible", "progressive"} for row in table["rows"])
    assert table["checks"] and all({"strict", "flexible", "progressive"} <= set(row) for row in table["checks"])
    assert "score" not in json.dumps(table).lower() and done["no_overall_score"]
    assert done["label"] == "within-model evidence, not real-world causality"


def test_a_comparison_is_refused_when_a_run_is_going_or_today_has_too_few_runs(store, approved, monkeypatch,  # noqa: F811
                                                                                 tmp_path) -> None:
    gated = GatedModel()
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_blueprint_model] = lambda: FakeModel([VERSIONS])
    app.dependency_overrides[get_agent_model] = lambda: gated
    app.dependency_overrides[get_runs_dir] = lambda: str(tmp_path / "runs")
    http = TestClient(app)
    try:
        run_id = http.post("/api/runs", json={"blueprint_id": approved.id}).json()["run_id"]
        busy = http.post("/api/comparisons", json={"blueprint_id": approved.id})
        assert busy.status_code == 409 and busy.json()["run_id"] == run_id
        gated.gate.set()
        while http.get(f"/api/runs/{run_id}").json()["status"] == "running":
            time.sleep(0.05)
        monkeypatch.setenv("MAX_RUNS_PER_DAY", "3")  # one used above, so two are left
        before = store.daily_usage()["blueprint_calls"]
        short = http.post("/api/comparisons", json={"blueprint_id": approved.id})
        assert short.status_code == 429 and "needs 3 runs; 2 left" in short.json()["detail"]
        assert store.daily_usage()["blueprint_calls"] == before  # refused before the model call
    finally:
        gated.gate.set()
        app.dependency_overrides.clear()


def test_unknown_and_unapproved_blueprints_and_comparisons(http, store) -> None:  # noqa: F811
    assert http.post("/api/comparisons", json={"blueprint_id": "B-missing"}).status_code == 404
    assert http.get("/api/comparisons/C-missing").status_code == 404
    assert http.post("/api/comparisons", json={}).status_code == 422


def test_a_comparison_cut_off_by_a_restart_becomes_failed(store, approved) -> None:  # noqa: F811
    store.save_comparison({"id": "C-cut", "blueprint_id": approved.id, "status": "running", "versions": [],
                           "created_at": "2026-11-25T00:00:00+00:00"})
    recover_interrupted(store)
    cut = store.get_comparison("C-cut")
    assert cut["status"] == "failed" and cut["error"].startswith("Interrupted")


def test_the_prompt_names_all_three_versions_and_only_policy_values(store, approved) -> None:  # noqa: F811
    from rulestorm.core.model import load_template

    template = load_template("attendance")
    prompt = comparison.comparison_prompt(template, approved.blueprint, store.get_policy(approved.policy_id))
    for name in ("strict", "flexible", "progressive"):
        assert f"- {name}:" in prompt
    assert "- decision_rule:" in prompt and "- office_capacity_per_week:" not in prompt
    assert "- threshold_pct:" not in prompt and "as the policymaker stated them: threshold_pct 80" in prompt
    schema = comparison.comparison_schema(template, approved.blueprint)
    assert set(schema.model_fields) == {"strict", "flexible", "progressive"}
