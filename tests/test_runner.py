"""Slices 7a and 7b: runs in the background, one at a time, followed by polling; daily caps,
interrupted runs and clean errors (fake model; no Bedrock)."""

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
    assert running["status"] == "running" and running["periods"] == 10 and running["template"] == "attendance@2"
    assert running["run_id"] == run_id

    model.gate.set()
    done = wait_until_finished(http, run_id)
    assert done["status"] in ("completed", "degraded") and done["period"] == 10
    assert done["summary"]["decisions"] > 0 and done["finished_at"]
    assert http.post("/api/runs", json={"blueprint_id": approved.id}).status_code == 200  # free again


def test_a_finished_run_has_its_findings_saved_from_its_own_events(client, approved, store) -> None:
    from rulestorm.core.model import load_template
    from rulestorm.detect import detect

    http, model = client
    model.gate.set()
    run_id = http.post("/api/runs", json={"blueprint_id": approved.id}).json()["run_id"]
    wait_until_finished(http, run_id)
    expected = detect(run_id, store.run_events(run_id), load_template("attendance"))
    assert store.run_findings(run_id) == [f.model_dump() for f in expected]  # saved by the runner itself
    assert http.get(f"/api/runs/{run_id}/findings").json()["findings"] == store.run_findings(run_id)


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


# --- slice 7b: spending stays capped and broken runs are visible, not stuck ---------------------

LEAKY = ("User: arn:aws:sts::123456789012:assumed-role/rulestorm-ec2/i-0abc12 is not authorized "
         "to perform bedrock:Converse; access key AKIAABCDEFGHIJKLMNOP")


def test_a_running_run_at_startup_becomes_failed_interrupted(store, approved, tmp_path) -> None:
    from rulestorm.runner import INTERRUPTED

    store.create_run("L-cutoff", approved.id, "attendance@1", 10, "fake")
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_agent_model] = lambda: RoutedModel()
    app.dependency_overrides[get_runs_dir] = lambda: str(tmp_path / "runs")
    try:
        with TestClient(app) as http:  # `with` runs the app's startup
            cut = http.get("/api/runs/L-cutoff").json()
            assert cut["status"] == "failed" and cut["error"] == INTERRUPTED and cut["finished_at"]
            assert http.post("/api/runs", json={"blueprint_id": approved.id}).status_code == 200  # not blocked
    finally:
        app.dependency_overrides.clear()


def test_four_threads_racing_for_one_remaining_call_exactly_one_succeeds(store, monkeypatch) -> None:
    from rulestorm.agents import CallBudget, CallCapReached, CappedModel

    monkeypatch.setenv("MAX_LLM_CALLS_PER_DAY", "5")
    for _ in range(4):
        assert store.take_daily("llm_calls", 5)  # 1 call left today
    reached = []
    model = CappedModel(RoutedModel(lambda person, prompt: (reached.append(1), NOTHING)[1]), CallBudget(100), store)
    barrier, results = threading.Barrier(4), []

    def call() -> None:
        barrier.wait()
        try:
            model.complete("You are the student agent `commuter`", 100)
            results.append("ok")
        except CallCapReached as exc:
            results.append(str(exc))

    threads = [threading.Thread(target=call) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count("ok") == 1 and len(reached) == 1  # exactly one reached the model
    assert results.count("daily call cap of 5 reached") == 3
    assert store.daily_usage()["llm_calls"] == 5
    assert model.budget.used == 1 and model.budget.cap_hits == 1  # the run's own budget counts only the real call


def test_a_failed_runs_get_shows_a_clean_short_error_and_the_log_has_it_all(client, approved, monkeypatch,
                                                                            caplog) -> None:
    from rulestorm import runner
    from rulestorm.core.term import Term

    http, model = client
    model.gate.set()

    class Broken(Term):
        def run(self, on_period=None):
            raise PermissionError(LEAKY)

    monkeypatch.setattr(runner, "Term", Broken)
    with caplog.at_level("ERROR", logger="rulestorm.runner"):
        run_id = http.post("/api/runs", json={"blueprint_id": approved.id}).json()["run_id"]
        done = wait_until_finished(http, run_id)
    shown = done["error"]
    assert done["status"] == "failed" and shown.startswith("PermissionError: User: <arn> is not authorized")
    for secret in ("123456789012", "arn:aws", "AKIAABCDEFGHIJKLMNOP", "rulestorm-ec2"):
        assert secret not in shown and secret not in json.dumps(http.get(f"/api/runs/{run_id}").json())
    assert len(shown) <= len("PermissionError: ") + runner.SHORT_ERROR_CHARS + 1
    assert any("123456789012" in r.getMessage() + str(r.exc_info) for r in caplog.records)  # full error: log only


def test_a_model_error_in_the_timeline_is_cleaned_too() -> None:
    from rulestorm import llm
    from rulestorm.agents import AgentDecision

    class Denied:
        model_id = "fake"

        def complete(self, prompt, max_tokens, timeout_s=None):
            raise PermissionError(LEAKY)

    error = llm.decide("prompt", AgentDecision, model=Denied()).error
    assert error.startswith("PermissionError: User: <arn> is not authorized") and "<access key>" in error
    assert "123456789012" not in error and "arn:aws" not in error


def test_the_daily_run_cap_gives_429_but_a_running_run_still_gives_409(client, approved, monkeypatch) -> None:
    http, model = client
    first = http.post("/api/runs", json={"blueprint_id": approved.id}).json()["run_id"]
    monkeypatch.setenv("MAX_RUNS_PER_DAY", "0")
    busy = http.post("/api/runs", json={"blueprint_id": approved.id})
    assert busy.status_code == 409 and busy.json()["run_id"] == first  # the running run comes first, costs nothing
    model.gate.set()
    wait_until_finished(http, first)
    capped = http.post("/api/runs", json={"blueprint_id": approved.id})
    assert capped.status_code == 429 and "daily run limit" in capped.json()["detail"]
