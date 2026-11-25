"""Slice 16: the guided scenario search (fake models; no Bedrock)."""

import json
import random
import time

import pytest
from fastapi.testclient import TestClient

from rulestorm import search
from rulestorm.api import app, get_agent_model, get_blueprint_model, get_runs_dir, get_store
from rulestorm.blueprint import values_model
from rulestorm.core.model import load_template
from rulestorm.explore import environment
from rulestorm.fixture import restore_demo
from rulestorm.llm import Reply
from rulestorm.runner import recover_interrupted
from test_agents import RoutedModel
from test_runner import GatedModel, approved, store  # noqa: F401 - fixtures


def disruption(period: int, delay: int = 120) -> dict:
    return {"kind": "transport", "period": period, "steps": [1, 2], "people": ["working"], "delay": delay,
            "description": f"week {period} strike"}


def scenario(name: str, disruptions: list[dict], capacity: int = 2, checkpoint: int = 6) -> dict:
    return {"name": name, "weak_point": f"{name} tests the threshold",
            "values": {"office_capacity_per_week": capacity, "checkpoint_week": checkpoint, "disruptions": disruptions}}


MILD = scenario("Mild strike", [disruption(3, delay=10)])
HARSH = scenario("Six weeks of strikes", [disruption(p) for p in range(1, 7)])


class ProposalModel:
    """Replies to every proposal with the same scenarios and keeps the prompts it was sent."""

    model_id = "fake"

    def __init__(self, *variants: dict) -> None:
        self.reply = json.dumps({"variants": list(variants)})
        self.prompts: list[str] = []

    def complete(self, prompt: str, max_tokens: int, timeout_s: float | None = None) -> Reply:
        self.prompts.append(prompt)
        return Reply(self.reply, 100, 50)


@pytest.fixture
def http(store, tmp_path):  # noqa: F811
    def use(proposals):
        app.dependency_overrides[get_store] = lambda: store
        app.dependency_overrides[get_blueprint_model] = lambda: proposals
        app.dependency_overrides[get_agent_model] = lambda: RoutedModel()
        app.dependency_overrides[get_runs_dir] = lambda: str(tmp_path / "runs")
        return TestClient(app)

    yield use
    app.dependency_overrides.clear()


def wait_until_done(http, sid: str, timeout: float = 90) -> dict:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        s = http.get(f"/api/searches/{sid}").json()
        if s["status"] != "running":
            return s
        time.sleep(0.1)
    raise AssertionError(f"search {sid} still running")


def test_a_break_counts_only_once_a_rerun_repeats_it(http, store, approved) -> None:  # noqa: F811
    client = http(ProposalModel(MILD, HARSH))
    started = client.post(f"/api/blueprints/{approved.id}/search", json={"max_runs": 6})
    assert started.status_code == 200 and started.json()["status"] == "running"
    done = wait_until_done(client, started.json()["id"])
    assert done["status"] == "broken", done
    first = done["rounds"][0]["scenarios"]
    assert [s["source"] for s in first] == ["targeted", "targeted", "random"]
    mild, harsh, rnd = first
    assert mild["status"] == "ran: no finding" and mild["runs"][0]["closeness"]["closest"]["spare"] > 0
    assert harsh["status"] == "broke, repeated by the rerun" and harsh["confirmed"] is True
    assert len(harsh["runs"]) == 2 and all(r["findings"] for r in harsh["runs"])
    assert rnd["status"] == "not run: the search ended"
    assert done["runs_used"] == 3
    assert done["result"]["scenario"] == "Six weeks of strikes" and len(done["result"]["runs"]) == 2
    assert done["result"]["findings"] and done["label"] == "within-model evidence, not real-world causality"
    # only environment values changed; the scenarios are their own blueprints, not stress variants
    child = store.get_blueprint(harsh["blueprint_id"])
    assert child.search_of == done["id"] and child.parent_id is None and child.approved
    for p in load_template("attendance").parameters:
        if p.kind != "environment":
            assert child.blueprint.values[p.name] == approved.blueprint.values[p.name], p.name
    assert store.list_variants(approved.id) == []


def test_round_two_is_told_how_close_round_one_came_and_ends_honestly(http, store, approved, monkeypatch) -> None:  # noqa: F811
    proposals = ProposalModel(MILD, scenario("Small backlog", [disruption(4, delay=10)], capacity=1))
    monkeypatch.setattr(search, "random_scenario", lambda t, base, rng: {**base, "checkpoint_week": 7})
    client = http(proposals)
    done = wait_until_done(client, client.post(f"/api/blueprints/{approved.id}/search",
                                               json={"max_runs": 6}).json()["id"])
    assert done["status"] == "not_broken" and done["runs_used"] == 6
    assert len(done["rounds"]) == 2 and all(s["source"] == "random" for s in [done["rounds"][1]["scenarios"][-1]])
    assert "Scenarios already run" not in proposals.prompts[0]
    second = proposals.prompts[1]
    assert "Scenarios already run, from each run's own records, closest to breaking first:" in second
    assert "to spare before 'not eligible'" in second and "push harder on the weak point" in second
    assert done["rounds"][1]["pushes"] and "to spare" in done["rounds"][1]["pushes"]
    assert done["result"]["summary"] == "not broken in 6 runs" and done["result"]["closest"]["closeness"]


def test_a_break_the_rerun_does_not_repeat_is_reported_and_the_search_goes_on(store, approved, monkeypatch) -> None:  # noqa: F811
    rows = iter([[{"finding_id": "X-F1", "kind": "check_failed"}], [], [], []])

    def fake_run(store_, record, s, agent_model, out_dir):
        row = {"run_id": f"L-{record['runs_used']}", "status": "completed", "findings": next(rows),
               "closeness": {"closest": {"spare": 1, "text": "working: 1 absences to spare"},
                             "pending_at_check": 0, "queue": {"peak": 0, "lowest_capacity": 2,
                                                              "periods_over_capacity": 0}, "checks": []}}
        s["runs"].append(row)
        record["runs_used"] += 1
        return row

    monkeypatch.setattr(search, "_run_scenario", fake_run)
    record = {"id": "S-t", "blueprint_id": approved.id, "status": "running", "max_runs": 4, "runs_used": 0,
              "seed": 1, "rounds": [], "result": None, "created_at": "x"}
    store.save_search(record)
    search._rounds(store, record, ProposalModel(MILD, HARSH), None, "runs")
    first = record["rounds"][0]["scenarios"]
    assert first[0]["status"] == "broke once, not repeated" and first[0]["confirmed"] is False
    assert record["status"] == "not_broken" and record["runs_used"] == 4


@pytest.mark.parametrize("template_id", ["attendance", "hostel_curfew"])
def test_random_scenarios_pass_the_engine_and_change_only_the_environment(template_id) -> None:
    from rulestorm.core.term import dry_run_values

    t = load_template(template_id)
    raw = {**{p.name: "as the policy states" for p in t.parameters if p.type == "text"}, **dry_run_values(t)}
    base = values_model(t).model_validate(raw).model_dump()
    env = {p.name for p in environment(t)}
    for seed in range(40):
        values = search.random_scenario(t, base, random.Random(seed))
        values_model(t).model_validate(values)
        assert any(values[n] != base[n] for n in env)
        assert all(values[p.name] == base[p.name] for p in t.parameters if p.name not in env)


def test_closeness_reads_the_demo_runs_own_records() -> None:
    s = __import__("rulestorm.store", fromlist=["Store"]).Store(":memory:")
    restore_demo(s)
    run = s.get_run("demo")
    bp = s.get_blueprint(run["blueprint_id"]).blueprint
    c = search.closeness(load_template("attendance"), bp.values, s.run_events("demo"))
    assert c["closest"]["person"] == "working" and c["closest"]["spare"] <= 0
    assert "working reached 'not eligible' (week 6)" == c["closest"]["text"]


def test_refusals_and_restart(http, store, approved, monkeypatch, tmp_path) -> None:  # noqa: F811
    client = http(ProposalModel(MILD))
    assert client.post("/api/blueprints/B-missing/search", json={}).status_code == 404
    assert client.get("/api/searches/S-missing").status_code == 404
    assert client.post(f"/api/blueprints/{approved.id}/search", json={"max_runs": 20}).status_code == 422
    monkeypatch.setenv("MAX_RUNS_PER_DAY", "2")
    short = client.post(f"/api/blueprints/{approved.id}/search", json={})
    assert short.status_code == 429 and "at least 3 runs; 2 left" in short.json()["detail"]
    monkeypatch.delenv("MAX_RUNS_PER_DAY")
    gated = GatedModel()
    app.dependency_overrides[get_agent_model] = lambda: gated
    try:
        run_id = client.post("/api/runs", json={"blueprint_id": approved.id}).json()["run_id"]
        busy = client.post(f"/api/blueprints/{approved.id}/search", json={})
        assert busy.status_code == 409 and busy.json()["run_id"] == run_id
    finally:
        gated.gate.set()
    store.save_search({"id": "S-cut", "blueprint_id": approved.id, "status": "running", "rounds": [],
                       "created_at": "x"})
    recover_interrupted(store)
    assert store.get_search("S-cut")["status"] == "failed"
