"""Slice 7a: runs in the background, one at a time, followed by polling (fake model; no Bedrock)."""

import json
import threading
import time

import pytest
from fastapi.testclient import TestClient

from rulestorm.api import app, get_agent_model, get_runs_dir, get_store
from rulestorm.llm import FakeModel
from rulestorm.policy import PolicyInput, approve_blueprint, create_blueprint
from rulestorm.store import Store
from test_agents import NOTHING, RoutedModel
from test_blueprint import FILL, PICK


class GatedModel(RoutedModel):
    """Replies "no action" to everyone, but every call waits until the gate opens, so a test
    can look at the run while it is still going. `delay` slows each call down a little."""

    def __init__(self, delay: float = 0.0) -> None:
        self.gate = threading.Event()
        self.delay = delay

        def reply(person, prompt):
            self.gate.wait(10)
            time.sleep(self.delay)
            return NOTHING

        super().__init__(reply)


@pytest.fixture
def store(tmp_path) -> Store:
    return Store(str(tmp_path / "test.db"))


@pytest.fixture
def approved(store):
    policy = store.save_policy(PolicyInput(text="80% attendance", purpose="y", environment="strikes happen"))
    record = create_blueprint(store, policy.id, FakeModel([PICK, json.dumps(FILL)]))
    return approve_blueprint(store, record.id)


@pytest.fixture
def client(store, tmp_path):
    model = GatedModel()
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_agent_model] = lambda: model
    app.dependency_overrides[get_runs_dir] = lambda: str(tmp_path / "runs")
    yield TestClient(app), model
    model.gate.set()
    app.dependency_overrides.clear()


def wait_until_finished(http, run_id: str, timeout: float = 30) -> dict:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        run = http.get(f"/api/runs/{run_id}").json()
        if run["status"] != "running":
            return run
        time.sleep(0.05)
    raise AssertionError(f"run {run_id} still running after {timeout} s")


def test_a_post_answers_at_once_and_a_second_gets_409_with_the_same_run(client, approved) -> None:
    http, model = client
    started = time.monotonic()
    first = http.post("/api/runs", json={"blueprint_id": approved.id})
    assert first.status_code == 200 and time.monotonic() - started < 1.0  # the term runs in the background
    run_id = first.json()["run_id"]
    second = http.post("/api/runs", json={"blueprint_id": approved.id})
    assert second.status_code == 409 and second.json()["run_id"] == run_id
    running = http.get(f"/api/runs/{run_id}").json()
    assert running["status"] == "running" and running["periods"] == 10 and running["template"] == "attendance@1"
    assert running["run_id"] == run_id

    model.gate.set()
    done = wait_until_finished(http, run_id)
    assert done["status"] in ("completed", "degraded") and done["period"] == 10
    assert done["summary"]["decisions"] > 0 and done["finished_at"]
    assert http.post("/api/runs", json={"blueprint_id": approved.id}).status_code == 200  # free again


def test_the_timeline_can_be_followed_while_the_run_goes(client, approved, tmp_path) -> None:
    http, model = client
    model.delay = 0.03
    run_id = http.post("/api/runs", json={"blueprint_id": approved.id}).json()["run_id"]
    model.gate.set()
    seen = []
    while True:
        run = http.get(f"/api/runs/{run_id}").json()
        seen.append((run["period"], len(run["timeline"])))
        if run["status"] != "running":
            break
        time.sleep(0.02)
    periods = [p for p, _ in seen]
    assert periods == sorted(periods) and any(0 < p < 10 for p in periods)  # rising, seen mid-run
    lengths = [n for _, n in seen]
    assert lengths == sorted(lengths) and 0 < lengths[len(lengths) // 2]
    # at the end: every event, in order, the same as the run file
    timeline = run["timeline"]
    saved = json.loads((tmp_path / "runs" / f"{run_id}.json").read_text(encoding="utf-8"))["events"]
    assert [e["event_id"] for e in timeline] == [e["event_id"] for e in saved]
    assert [e["seq"] for e in timeline] == list(range(1, len(timeline) + 1))
    # `after` gives only the newer events
    newer = http.get(f"/api/runs/{run_id}", params={"after": 10}).json()["timeline"]
    assert newer[0]["seq"] == 11 and len(newer) == len(timeline) - 10


def test_a_run_that_breaks_ends_failed_not_stuck_running(client, approved, monkeypatch) -> None:
    from rulestorm import runner
    from rulestorm.core.term import Term

    http, model = client
    model.gate.set()

    class Broken(Term):  # only the runner's term breaks; the template check's dry run still works
        def run(self, on_period=None):
            raise RuntimeError("engine broke")

    monkeypatch.setattr(runner, "Term", Broken)
    run_id = http.post("/api/runs", json={"blueprint_id": approved.id}).json()["run_id"]
    done = wait_until_finished(http, run_id)
    assert done["status"] == "failed" and done["error"] == "RuntimeError: engine broke"
    assert http.post("/api/runs", json={"blueprint_id": approved.id}).status_code == 200  # not blocked


def test_unknown_and_unapproved(client, store, approved) -> None:
    from rulestorm.policy import BlueprintDraft

    http, _ = client
    assert http.get("/api/runs/L-missing").status_code == 404
    assert http.post("/api/runs", json={"blueprint_id": "B-missing"}).status_code == 404
    draft = store.save_blueprint(BlueprintDraft(
        policy_id=approved.policy_id, model_id="fake", status="valid", blueprint=approved.blueprint,
        template_id=approved.template_id, template_version=approved.template_version, attempts=1, seconds=0.0))
    assert http.post("/api/runs", json={"blueprint_id": draft.id}).status_code == 409


def test_only_one_of_several_racing_requests_starts_a_run(store, approved) -> None:
    results, barrier = [], threading.Barrier(4)

    def start(i: int) -> None:
        barrier.wait()
        results.append(store.create_run(f"L-race{i}", approved.id, "attendance@1", 10, "fake"))

    threads = [threading.Thread(target=start, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    started = [r for r in results if r is None]
    assert len(started) == 1  # the other three were told which run is running
    assert len({r for r in results if r is not None}) == 1
