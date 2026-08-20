"""The health engine: five pure signal detectors + a `detect` orchestrator.

Zero network calls. Everything here takes two runs' worth of records (baseline and
current, as {recall_key: payload} dicts) plus contracts, and emits `Signal`s. That makes
it fast to iterate offline, fully unit-testable, and cheap on Bright Data credits.

The five signals are *sensors*, not the product. The product is the closed loop that a
fired signal starts: evidence -> heal prompt -> preview -> approve/reject -> recovery.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Iterable, NamedTuple, Optional

from . import config as _config
from . import models
from .models import Signal

Records = dict[str, dict[str, Any]]


# ------------------------------------------------------------------- value helpers

def is_blank(value: Any) -> bool:
    """None, empty string/whitespace, and empty list/dict all count as missing.

    Empty nested containers matter: an `affected_products: []` is a silent drop just as
    much as a null company, and a typed-column schema would have hidden it.
    """
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, (list, dict, tuple, set)):
        return len(value) == 0
    return False


def _field_universe(records: Records) -> set[str]:
    keys: set[str] = set()
    for payload in records.values():
        keys.update(payload.keys())
    return keys


def _populated(records: Records, field: str) -> tuple[int, int]:
    """(#records where field is non-blank, #records)."""
    total = len(records)
    count = sum(1 for p in records.values() if not is_blank(p.get(field)))
    return count, total


def _presence(records: Records, field: str) -> float:
    """Fraction of records where the *key* is present (regardless of blankness)."""
    if not records:
        return 0.0
    return sum(1 for p in records.values() if field in p) / len(records)


def _scalar_values(records: Records, field: str) -> list[Any]:
    """Non-blank scalar values only (cardinality on a list field is meaningless)."""
    out = []
    for p in records.values():
        v = p.get(field)
        if not is_blank(v) and isinstance(v, (str, int, float, bool)):
            out.append(v)
    return out


# ------------------------------------------------------------------- format parsers

def _iso_date(v: Any) -> bool:
    return isinstance(v, str) and bool(re.match(r"^\d{4}-\d{2}-\d{2}$", v.strip()))


PARSERS: dict[str, Callable[[Any], bool]] = {"iso_date": _iso_date}


def _validator(contract) -> Optional[Callable[[Any], bool]]:
    checks: list[Callable[[Any], bool]] = []
    if contract.format:
        pat = re.compile(contract.format)
        checks.append(lambda v: isinstance(v, str) and bool(pat.search(v)))
    if contract.parser and contract.parser in PARSERS:
        checks.append(PARSERS[contract.parser])
    if not checks:
        return None
    return lambda v: all(c(v) for c in checks)


# ------------------------------------------------------------------- findings

class Finding(NamedTuple):
    kind: str
    field: Optional[str]
    severity: str
    detail: str


def _sev(field: Optional[str], contracts: dict, base: str = models.SEV_WARN) -> str:
    c = contracts.get(field) if field else None
    return models.SEV_CRITICAL if (c and c.required) else base


# ------------------------------------------------------------------- the five signals

def null_rate_spike(baseline: Records, current: Records, contracts: dict, cfg=_config) -> list[Finding]:
    findings = []
    for field in sorted(_field_universe(baseline)):
        b_count, b_total = _populated(baseline, field)
        if b_total == 0 or b_count / b_total < cfg.NULL_RATE_BASELINE_MIN:
            continue  # not watched: wasn't reliably populated in the baseline
        c_count, c_total = _populated(current, field)
        if c_total == 0:
            continue
        if c_count / c_total < cfg.NULL_RATE_FLOOR:
            findings.append(Finding(
                models.KIND_NULL_RATE, field, _sev(field, contracts, models.SEV_CRITICAL),
                f"{field} populated {b_count}/{b_total} in baseline, {c_count}/{c_total} now",
            ))
    return findings


def cardinality_collapse(baseline: Records, current: Records, contracts: dict, cfg=_config) -> list[Finding]:
    findings = []
    for field in sorted(_field_universe(baseline)):
        c = contracts.get(field)
        if c and c.enum:
            continue  # legitimately low-diversity field
        b_distinct = len(set(_scalar_values(baseline, field)))
        if b_distinct < cfg.CARDINALITY_MIN_BASELINE:
            continue
        # If the field is now mostly blank, that's a null spike, not a diversity collapse —
        # let null_rate own it instead of double-firing.
        c_count, c_total = _populated(current, field)
        if c_total == 0 or c_count / c_total < cfg.NULL_RATE_FLOOR:
            continue
        n_distinct = len(set(_scalar_values(current, field)))
        if n_distinct <= b_distinct * cfg.CARDINALITY_DROP_RATIO:
            findings.append(Finding(
                models.KIND_CARDINALITY, field, _sev(field, contracts),
                f"{field} distinct values {b_distinct} -> {n_distinct}",
            ))
    return findings


def rowcount_delta(
    baseline: Records, current: Records, contracts: dict, cfg=_config,
    expected_ids: Optional[Iterable[str]] = None,
) -> list[Finding]:
    b_n, c_n = len(baseline), len(current)
    if b_n == 0 or c_n >= b_n * cfg.ROWCOUNT_DROP_RATIO:
        return []
    if expected_ids is not None:
        # Membership oracle present -> we can name exactly what's missing and mean it.
        missing = [k for k in expected_ids if k not in current]
        shown = ", ".join(map(str, missing[:5])) + ("…" if len(missing) > 5 else "")
        return [Finding(
            models.KIND_ROWCOUNT, None, models.SEV_CRITICAL,
            f"row count {b_n} -> {c_n}; {len(missing)} expected recalls missing from scrape: {shown}",
        )]
    # No oracle -> report a volume anomaly ONLY. Do not claim "no delisting".
    return [Finding(
        models.KIND_ROWCOUNT, None, models.SEV_WARN,
        f"row count {b_n} -> {c_n} (volume anomaly; source membership not verified)",
    )]


def schema_drift(baseline: Records, current: Records, contracts: dict, cfg=_config) -> list[Finding]:
    findings = []
    current_keys = _field_universe(current)
    for field in sorted(_field_universe(baseline)):
        if _presence(baseline, field) >= cfg.SCHEMA_DRIFT_PRESENCE and field not in current_keys:
            findings.append(Finding(
                models.KIND_SCHEMA_DRIFT, field, _sev(field, contracts, models.SEV_CRITICAL),
                f"key '{field}' present in {_presence(baseline, field):.0%} of baseline, absent entirely now",
            ))
    return findings


def format_violation(baseline: Records, current: Records, contracts: dict, cfg=_config) -> list[Finding]:
    findings = []
    for field, contract in contracts.items():
        validate = _validator(contract)
        if validate is None:
            continue
        b_vals = [v for v in (p.get(field) for p in baseline.values()) if not is_blank(v)]
        if not b_vals or sum(validate(v) for v in b_vals) / len(b_vals) < 0.90:
            continue  # field wasn't reliably formatted in the baseline; don't judge it
        c_vals = [v for v in (p.get(field) for p in current.values()) if not is_blank(v)]
        if not c_vals:
            continue
        fail = sum(0 if validate(v) else 1 for v in c_vals)
        if fail / len(c_vals) > cfg.FORMAT_FAIL_RATIO:
            findings.append(Finding(
                models.KIND_FORMAT, field, _sev(field, contracts),
                f"{field}: {fail}/{len(c_vals)} values stopped matching expected format",
            ))
    return findings


# ------------------------------------------------------------------- orchestrator

def detect(
    *,
    baseline: Records,
    current: Records,
    baseline_run_id: Optional[int],
    current_run_id: int,
    contracts: Optional[dict] = None,
    cfg=_config,
    expected_ids: Optional[Iterable[str]] = None,
) -> list[Signal]:
    """Run every signal comparing `current` against its `baseline` (last verified run).

    Returns fully-formed `Signal`s ready to persist. `baseline_run_id` is recorded on
    each so the audit trail shows exactly which run was the yardstick.
    """
    contracts = _config.FIELD_CONTRACTS if contracts is None else contracts
    findings: list[Finding] = []
    findings += null_rate_spike(baseline, current, contracts, cfg)
    findings += cardinality_collapse(baseline, current, contracts, cfg)
    findings += rowcount_delta(baseline, current, contracts, cfg, expected_ids)
    findings += schema_drift(baseline, current, contracts, cfg)
    findings += format_violation(baseline, current, contracts, cfg)

    return [
        Signal(
            run_id=current_run_id, kind=f.kind, field=f.field, severity=f.severity,
            detail=f.detail, baseline_run_id=baseline_run_id,
        )
        for f in findings
    ]
