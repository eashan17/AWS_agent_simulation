"""Slice 10: the seeded demo run, a real recorded run, restored with one command (no model)."""

import json

import pytest
from fastapi.testclient import TestClient

from rulestorm import llm
from rulestorm.api import app, get_store
from rulestorm.fixture import (DEFAULT_PATH, SCHEMA, FixtureError, check_blueprint, export_run, read_fixture,
                               restore_demo)
from rulestorm.store import Store

HERO_TITLE = "Students fall below the attendance threshold and lose exam eligibility"


@pytest.fixture(scope="module")
def bundle():
    return read_fixture(DEFAULT_PATH)


@pytest.fixture
def store(tmp_path) -> Store:
    return Store(str(tmp_path / "test.db"))


# --- the committed file ---------------------------------------------------------------------------

def test_the_file_is_utf8_without_a_bom_and_in_this_schema(bundle) -> None:
    raw = DEFAULT_PATH.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    raw.decode("utf-8")  # strict: raises on anything else
    assert bundle["schema"] == SCHEMA == 2


def test_the_bundled_blueprint_still_fits_its_template(bundle) -> None:
    record, template = check_blueprint(bundle)
    assert record.approved and record.status == "valid" and record.id == bundle["run"]["blueprint_id"]
    assert f"{template.id}@{template.version}" == bundle["run"]["template"]
    assert bundle["policy"]["id"] == record.policy_id


def test_it_is_a_real_finished_run_with_no_model_errors_and_the_hero(bundle) -> None:
    run = bundle["run"]
    assert run["status"] == "completed" and run["model_id"] != "fake" and run["period"] == run["periods"]
    assert run["summary"]["llm_errors"] == 0 and run["summary"]["llm_calls"] > 0
    assert run["summary"]["decisions"] > 0
    hero = bundle["hero"]
    assert hero["kind"] == "check_failed" and hero["title"] == HERO_TITLE
    assert any(f["finding_id"] == hero["finding_id"] for f in bundle["findings"])
    assert [e["seq"] for e in bundle["events"]] == list(range(1, len(bundle["events"]) + 1))


def test_the_file_holds_no_account_id_arn_or_access_key() -> None:
    text = DEFAULT_PATH.read_text(encoding="utf-8")
    assert llm.redact(text) == text


# --- restoring it ---------------------------------------------------------------------------------

def test_reset_demo_restores_the_run_its_findings_and_their_evidence(store, bundle) -> None:
    restored = restore_demo(store)
    assert restored["run_id"] == "demo" and restored["schema"] == SCHEMA and restored["hero"] == "demo-F1"
    app.dependency_overrides[get_store] = lambda: store
    try:
        http = TestClient(app)
        run = http.get("/api/runs/demo").json()
        assert run["status"] == "completed" and len(run["timeline"]) == len(bundle["events"])
        findings = http.get("/api/runs/demo/findings").json()["findings"]
        assert [(f["kind"], f["person"]) for f in findings] == [(f["kind"], f["person"]) for f in bundle["findings"]]
        hero = next(f for f in findings if f["finding_id"] == "demo-F1")
        assert hero["title"] == HERO_TITLE and hero["chain"] == bundle["findings"][0]["chain"]
        evidence = http.get("/api/findings/demo-F1/evidence").json()
        assert evidence["steps"][-1]["calculation"]["matches_recorded"] is True
    finally:
        app.dependency_overrides.clear()
    assert store.get_blueprint(bundle["run"]["blueprint_id"]).approved
    assert store.get_policy(bundle["policy"]["id"]) is not None


def test_reset_demo_twice_gives_the_same_demo(store) -> None:
    first = restore_demo(store)
    again = restore_demo(store)  # the frozen blueprint is already there: kept, not rewritten
    assert first == again
    assert len(store.run_findings("demo")) == first["findings"]
    assert len(store.run_events("demo")) == first["events"]


def test_a_file_with_a_bom_or_another_schema_is_refused(tmp_path, store) -> None:
    text = DEFAULT_PATH.read_text(encoding="utf-8")
    bom = tmp_path / "bom.json"
    bom.write_bytes(b"\xef\xbb\xbf" + text.encode("utf-8"))
    with pytest.raises(FixtureError, match="byte-order mark"):
        restore_demo(store, bom)
    old = tmp_path / "old.json"
    old.write_text(json.dumps({**json.loads(text), "schema": 1}), encoding="utf-8")
    with pytest.raises(FixtureError, match="schema 1"):
        restore_demo(store, old)
    assert store.get_run("demo") is None  # nothing half-restored


def test_only_a_finished_run_with_a_finding_can_be_exported(store) -> None:
    with pytest.raises(FixtureError, match="run not found"):
        export_run(store, "L-missing")
    restore_demo(store)
    exported = export_run(store, "demo", hero="demo-F1")
    assert exported["hero"]["finding_id"] == "demo-F1" and exported["schema"] == SCHEMA
    with pytest.raises(FixtureError, match="no finding"):
        export_run(store, "demo", hero="demo-F9")
