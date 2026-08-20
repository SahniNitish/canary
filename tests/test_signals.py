"""Health-engine math, proven on synthetic abstract records.

These deliberately do NOT use the Health Canada schema — they exercise the detector logic
on generic fields so the engine is verified independent of any collector. The real-fixture
signal tests (each broken fixture derived from fixtures/hc_baseline.json) come after the
baseline exists; see test_signals_realfixtures.py.
"""

import copy

from canary import models, signals
from canary.config import FieldContract

CONTRACTS = {
    "company": FieldContract(required=True),
    "product": FieldContract(required=True),
    "code": FieldContract(required=True, format=r"^RA-\d+$"),
    "category": FieldContract(required=False, enum=True),
    "affected": FieldContract(required=True),
}


def baseline():
    return {
        f"k{i}": {
            "company": f"Co{i}", "product": f"P{i}", "code": f"RA-{1000 + i}",
            "category": "Class 1", "affected": [{"model": f"M{i}"}],
        }
        for i in range(10)
    }


def _detect(base, curr, **kw):
    return signals.detect(
        baseline=base, current=curr, baseline_run_id=1, current_run_id=2,
        contracts=CONTRACTS, **kw,
    )


def _kinds(sigs, field=None):
    return {s.kind for s in sigs if field is None or s.field == field}


def test_baseline_vs_itself_is_silent():
    assert _detect(baseline(), baseline()) == []


def test_null_rate_spike_fires_critical_on_required_field():
    curr = copy.deepcopy(baseline())
    for k in ["k0", "k1", "k2", "k3"]:          # 6/10 populated -> below 0.70 floor
        curr[k]["company"] = ""
    sigs = _detect(baseline(), curr)
    company = [s for s in sigs if s.kind == models.KIND_NULL_RATE and s.field == "company"]
    assert company and company[0].severity == models.SEV_CRITICAL
    assert "10 in baseline" in company[0].detail or "/10" in company[0].detail


def test_null_rate_ignores_legitimately_sparse_field():
    base = baseline()
    for i in range(6):                           # company only 4/10 in baseline
        base[f"k{i}"]["company"] = ""
    curr = copy.deepcopy(base)
    for k in curr:                               # now fully blank, but baseline wasn't watched
        curr[k]["company"] = ""
    assert models.KIND_NULL_RATE not in _kinds(_detect(base, curr), field="company")


def test_cardinality_collapse_fires():
    curr = copy.deepcopy(baseline())
    for k in curr:
        curr[k]["company"] = "SAME"              # 10 distinct -> 1, but still populated
    sigs = _detect(baseline(), curr)
    assert models.KIND_CARDINALITY in _kinds(sigs, field="company")
    assert models.KIND_NULL_RATE not in _kinds(sigs, field="company")  # not a null spike


def test_cardinality_skips_enum_field():
    curr = copy.deepcopy(baseline())
    # category is enum + only 1 distinct in baseline anyway -> never a cardinality signal
    assert models.KIND_CARDINALITY not in _kinds(_detect(baseline(), curr), field="category")


def test_rowcount_delta_volume_anomaly_without_oracle():
    curr = {k: baseline()[k] for k in ["k0", "k1", "k2"]}   # 10 -> 3
    row = [s for s in _detect(baseline(), curr) if s.kind == models.KIND_ROWCOUNT]
    assert row and row[0].severity == models.SEV_WARN
    assert "not verified" in row[0].detail          # never claims a delisting


def test_rowcount_delta_names_missing_ids_with_oracle():
    curr = {k: baseline()[k] for k in ["k0", "k1", "k2"]}
    row = [s for s in _detect(baseline(), curr, expected_ids=list(baseline())) if s.kind == models.KIND_ROWCOUNT]
    assert row and row[0].severity == models.SEV_CRITICAL
    assert "7 expected recalls missing" in row[0].detail and "k3" in row[0].detail


def test_schema_drift_fires_when_key_disappears():
    curr = copy.deepcopy(baseline())
    for k in curr:
        del curr[k]["code"]                      # key gone entirely
    assert models.KIND_SCHEMA_DRIFT in _kinds(_detect(baseline(), curr), field="code")


def test_format_violation_fires_when_values_stop_parsing():
    curr = copy.deepcopy(baseline())
    for k in curr:
        curr[k]["code"] = "12345"                # populated + distinct, but no RA- prefix
    sigs = _detect(baseline(), curr)
    assert models.KIND_FORMAT in _kinds(sigs, field="code")
    assert models.KIND_NULL_RATE not in _kinds(sigs, field="code")


def test_derive_status_from_contracts():
    from canary import config
    assert config.derive_status({}, CONTRACTS) == models.RUN_EMPTY
    ok = baseline()
    assert config.derive_status(ok, CONTRACTS) == models.RUN_OK
    partial = copy.deepcopy(ok)
    partial["k0"]["company"] = ""
    assert config.derive_status(partial, CONTRACTS) == models.RUN_PARTIAL
