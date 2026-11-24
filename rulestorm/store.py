"""Storage interface + SQLite backend (WAL mode, one connection per thread)."""

import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from rulestorm.blueprint import TemplateBlueprint
from rulestorm.policy import (
    BlueprintDraft,
    BlueprintFrozen,
    BlueprintNotFound,
    BlueprintRecord,
    Policy,
    PolicyInput,
)

DEFAULT_DB_PATH = "data/rulestorm.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS policies (
    id TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    purpose TEXT NOT NULL,
    environment TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS blueprints (
    id TEXT PRIMARY KEY,
    policy_id TEXT NOT NULL REFERENCES policies(id),
    model_id TEXT NOT NULL,
    status TEXT NOT NULL,
    approved INTEGER NOT NULL DEFAULT 0,
    record TEXT NOT NULL,
    created_at TEXT NOT NULL
);
-- An approved blueprint is frozen: the database itself refuses any change or deletion,
-- so a run and its counterfactual always use the same values.
CREATE TRIGGER IF NOT EXISTS blueprints_frozen_update BEFORE UPDATE ON blueprints
WHEN OLD.approved = 1
BEGIN SELECT RAISE(ABORT, 'blueprint is approved and frozen'); END;
CREATE TRIGGER IF NOT EXISTS blueprints_frozen_delete BEFORE DELETE ON blueprints
WHEN OLD.approved = 1
BEGIN SELECT RAISE(ABORT, 'blueprint is approved and frozen'); END;
-- Daily spend caps (UTC day). Taken atomically: UPDATE ... WHERE n < cap; rowcount 0 = over the cap.
CREATE TABLE IF NOT EXISTS daily_usage (
    date TEXT PRIMARY KEY,
    runs INTEGER NOT NULL DEFAULT 0,
    llm_calls INTEGER NOT NULL DEFAULT 0,
    blueprint_calls INTEGER NOT NULL DEFAULT 0
);
-- Runs (slice 7a): one row per run, its events saved after each period so the timeline can be
-- followed while it runs.
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    blueprint_id TEXT NOT NULL REFERENCES blueprints(id),
    template TEXT NOT NULL,
    status TEXT NOT NULL,
    period INTEGER NOT NULL DEFAULT 0,
    periods INTEGER NOT NULL,
    model_id TEXT NOT NULL,
    summary TEXT,
    error TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT
);
CREATE TABLE IF NOT EXISTS events (
    run_id TEXT NOT NULL REFERENCES runs(id),
    seq INTEGER NOT NULL,
    event TEXT NOT NULL,
    PRIMARY KEY (run_id, seq)
);
"""

USAGE_COUNTERS = ("runs", "llm_calls", "blueprint_calls")
RUN_FIELDS = ("status", "period", "summary", "error", "finished_at")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    """The one storage interface the core, API and CLI use."""

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or os.environ.get("RULESTORM_DB_PATH") or DEFAULT_DB_PATH
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._conn().executescript(_SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn = conn
        return conn

    def take_daily(self, counter: str, cap: int) -> bool:
        """Takes one unit of today's `counter` if it is under `cap`; safe across threads and processes."""
        if counter not in USAGE_COUNTERS:
            raise ValueError(f"unknown usage counter {counter!r}")
        today = datetime.now(timezone.utc).date().isoformat()
        conn = self._conn()
        with conn:
            conn.execute("INSERT OR IGNORE INTO daily_usage (date) VALUES (?)", (today,))
            cursor = conn.execute(
                f"UPDATE daily_usage SET {counter} = {counter} + 1 WHERE date = ? AND {counter} < ?",
                (today, cap),
            )
        return cursor.rowcount == 1

    def daily_usage(self) -> dict[str, int]:
        today = datetime.now(timezone.utc).date().isoformat()
        row = self._conn().execute("SELECT * FROM daily_usage WHERE date = ?", (today,)).fetchone()
        return {c: (row[c] if row else 0) for c in USAGE_COUNTERS}

    def save_policy(self, data: PolicyInput) -> Policy:
        policy = Policy(
            id=f"P-{uuid.uuid4().hex[:8]}",
            created_at=_now(),
            **data.model_dump(),
        )
        conn = self._conn()
        with conn:
            conn.execute(
                "INSERT INTO policies (id, text, purpose, environment, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (policy.id, policy.text, policy.purpose, policy.environment, policy.created_at),
            )
        return policy

    def get_policy(self, policy_id: str) -> Policy | None:
        row = self._conn().execute(
            "SELECT * FROM policies WHERE id = ?", (policy_id,)
        ).fetchone()
        return Policy(**dict(row)) if row else None

    def save_blueprint(self, draft: BlueprintDraft) -> BlueprintRecord:
        record = BlueprintRecord(
            id=f"B-{uuid.uuid4().hex[:8]}", created_at=_now(), **draft.model_dump()
        )
        conn = self._conn()
        with conn:
            conn.execute(
                "INSERT INTO blueprints (id, policy_id, model_id, status, approved, record, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    record.id,
                    record.policy_id,
                    record.model_id,
                    record.status,
                    int(record.approved),
                    record.model_dump_json(),
                    record.created_at,
                ),
            )
        return record

    def get_blueprint(self, blueprint_id: str) -> BlueprintRecord | None:
        row = self._conn().execute(
            "SELECT record, approved FROM blueprints WHERE id = ?", (blueprint_id,)
        ).fetchone()
        if row is None:
            return None
        record = BlueprintRecord.model_validate_json(row["record"])
        record.approved = bool(row["approved"])
        return record

    def list_variants(self, parent_id: str) -> list[BlueprintRecord]:
        """Stress variants of one approved blueprint, oldest first."""
        # Filtered in SQL, so blueprints in an older format (before slice 3c) are never parsed.
        rows = self._conn().execute(
            "SELECT record, approved FROM blueprints WHERE json_extract(record, '$.parent_id') = ? "
            "ORDER BY created_at, rowid",
            (parent_id,),
        ).fetchall()
        variants = []
        for row in rows:
            record = BlueprintRecord.model_validate_json(row["record"])
            record.approved = bool(row["approved"])
            variants.append(record)
        return variants

    def mark_approved(self, blueprint_id: str) -> bool:
        """Only a valid, not-yet-approved blueprint changes; returns whether it did."""
        conn = self._conn()
        with conn:
            cursor = conn.execute(
                "UPDATE blueprints SET approved = 1 WHERE id = ? AND status = 'valid' AND approved = 0",
                (blueprint_id,),
            )
        return cursor.rowcount == 1

    # --- runs ---------------------------------------------------------------------------------

    def create_run(self, run_id: str, blueprint_id: str, template: str, periods: int, model_id: str,
                   only_if_none_running: bool = True) -> str | None:
        """Adds a running run. With `only_if_none_running`, the insert happens only if no run is
        running, in one statement, so two requests can't both start one; returns the running run's
        ID instead when there is one (else None)."""
        conn = self._conn()
        guard = "WHERE NOT EXISTS (SELECT 1 FROM runs WHERE status = 'running')" if only_if_none_running else ""
        with conn:
            cursor = conn.execute(
                "INSERT INTO runs (id, blueprint_id, template, status, period, periods, model_id, started_at) "
                f"SELECT ?, ?, ?, 'running', 0, ?, ?, ? {guard}",
                (run_id, blueprint_id, template, periods, model_id, _now()),
            )
        if cursor.rowcount == 1:
            return None
        running = conn.execute("SELECT id FROM runs WHERE status = 'running' LIMIT 1").fetchone()
        return running["id"] if running else None

    def update_run(self, run_id: str, **fields) -> None:
        unknown = set(fields) - set(RUN_FIELDS)
        if unknown:
            raise ValueError(f"unknown run fields {sorted(unknown)}")
        if "summary" in fields and not isinstance(fields["summary"], (str, type(None))):
            fields["summary"] = json.dumps(fields["summary"], ensure_ascii=False)
        conn = self._conn()
        with conn:
            conn.execute(f"UPDATE runs SET {', '.join(f'{k} = ?' for k in fields)} WHERE id = ?",
                         (*fields.values(), run_id))

    def add_events(self, run_id: str, events: list[dict]) -> None:
        conn = self._conn()
        with conn:
            conn.executemany("INSERT INTO events (run_id, seq, event) VALUES (?, ?, ?)",
                             [(run_id, e["seq"], json.dumps(e, ensure_ascii=False)) for e in events])

    def get_run(self, run_id: str) -> dict | None:
        row = self._conn().execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            return None
        run = dict(row)
        run["summary"] = json.loads(run["summary"]) if run["summary"] else None
        return run

    def run_events(self, run_id: str, after_seq: int = 0) -> list[dict]:
        rows = self._conn().execute(
            "SELECT event FROM events WHERE run_id = ? AND seq > ? ORDER BY seq", (run_id, after_seq)).fetchall()
        return [json.loads(r["event"]) for r in rows]

    def update_blueprint(self, blueprint_id: str, blueprint: TemplateBlueprint) -> BlueprintRecord:
        """Edit a blueprint before approval (e.g. corrected assumptions). Refused once approved."""
        record = self.get_blueprint(blueprint_id)
        if record is None:
            raise BlueprintNotFound(blueprint_id)
        if record.approved:
            raise BlueprintFrozen(blueprint_id)
        record = record.model_copy(update={"blueprint": blueprint, "status": "valid", "errors": []})
        conn = self._conn()
        try:
            with conn:
                conn.execute(
                    "UPDATE blueprints SET status = ?, record = ? WHERE id = ?",
                    (record.status, record.model_dump_json(), blueprint_id),
                )
        except sqlite3.IntegrityError as exc:  # approved between the check and the write
            raise BlueprintFrozen(blueprint_id) from exc
        return record
