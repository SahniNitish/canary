"""Domain types for Canary.

These are deliberately thin: `runs` and `records` are *immutable snapshots* of what a
collector returned, stored so that run N can be compared against the last verified run.
Nothing here normalizes the scraped payload into typed columns — doing so would silently
drop fields the site adds, which is the exact blind failure Canary exists to detect.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

# --- Run status domain (CLAUDE.md §5). An absent run must differ from a failed run. ---
RUN_OK = "ok"          # collector returned a healthy row set
RUN_EMPTY = "empty"    # HTTP 200 with []  -> raise a signal, serve last-known-good
RUN_PARTIAL = "partial"  # rows present, but a required field fell below its contract
RUN_FAILED = "failed"  # timeout / 4xx -> write NO records, leave the prior run intact
RUN_STATUSES = (RUN_OK, RUN_EMPTY, RUN_PARTIAL, RUN_FAILED)

# --- Signal severity ---
SEV_INFO = "info"
SEV_WARN = "warn"
SEV_CRITICAL = "critical"
SEVERITIES = (SEV_INFO, SEV_WARN, SEV_CRITICAL)

# --- Signal kinds: the five sensors (they are sensors, not the product) ---
KIND_NULL_RATE = "null_rate"
KIND_CARDINALITY = "cardinality"
KIND_ROWCOUNT = "rowcount"
KIND_SCHEMA_DRIFT = "schema_drift"
KIND_FORMAT = "format"

# --- Signal resolution (the human-in-the-loop gate) ---
RES_PENDING = "pending"
RES_APPROVED = "approved"
RES_REJECTED = "rejected"
RES_IGNORED = "ignored"
RESOLUTIONS = (RES_PENDING, RES_APPROVED, RES_REJECTED, RES_IGNORED)


@dataclass
class Run:
    """One immutable execution of a collector."""

    collector_id: str
    source: str
    started_at: str
    row_count: Optional[int]
    status: str
    run_id: Optional[int] = None
    # Lifecycle columns the three-table schema alone cannot explain (e.g. a hung job).
    collection_id: Optional[str] = None  # j_* returned by /dca/trigger
    completed_at: Optional[str] = None
    input_count: Optional[int] = None
    error_code: Optional[str] = None
    error_detail: Optional[str] = None


@dataclass
class Record:
    """One recall inside a run, stored with its payload raw and unmodified."""

    run_id: int
    recall_key: str  # stable identity: recall/notice number or URL
    payload: dict[str, Any]


@dataclass
class Signal:
    """A detected anomaly comparing a run against its baseline (last verified run)."""

    run_id: int
    kind: str
    severity: str
    detail: str  # human-readable; feeds the heal prompt
    field: Optional[str] = None
    baseline_run_id: Optional[int] = None  # which run this was compared against
    heal_prompt: Optional[str] = None
    resolution: str = RES_PENDING
    signal_id: Optional[int] = None


@dataclass
class HealAttempt:
    """One turn of the heal loop; multiple rows preserve the reject -> retry history."""

    signal_id: int
    created_at: str
    prompt: str
    status: str
    preview_payload: Optional[str] = None
    validation_result: Optional[str] = None
    view_url: Optional[str] = None
    decided_at: Optional[str] = None
    decision_reason: Optional[str] = None
    attempt_id: Optional[int] = None
