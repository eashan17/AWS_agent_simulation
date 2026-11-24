"""Storage interface + SQLite backend (WAL mode, one connection per thread)."""

import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from rulestorm.policy import BlueprintDraft, BlueprintRecord, Policy, PolicyInput

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
"""


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
