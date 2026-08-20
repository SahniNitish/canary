"""Turn collector output into an immutable run — from a saved fixture or a live scrape.

The live path shells out to the `bdata` CLI. That is a **deliberate temporary adapter**:
`POST /dca/trigger` returns a `j_*` collection id that must be polled, not rows, and the
CLI already does that polling. It is invoked with an argument list (`shell=False`) so a URL
or prompt can never be interpolated into a shell string.
"""

from __future__ import annotations

import datetime
import json
import subprocess
import tempfile
from typing import Any, Optional

from . import config, db, models
from .models import Record, Run


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _as_list(raw: Any) -> list[dict]:
    """Collector output is a JSON array of objects; tolerate a few envelope shapes."""
    if isinstance(raw, list):
        return [r for r in raw if isinstance(r, dict)]
    if isinstance(raw, dict):
        for k in ("data", "results", "items", "records"):
            if isinstance(raw.get(k), list):
                return [r for r in raw[k] if isinstance(r, dict)]
        return [raw]
    return []


def _recall_key(payload: dict, i: int) -> str:
    key = payload.get(config.RECALL_KEY_FIELD)
    if not key:
        key = payload.get("input", {}).get("url") if isinstance(payload.get("input"), dict) else None
    return str(key) if key else f"row-{i}"


def ingest_records(
    conn,
    *,
    records_raw: Any,
    source: str = config.SOURCE,
    collector_id: str,
    contracts: Optional[dict] = None,
    collection_id: Optional[str] = None,
) -> Run:
    """Persist one immutable run from raw collector output. Returns the stored Run.

    Status rules:
      * no input rows at all            -> empty
      * rows present but all errored    -> failed  (writes NO records)
      * otherwise                       -> ok / partial / empty via field contracts
    """
    contracts = config.FIELD_CONTRACTS if contracts is None else contracts
    rows = _as_list(records_raw)
    errored = [r for r in rows if r.get("error")]
    clean = [r for r in rows if not r.get("error")]

    records = {_recall_key(p, i): p for i, p in enumerate(clean)}

    if not rows:
        status = models.RUN_EMPTY
    elif clean:
        status = config.derive_status(records, contracts)
    else:
        status = models.RUN_FAILED  # every input errored at the transport level

    run = Run(
        collector_id=collector_id, source=source, started_at=_now(),
        row_count=len(records) if status != models.RUN_FAILED else None,
        status=status, completed_at=_now(),
        collection_id=collection_id, input_count=len(rows),
        error_code=(errored[0].get("error_code") if status == models.RUN_FAILED else None),
        error_detail=(errored[0].get("error") if status == models.RUN_FAILED else None),
    )
    db.insert_run(conn, run)
    if status != models.RUN_FAILED:
        db.insert_records(conn, run.run_id, [Record(run.run_id, k, v) for k, v in records.items()])
    return run


def ingest_fixture(conn, path: str, *, source: str = config.SOURCE, collector_id: str,
                   contracts: Optional[dict] = None) -> Run:
    with open(path) as f:
        raw = json.load(f)
    return ingest_records(conn, records_raw=raw, source=source, collector_id=collector_id,
                          contracts=contracts)


def scrape_live(collector_id: str, input_file: str, *, version: Optional[str] = None,
                timeout: int = 900) -> Any:
    """Run the collector over an input file via the bdata CLI and return parsed rows.

    Deliberate temporary adapter — see module docstring. `version="dev"` runs the draft
    (used for the controlled-break demo); omit it to run production.
    """
    out = tempfile.mktemp(suffix=".json")
    argv = [
        "bdata", "scraper", "run", collector_id,
        "--input-file", input_file, "--json", "-o", out,
        "--timeout", str(timeout),
    ]
    if version:
        argv += ["--version", version]
    subprocess.run(argv, check=True, timeout=timeout + 100, capture_output=True, text=True)
    with open(out) as f:
        return json.load(f)
