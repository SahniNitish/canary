"""Thresholds and field contracts — the one place tuning lives (CLAUDE.md §6).

Two kinds of knobs live here:

1. **Thresholds** — schema-independent constants the five signals use. Tunable, commented.
2. **Field contracts** — which fields are required, and their expected format/parser.
   These are written from the *real* collector output (see `FIELD_CONTRACTS`), never
   guessed ahead of the first scrape. Guessing them reintroduces the exact blind-schema
   bug Canary exists to detect, and a wrong regex would false-fire on a healthy baseline.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from . import models

# --------------------------------------------------------------------- thresholds

# Null-rate spike: a field watched only if it was near-fully populated in the baseline,
# and it fires when the current run drops below the floor.
NULL_RATE_BASELINE_MIN = 0.90  # field must be >=90% populated in the baseline to be watched
NULL_RATE_FLOOR = 0.70         # ...and fires if it falls below 70% populated now

# Cardinality collapse: distinct values crater (e.g. 30 companies -> 2).
CARDINALITY_DROP_RATIO = 0.5   # fire if distinct_now <= distinct_baseline * this
CARDINALITY_MIN_BASELINE = 5   # ...but ignore low-diversity fields to avoid pager noise

# Row-count delta: rows vanish. Without the membership oracle this is only a *volume*
# anomaly — we never claim "no delisting on the source" without evidence.
ROWCOUNT_DROP_RATIO = 0.5      # fire if row_count_now < row_count_baseline * this

# Schema drift: a key present in most of the baseline is absent entirely now.
SCHEMA_DRIFT_PRESENCE = 0.90   # key present in >=90% of baseline records...
# (...and absent from *every* current record -> fire)

# Format violation: values that used to parse stop parsing.
FORMAT_FAIL_RATIO = 0.5        # fire if >50% of currently-populated values fail the format


# --------------------------------------------------------------------- contracts

@dataclass(frozen=True)
class FieldContract:
    """What a field is expected to be. `format` is a regex string; `parser` names a
    built-in check (see canary.signals.PARSERS). `enum` marks legitimately low-diversity
    fields so cardinality-collapse skips them."""

    required: bool = False
    format: Optional[str] = None
    parser: Optional[str] = None
    enum: bool = False


# Logical source + the payload key that stably identifies a recall (its recall_key).
SOURCE = "ikea"
RECALL_KEY_FIELD = "source_url"

# Pinned collector (mirror of CLAUDE.md). Not a secret; overridable via --collector / env.
COLLECTOR_ID = "c_mt07a4h921tnzr8kvt"

# Human-readable "what this field should be", woven into heal prompts. Optional per field.
EXPECTED_SHAPES: dict[str, str] = {
    "hazard": "a non-empty text description of why the product is dangerous",
    "remedy": "a non-empty text description of what the customer should do",
    "article_numbers": "a non-empty list of IKEA article-number strings like 501.637.54",
    "source_url": "the canonical IKEA recall-notice URL",
}

# Written from the REAL collector output (fixtures/ikea_baseline.json), not guessed.
# Only the fields the collector extracts reliably across the whole cohort (6/6) are part
# of the health contract; the rest are inconsistently formatted page-to-page and are
# tracked as optional so a healthy baseline reads as `ok`, not a false `partial`.
#   reliable 6/6 : source_url, hazard, remedy
#   flaky        : title 4/6, product_name 4/6, contact_phone 2/6,
#                  article_numbers 1/6, sold_period 1/6, retail_price 1/6
FIELD_CONTRACTS: dict[str, FieldContract] = {
    "source_url": FieldContract(required=True),   # identity / recall_key
    "hazard": FieldContract(required=True),        # why the product is dangerous
    "remedy": FieldContract(required=True),        # what the customer must do
    "title": FieldContract(required=False),
    "product_name": FieldContract(required=False),
    "article_numbers": FieldContract(required=False),
    "sold_period": FieldContract(required=False),
    "retail_price": FieldContract(required=False),
    "contact_phone": FieldContract(required=False),
}


def critical_fields(contracts: dict[str, FieldContract]) -> list[str]:
    """Fields whose absence/blankness makes a run `partial`."""
    return [name for name, c in contracts.items() if c.required]


def derive_status(records: dict, contracts: dict[str, FieldContract]) -> str:
    """Classify a completed run from its records + contracts.

    empty   -> no records at all (HTTP 200 with [])
    partial -> some required field is blank on at least one record
    ok      -> every required field populated on every record
    (`failed` is set by the runner on transport error, never here.)
    """
    from .signals import is_blank  # local import avoids a cycle

    if not records:
        return models.RUN_EMPTY
    required = critical_fields(contracts)
    for payload in records.values():
        for fname in required:
            if is_blank(payload.get(fname)):
                return models.RUN_PARTIAL
    return models.RUN_OK
