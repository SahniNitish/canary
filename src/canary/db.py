"""SQLite persistence for Canary.

Design rules that this module enforces structurally, not by convention:

* Runs and records are **append-only**. There is no `update_run` / `update_record`. A
  second `insert_records` for the same `(run_id, recall_key)` raises `IntegrityError` by
  design — never upsert, because the temporal comparison dies without an intact baseline.
* Payloads are stored **raw as JSON text**. No typed columns for scraped fields.
* `status` / `severity` / `resolution` domains are enforced with CHECK constraints so an
  absent run can never be confused with a failed one.

Only workflow state (`signals.resolution`, `heal_attempts`) is mutable — that is the
human-in-the-loop gate, not a run snapshot.
"""

from __future__ import annotations

import json
import os
import sqlite3
from typing import Any, Optional

from . import models
from .models import HealAttempt, Record, Run, Signal

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  run_id        INTEGER PRIMARY KEY,
  collector_id  TEXT    NOT NULL,
  source        TEXT    NOT NULL,
  started_at    TEXT    NOT NULL,
  row_count     INTEGER,
  status        TEXT    NOT NULL CHECK (status IN ('ok','empty','partial','failed')),
  collection_id TEXT,
  completed_at  TEXT,
  input_count   INTEGER,
  error_code    TEXT,
  error_detail  TEXT
);

CREATE TABLE IF NOT EXISTS records (
  run_id      INTEGER NOT NULL REFERENCES runs(run_id),
  recall_key  TEXT    NOT NULL,
  payload     TEXT    NOT NULL,   -- raw JSON, unmodified
  PRIMARY KEY (run_id, recall_key)
);

CREATE TABLE IF NOT EXISTS signals (
  signal_id       INTEGER PRIMARY KEY,
  run_id          INTEGER NOT NULL REFERENCES runs(run_id),
  kind            TEXT    NOT NULL,
  field           TEXT,
  severity        TEXT    NOT NULL CHECK (severity IN ('info','warn','critical')),
  detail          TEXT    NOT NULL,
  baseline_run_id INTEGER REFERENCES runs(run_id),
  heal_prompt     TEXT,
  resolution      TEXT    NOT NULL DEFAULT 'pending'
                          CHECK (resolution IN ('pending','approved','rejected','ignored'))
);

CREATE TABLE IF NOT EXISTS heal_attempts (
  attempt_id        INTEGER PRIMARY KEY,
  signal_id         INTEGER NOT NULL REFERENCES signals(signal_id),
  created_at        TEXT    NOT NULL,
  prompt            TEXT    NOT NULL,
  status            TEXT    NOT NULL,
  preview_payload   TEXT,
  validation_result TEXT,
  view_url          TEXT,
  decided_at        TEXT,
  decision_reason   TEXT
);

CREATE INDEX IF NOT EXISTS idx_runs_source_started ON runs (source, started_at);
CREATE INDEX IF NOT EXISTS idx_signals_run ON signals (run_id);
CREATE INDEX IF NOT EXISTS idx_heal_signal ON heal_attempts (signal_id);
"""


def connect(path: str) -> sqlite3.Connection:
    """Open a connection with foreign keys enforced and row access by name."""
    if path != ":memory:":
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(path: str) -> sqlite3.Connection:
    """Create the schema if absent and return an open connection."""
    conn = connect(path)
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


# --------------------------------------------------------------------------- writes

def insert_run(conn: sqlite3.Connection, run: Run) -> int:
    """Append a run snapshot. Returns the new run_id."""
    if run.status not in models.RUN_STATUSES:
        raise ValueError(f"invalid run status: {run.status!r}")
    cur = conn.execute(
        """
        INSERT INTO runs (collector_id, source, started_at, row_count, status,
                          collection_id, completed_at, input_count, error_code, error_detail)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (run.collector_id, run.source, run.started_at, run.row_count, run.status,
         run.collection_id, run.completed_at, run.input_count, run.error_code, run.error_detail),
    )
    conn.commit()
    run.run_id = int(cur.lastrowid)
    return run.run_id


def insert_records(conn: sqlite3.Connection, run_id: int, records: list[Record]) -> int:
    """Append records for a run. Plain INSERT — a duplicate (run_id, recall_key) raises.

    A `failed` run must call this with an empty list (it writes no records).
    """
    rows = [(run_id, r.recall_key, json.dumps(r.payload, ensure_ascii=False)) for r in records]
    conn.executemany(
        "INSERT INTO records (run_id, recall_key, payload) VALUES (?, ?, ?)", rows
    )
    conn.commit()
    return len(rows)


def insert_signal(conn: sqlite3.Connection, signal: Signal) -> int:
    cur = conn.execute(
        """
        INSERT INTO signals (run_id, kind, field, severity, detail,
                             baseline_run_id, heal_prompt, resolution)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (signal.run_id, signal.kind, signal.field, signal.severity, signal.detail,
         signal.baseline_run_id, signal.heal_prompt, signal.resolution),
    )
    conn.commit()
    signal.signal_id = int(cur.lastrowid)
    return signal.signal_id


def set_signal_resolution(conn: sqlite3.Connection, signal_id: int, resolution: str) -> None:
    if resolution not in models.RESOLUTIONS:
        raise ValueError(f"invalid resolution: {resolution!r}")
    conn.execute(
        "UPDATE signals SET resolution = ? WHERE signal_id = ?", (resolution, signal_id)
    )
    conn.commit()


def insert_heal_attempt(conn: sqlite3.Connection, attempt: HealAttempt) -> int:
    cur = conn.execute(
        """
        INSERT INTO heal_attempts (signal_id, created_at, prompt, status, preview_payload,
                                   validation_result, view_url, decided_at, decision_reason)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (attempt.signal_id, attempt.created_at, attempt.prompt, attempt.status,
         attempt.preview_payload, attempt.validation_result, attempt.view_url,
         attempt.decided_at, attempt.decision_reason),
    )
    conn.commit()
    attempt.attempt_id = int(cur.lastrowid)
    return attempt.attempt_id


def decide_heal_attempt(
    conn: sqlite3.Connection,
    attempt_id: int,
    status: str,
    decided_at: str,
    decision_reason: Optional[str] = None,
    preview_payload: Optional[str] = None,
    validation_result: Optional[str] = None,
    view_url: Optional[str] = None,
) -> None:
    conn.execute(
        """
        UPDATE heal_attempts
           SET status = ?, decided_at = ?, decision_reason = ?,
               preview_payload = COALESCE(?, preview_payload),
               validation_result = COALESCE(?, validation_result),
               view_url = COALESCE(?, view_url)
         WHERE attempt_id = ?
        """,
        (status, decided_at, decision_reason, preview_payload,
         validation_result, view_url, attempt_id),
    )
    conn.commit()


# --------------------------------------------------------------------------- reads

def _row_to_run(row: sqlite3.Row) -> Run:
    return Run(
        run_id=row["run_id"], collector_id=row["collector_id"], source=row["source"],
        started_at=row["started_at"], row_count=row["row_count"], status=row["status"],
        collection_id=row["collection_id"], completed_at=row["completed_at"],
        input_count=row["input_count"], error_code=row["error_code"],
        error_detail=row["error_detail"],
    )


def get_run(conn: sqlite3.Connection, run_id: int) -> Optional[Run]:
    row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    return _row_to_run(row) if row else None


def get_latest_run(conn: sqlite3.Connection, source: str) -> Optional[Run]:
    row = conn.execute(
        "SELECT * FROM runs WHERE source = ? ORDER BY run_id DESC LIMIT 1", (source,)
    ).fetchone()
    return _row_to_run(row) if row else None


def get_previous_run(
    conn: sqlite3.Connection, source: str, before_run_id: int
) -> Optional[Run]:
    """The immediately prior run for a source. Kept for diagnostics only — detection
    baselines on the last *verified* run (`get_last_known_good`), never blindly on N-1."""
    row = conn.execute(
        "SELECT * FROM runs WHERE source = ? AND run_id < ? ORDER BY run_id DESC LIMIT 1",
        (source, before_run_id),
    ).fetchone()
    return _row_to_run(row) if row else None


def get_last_known_good(
    conn: sqlite3.Connection, source: str, before_run_id: Optional[int] = None
) -> Optional[Run]:
    """The most recent `ok` run for a source (optionally strictly before a given run).

    This is the health baseline: a broken/partial run must never become the baseline, or
    a persistent failure silently becomes the new normal.
    """
    if before_run_id is None:
        row = conn.execute(
            "SELECT * FROM runs WHERE source = ? AND status = 'ok' ORDER BY run_id DESC LIMIT 1",
            (source,),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM runs WHERE source = ? AND status = 'ok' AND run_id < ? "
            "ORDER BY run_id DESC LIMIT 1",
            (source, before_run_id),
        ).fetchone()
    return _row_to_run(row) if row else None


def get_records(conn: sqlite3.Connection, run_id: int) -> dict[str, dict[str, Any]]:
    """Return {recall_key: payload} for a run, payloads parsed back from JSON."""
    rows = conn.execute(
        "SELECT recall_key, payload FROM records WHERE run_id = ?", (run_id,)
    ).fetchall()
    return {row["recall_key"]: json.loads(row["payload"]) for row in rows}


def get_signals(conn: sqlite3.Connection, run_id: int) -> list[Signal]:
    rows = conn.execute(
        "SELECT * FROM signals WHERE run_id = ? ORDER BY signal_id", (run_id,)
    ).fetchall()
    return [
        Signal(
            signal_id=r["signal_id"], run_id=r["run_id"], kind=r["kind"], field=r["field"],
            severity=r["severity"], detail=r["detail"], baseline_run_id=r["baseline_run_id"],
            heal_prompt=r["heal_prompt"], resolution=r["resolution"],
        )
        for r in rows
    ]
