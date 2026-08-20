"""DB invariants: append-only snapshots, distinct run statuses, last-known-good baseline.

These are the structural guarantees the whole product rests on, so they are tested
directly rather than only through the higher layers.
"""

import sqlite3

import pytest

from canary import db, models
from canary.models import HealAttempt, Record, Run, Signal


def _run(source="healthcanada", status=models.RUN_OK, row_count=3, collector="c_test") -> Run:
    return Run(
        collector_id=collector, source=source, started_at="2026-08-19T10:00:00",
        row_count=row_count, status=status,
    )


def test_insert_run_and_records_roundtrip(conn):
    run_id = db.insert_run(conn, _run())
    db.insert_records(conn, run_id, [
        Record(run_id, "RA-1", {"company": "Acme", "product": "Pump"}),
        Record(run_id, "RA-2", {"company": "Globex", "product": "Valve"}),
    ])
    records = db.get_records(conn, run_id)
    assert set(records) == {"RA-1", "RA-2"}
    assert records["RA-1"]["company"] == "Acme"  # payload survives raw


def test_records_are_append_only_never_upsert(conn):
    """Re-inserting the same (run_id, recall_key) must fail, not overwrite the baseline."""
    run_id = db.insert_run(conn, _run())
    db.insert_records(conn, run_id, [Record(run_id, "RA-1", {"company": "Acme"})])
    with pytest.raises(sqlite3.IntegrityError):
        db.insert_records(conn, run_id, [Record(run_id, "RA-1", {"company": "TAMPERED"})])
    assert db.get_records(conn, run_id)["RA-1"]["company"] == "Acme"


def test_invalid_status_is_rejected(conn):
    with pytest.raises(ValueError):
        db.insert_run(conn, _run(status="broken"))


def test_empty_and_failed_runs_are_distinguishable(conn):
    """An absent/empty run must never be confused with a failed one (CLAUDE.md §5)."""
    empty_id = db.insert_run(conn, _run(status=models.RUN_EMPTY, row_count=0))
    failed_id = db.insert_run(conn, _run(status=models.RUN_FAILED, row_count=None))
    # A failed run writes NO records; an empty run also has none but is a different status.
    assert db.get_run(conn, empty_id).status == models.RUN_EMPTY
    assert db.get_run(conn, failed_id).status == models.RUN_FAILED
    assert db.get_records(conn, failed_id) == {}


def test_last_known_good_skips_broken_runs(conn):
    """The baseline is the last verified run — a later partial run must not become it."""
    good = db.insert_run(conn, _run(status=models.RUN_OK))
    db.insert_run(conn, _run(status=models.RUN_PARTIAL))       # newer, but broken
    db.insert_run(conn, _run(status=models.RUN_FAILED))        # newer, but broken
    baseline = db.get_last_known_good(conn, "healthcanada")
    assert baseline.run_id == good  # not the newer broken runs


def test_last_known_good_before_run_is_strict(conn):
    first_good = db.insert_run(conn, _run(status=models.RUN_OK))
    broken = db.insert_run(conn, _run(status=models.RUN_PARTIAL))
    # Baseline for the broken run is the good run strictly before it.
    assert db.get_last_known_good(conn, "healthcanada", before_run_id=broken).run_id == first_good


def test_signal_and_heal_attempt_persist(conn):
    run_id = db.insert_run(conn, _run(status=models.RUN_PARTIAL))
    baseline = db.insert_run(conn, _run(status=models.RUN_OK))
    sig = Signal(
        run_id=run_id, kind=models.KIND_NULL_RATE, severity=models.SEV_CRITICAL,
        detail="company null on 3/3 rows", field="company", baseline_run_id=baseline,
        heal_prompt="fix company",
    )
    signal_id = db.insert_signal(conn, sig)
    assert db.get_signals(conn, run_id)[0].resolution == models.RES_PENDING

    a1 = db.insert_heal_attempt(conn, HealAttempt(
        signal_id=signal_id, created_at="2026-08-19T10:05:00", prompt="v1 prompt", status="pending",
    ))
    a2 = db.insert_heal_attempt(conn, HealAttempt(
        signal_id=signal_id, created_at="2026-08-19T10:20:00", prompt="v2 sharper prompt", status="pending",
    ))
    # Two attempts coexist — the reject -> retry history is preserved, not overwritten.
    assert a1 != a2
    db.decide_heal_attempt(conn, a1, status="rejected", decided_at="2026-08-19T10:10:00",
                           decision_reason="preview still null")
    db.set_signal_resolution(conn, signal_id, models.RES_APPROVED)
    assert db.get_signals(conn, run_id)[0].resolution == models.RES_APPROVED


def test_severity_check_constraint(conn):
    run_id = db.insert_run(conn, _run())
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO signals (run_id, kind, severity, detail) VALUES (?, 'null_rate', 'boom', 'x')",
            (run_id,),
        )
