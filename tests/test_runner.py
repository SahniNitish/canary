"""End-to-end on the REAL collector output: ingest, run status, detection, heal prompt.

These use the committed fixtures/ikea_*.json — the actual JSON `bdata scraper run` returned
and the broken variants derived from it (one mutation each). They are the proof the engine
works against the real schema, not a hand-authored guess.
"""

import json
from pathlib import Path

import pytest

from canary import config, db, heal, models, runner, signals

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
COLLECTOR = "c_test"


def _ingest(conn, name):
    return runner.ingest_fixture(conn, str(FIXTURES / name), collector_id=COLLECTOR)


def _records(name):
    return json.loads((FIXTURES / name).read_text())


def test_real_baseline_is_ok_and_keyed_by_url(conn):
    run = _ingest(conn, "ikea_baseline.json")
    assert run.status == models.RUN_OK
    assert run.row_count == 6
    records = db.get_records(conn, run.run_id)
    assert all(k.startswith("https://www.ikea.com/") for k in records)  # recall_key = source_url


def test_dropped_hazard_makes_run_partial(conn):
    assert _ingest(conn, "ikea_broken_hazard.json").status == models.RUN_PARTIAL


def test_empty_run_is_empty_not_failed(conn):
    run = _ingest(conn, "ikea_empty.json")
    assert run.status == models.RUN_EMPTY
    assert db.get_records(conn, run.run_id) == {}


def test_all_error_rows_is_failed_and_writes_no_records(conn):
    raw = [{"error": "Crawler error: 403", "error_code": "proxy_config", "input": {"url": "u1"}}]
    run = runner.ingest_records(conn, records_raw=raw, collector_id=COLLECTOR)
    assert run.status == models.RUN_FAILED
    assert run.row_count is None
    assert db.get_records(conn, run.run_id) == {}
    assert run.error_code == "proxy_config"


def _detect(conn, broken_name):
    base = _ingest(conn, "ikea_baseline.json")
    cur = _ingest(conn, broken_name)
    return signals.detect(
        baseline=db.get_records(conn, base.run_id),
        current=db.get_records(conn, cur.run_id),
        baseline_run_id=base.run_id, current_run_id=cur.run_id,
    )


def test_hazard_drop_fires_critical_null_rate(conn):
    sigs = _detect(conn, "ikea_broken_hazard.json")
    hazard = [s for s in sigs if s.kind == models.KIND_NULL_RATE and s.field == "hazard"]
    assert hazard and hazard[0].severity == models.SEV_CRITICAL
    assert "6/6" in hazard[0].detail and "0/6" in hazard[0].detail


def test_remedy_key_removal_fires_schema_drift(conn):
    sigs = _detect(conn, "ikea_broken_schema.json")
    assert any(s.kind == models.KIND_SCHEMA_DRIFT and s.field == "remedy" for s in sigs)


def test_missing_rows_fire_rowcount_volume_anomaly(conn):
    sigs = _detect(conn, "ikea_broken_rowcount.json")
    row = [s for s in sigs if s.kind == models.KIND_ROWCOUNT]
    assert row and "volume anomaly" in row[0].detail   # honest: no membership oracle


def test_heal_prompt_is_specific_and_within_cap(conn):
    sigs = _detect(conn, "ikea_broken_hazard.json")
    hazard = next(s for s in sigs if s.field == "hazard")
    prompt = heal.prompt_for(
        hazard, example_url="https://www.ikea.com/us/en/.../pub.../",
        expected_shape=config.EXPECTED_SHAPES["hazard"],
    )
    assert len(prompt) <= heal.HEAL_CHAR_CAP
    assert "hazard" in prompt and "preserve the existing output schema" in prompt


def test_heal_prompt_never_exceeds_cap_even_when_detail_is_huge(conn):
    big = models.Signal(run_id=1, kind=models.KIND_NULL_RATE, severity=models.SEV_CRITICAL,
                        detail="x" * 5000, field="hazard")
    assert len(heal.prompt_for(big, expected_shape="y" * 5000)) <= heal.HEAL_CHAR_CAP


def test_summarize_preview_counts_hazard():
    envelope = {
        "status": "awaiting_approval",
        "preview_result": [
            {"hazard": "tip-over", "source_url": "https://www.ikea.com/a"},
            {"hazard": "", "source_url": "https://www.ikea.com/b"},
        ],
    }
    summary = heal.summarize_preview(envelope, field="hazard")
    assert "hazard_populated=1/2" in summary
    assert "status=awaiting_approval" in summary
