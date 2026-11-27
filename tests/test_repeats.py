"""Slice 21: repeated runs of one blueprint, counted as how often (fake models; no Bedrock)."""

import copy
import json
import time

import pytest
from fastapi.testclient import TestClient

from rulestorm.api import app, get_agent_model, get_runs_dir, get_store
from rulestorm.llm import FakeModel
from rulestorm.policy import PolicyInput, approve_blueprint, create_blueprint
from rulestorm.runner import recover_interrupted, run_now
from rulestorm.store import Store
from test_agents import RoutedModel
from test_blueprint import FILL, PICK
from test_runner import GatedModel


def strikes(period):
    return {"kind": "transport", "period": period, "steps": [1, 2], "people": ["working"], "delay": 120,
            "description": f"week {period} strike"}


@pytest.fixture
def store(tmp_path) -> Store:
    return Store(str(tmp_path / "test.db"))


@pytest.fixture
def harsh(store):
    """A blueprint where the working student misses six weeks of sessions: fails the check every run."""
    fill = copy.deepcopy(FILL)
    fill["values"]["disruptions"] = [strikes(p) for p in range(1, 7)]
    policy = store.save_policy(PolicyInput(text="80% attendance", purpose="y", environment="strikes happen"))
    return approve_blueprint(store, create_blueprint(store, policy.id, FakeModel([PICK, json.dumps(fill)])).id)


@pytest.fixture
def http(store, tmp_path):
    agents = RoutedModel()
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_agent_model] = lambda: agents
    app.dependency_overrides[get_runs_dir] = lambda: str(tmp_path / "runs")
    yield TestClient(app)
    app.dependency_overrides.clear()


def wait_until_done(http, rid, timeout=60):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        r = http.get(f"/api/repeats/{rid}").json()
        if r["status"] != "running":
            return r
        time.sleep(0.1)
    raise AssertionError("still running")


def test_repeated_runs_count_how_often_each_person_fails_with_an_included_run(http, store, harsh, tmp_path) -> None:
    first = run_now(store, harsh.id, RoutedModel(), out_dir=str(tmp_path / "runs"))
    started = http.post(f"/api/blueprints/{harsh.id}/repeats", json={"times": 2, "include_run": first})
    assert started.status_code == 200 and started.json()["status"] == "running"
    done = wait_until_done(http, started.json()["id"])
    assert done["status"] == "completed"
    assert [r["included"] for r in done["runs"]] == [True, False, False] and done["runs"][0]["run_id"] == first
    assert all(r["status"] == "completed" for r in done["runs"])
    s = done["summary"]
    assert s["runs"] == 3
    working = next(p for p in s["people"] if p["person"] == "working")
    assert (working["failed"], working["checked"]) == (3, 3) and working["highest"] < 80
    assert s["people"][0]["person"] == "working"  # most failures first
    assert {"kind": "check_failed", "runs": 3} in s["findings"]
    # Slice M9: per-person margin spread, obligations lost and the harms counted per cause class.
    assert working["margin"]["highest"] <= 0 and working["margin"]["lowest"] <= working["margin"]["mean"]
    assert s["obligations_lost"] == 0
    assert s["cause_classes"] and sum(c["harms"] for c in s["cause_classes"]) >= 3
    assert all(c["cause_class"] in ("no_reply", "ai_mistake", "forced", "process", "trade_off", "chosen")
               for c in s["cause_classes"])
    assert {"obligations_lost", "near_misses", "lowest_margin", "unexcused_absences", "ai_mistakes"} <= {
        m["measure"] for m in s["measures"]}
    filed = next(m for m in s["measures"] if m["measure"] == "requests_filed")
    assert len(filed["values"]) == 3 and filed["lowest"] <= filed["mean"] <= filed["highest"]
    assert done["label"] == "within-model evidence, not real-world causality" and "afresh" in done["note"]


def test_refusals(http, store, harsh, monkeypatch, tmp_path) -> None:
    assert http.post("/api/blueprints/B-missing/repeats", json={}).status_code == 404
    assert http.get("/api/repeats/R-missing").status_code == 404
    assert http.post(f"/api/blueprints/{harsh.id}/repeats", json={"times": 9}).status_code == 422
    wrong = http.post(f"/api/blueprints/{harsh.id}/repeats", json={"times": 2, "include_run": "nope"})
    assert wrong.status_code == 422 and "not a finished run of blueprint" in wrong.json()["detail"]
    monkeypatch.setenv("MAX_RUNS_PER_DAY", "1")
    short = http.post(f"/api/blueprints/{harsh.id}/repeats", json={"times": 2})
    assert short.status_code == 429 and "2 runs asked for; 1 left" in short.json()["detail"]
    monkeypatch.delenv("MAX_RUNS_PER_DAY")
    gated = GatedModel()
    app.dependency_overrides[get_agent_model] = lambda: gated
    try:
        run_id = http.post("/api/runs", json={"blueprint_id": harsh.id}).json()["run_id"]
        busy = http.post(f"/api/blueprints/{harsh.id}/repeats", json={"times": 2})
        assert busy.status_code == 409 and busy.json()["run_id"] == run_id
    finally:
        gated.gate.set()


def test_a_repeat_cut_off_by_a_restart_becomes_failed(store, harsh) -> None:
    store.save_repeat({"id": "R-cut", "blueprint_id": harsh.id, "status": "running", "runs": [], "created_at": "x"})
    recover_interrupted(store)
    assert store.get_repeat("R-cut")["status"] == "failed"
