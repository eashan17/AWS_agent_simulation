"""Retired recordings (26 Nov): anything stored before the cutoff reads as not found, and nothing is deleted."""

import sqlite3

from fastapi.testclient import TestClient

from rulestorm.api import app, get_store
from rulestorm.fixture import read_fixture, restore_demo
from rulestorm.store import Store

CUTOFF = "2026-11-27T00:00:00+00:00"


def _age(path: str, when: str) -> None:
    """Dates every stored row, as if it had been recorded at `when`."""
    conn = sqlite3.connect(path)
    with conn:
        conn.execute("DROP TRIGGER IF EXISTS blueprints_frozen_update")  # test data only
        conn.execute("UPDATE blueprints SET created_at = ?", (when,))
        conn.execute("UPDATE runs SET started_at = ?", (when,))
        for table in ("comparisons", "repeats", "searches"):
            conn.execute(f"UPDATE {table} SET created_at = ?", (when,))
    conn.close()


def _seed(path: str) -> dict:
    store = Store(path, retired_before="")
    restored = restore_demo(store)
    blueprint_id = read_fixture()["run"]["blueprint_id"]
    store.save_repeat({"id": "R-old", "blueprint_id": blueprint_id, "status": "completed", "created_at": "x"})
    return {**restored, "blueprint_id": blueprint_id}


def test_before_the_cutoff_reads_as_not_found(tmp_path) -> None:
    path = str(tmp_path / "test.db")
    seeded = _seed(path)
    _age(path, "2026-11-25T10:00:00+00:00")
    store = Store(path, retired_before=CUTOFF)
    assert store.get_run("demo") is None
    assert store.get_blueprint(seeded["blueprint_id"]) is None
    assert store.run_findings("demo") == [] and store.get_finding(seeded["hero"]) is None
    assert store.get_repeat("R-old") is None
    app.dependency_overrides[get_store] = lambda: store
    try:
        http = TestClient(app)
        assert http.get("/api/runs/demo").status_code == 404
        assert http.get(f"/api/blueprints/{seeded['blueprint_id']}").status_code == 404
        assert http.get(f"/api/findings/{seeded['hero']}/evidence").status_code == 404
        assert http.get("/api/repeats/R-old").status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_after_the_cutoff_is_shown_and_nothing_was_deleted(tmp_path) -> None:
    path = str(tmp_path / "test.db")
    seeded = _seed(path)
    _age(path, "2026-11-28T10:00:00+00:00")
    store = Store(path, retired_before=CUTOFF)
    assert store.get_run("demo") is not None and store.get_blueprint(seeded["blueprint_id"]) is not None
    assert store.get_finding(seeded["hero"]) is not None and store.get_repeat("R-old") is not None
    _age(path, "2026-11-25T10:00:00+00:00")
    assert Store(path, retired_before="").get_run("demo") is not None  # no cutoff: everything is back


def test_a_restored_demo_takes_its_source_run_time(tmp_path) -> None:
    """reset-demo keeps the recorded run's own start time, so a demo recorded after the cutoff stays visible."""
    path = str(tmp_path / "test.db")
    _seed(path)
    started = read_fixture()["run"]["started_at"]
    assert Store(path, retired_before="").get_run("demo")["started_at"] == started
