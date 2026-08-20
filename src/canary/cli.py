"""Canary operator CLI: init-db, ingest (the whole pipeline), signals, heal, approve.

`ingest` is the demo command: it stores a run, compares it to the last *verified* run,
prints the fired signals, and persists a specific heal prompt for each. `heal`/`approve`
drive Bright Data's `bdata scraper heal|approve` — the human-in-the-loop gate stays the
operator's; `--auto-approve` is never used.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import subprocess
import sys

from . import config, db, heal, models, runner, signals


def _db_path(args) -> str:
    return args.db or os.environ.get("CANARY_DB", "data/canary.db")


def _open(args):
    return db.init_db(_db_path(args))


def _example_failing_url(current_records: dict, field: str) -> str | None:
    for key, payload in current_records.items():
        if signals.is_blank(payload.get(field)):
            return key
    return None


# --------------------------------------------------------------------------- commands

def cmd_init_db(args) -> int:
    path = _db_path(args)
    db.init_db(path).close()
    print(f"initialized {path}")
    return 0


def cmd_ingest(args) -> int:
    conn = _open(args)
    source, collector = args.source, args.collector

    if args.live:
        raw = runner.scrape_live(collector, args.path, version=args.version, timeout=args.timeout)
    else:
        import json
        with open(args.path) as f:
            raw = json.load(f)

    run = runner.ingest_records(conn, records_raw=raw, source=source, collector_id=collector)
    print(f"run #{run.run_id}  status={run.status.upper()}  rows={run.row_count}  inputs={run.input_count}")

    baseline = db.get_last_known_good(conn, source, before_run_id=run.run_id)
    if run.status == models.RUN_FAILED:
        print(f"  transport failure ({run.error_code}): {run.error_detail}")
        print("  no records written; prior run left intact.")
        return 0
    if baseline is None:
        print("  no prior verified run to compare against — recorded as the baseline.")
        return 0

    current_records = db.get_records(conn, run.run_id)
    baseline_records = db.get_records(conn, baseline.run_id)
    found = signals.detect(
        baseline=baseline_records, current=current_records,
        baseline_run_id=baseline.run_id, current_run_id=run.run_id,
    )
    if not found:
        print(f"  ✓ no signals vs verified run #{baseline.run_id}")
        return 0

    print(f"  {len(found)} signal(s) vs verified run #{baseline.run_id}:")
    for s in found:
        example = _example_failing_url(current_records, s.field) if s.field else None
        s.heal_prompt = heal.prompt_for(
            s, example_url=example, expected_shape=config.EXPECTED_SHAPES.get(s.field),
        )
        db.insert_signal(conn, s)
        tag = {"critical": "✗", "warn": "!", "info": "·"}.get(s.severity, "·")
        print(f"    [{tag}] {s.severity.upper():8} {s.kind}/{s.field or '-'}: {s.detail}")
        print(f"           → canary heal {s.signal_id}")
    return 0


def cmd_signals(args) -> int:
    conn = _open(args)
    latest = db.get_latest_run(conn, args.source)
    if latest is None:
        print("no runs yet")
        return 0
    rows = conn.execute(
        "SELECT signal_id, run_id, kind, field, severity, detail, baseline_run_id, resolution "
        "FROM signals WHERE resolution = 'pending' ORDER BY signal_id"
    ).fetchall()
    if not rows:
        print("no pending signals")
        return 0
    for r in rows:
        print(f"#{r['signal_id']} run{r['run_id']}<-base{r['baseline_run_id']} "
              f"{r['severity'].upper()} {r['kind']}/{r['field'] or '-'}: {r['detail']}")
    return 0


def _heal_out_path(args, signal_id: int) -> str:
    parent = os.path.dirname(os.path.abspath(_db_path(args))) or "."
    return os.path.join(parent, f"heal_signal_{signal_id}.json")


def cmd_heal(args) -> int:
    conn = _open(args)
    row = conn.execute("SELECT * FROM signals WHERE signal_id = ?", (args.signal_id,)).fetchone()
    if row is None:
        print(f"no signal #{args.signal_id}")
        return 1
    prompt = row["heal_prompt"] or "(no prompt generated)"
    print(f"signal #{args.signal_id} {row['kind']}/{row['field']}\nheal prompt ({len(prompt)} chars):\n{prompt}")
    if not args.apply:
        print("\n(dry run — pass --apply to send to `bdata scraper heal`)")
        return 0

    attempt = models.HealAttempt(
        signal_id=args.signal_id, created_at=datetime.datetime.now().isoformat(timespec="seconds"),
        prompt=prompt, status="submitted",
    )
    db.insert_heal_attempt(conn, attempt)
    out_path = _heal_out_path(args, args.signal_id)
    argv = [
        "bdata", "scraper", "heal", args.collector, prompt,
        "--timeout", str(args.timeout), "--json", "-o", out_path,
    ]
    if args.url:
        argv += ["--url", args.url]
    print(f"\n$ bdata scraper heal {args.collector} <prompt> --timeout {args.timeout}")
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=args.timeout + 100)
    (sys.stdout if proc.returncode == 0 else sys.stderr).write(proc.stdout or proc.stderr)

    preview = None
    validation = None
    view_url = None
    if os.path.exists(out_path):
        preview = open(out_path).read()
        try:
            envelope = json.loads(preview)
            view_url = envelope.get("view_url")
            if isinstance(envelope.get("next_step"), str):
                view_url = view_url or envelope.get("next_step")
            validation = heal.summarize_preview(envelope, field=row["field"])
            print(f"preview: {validation}")
        except (json.JSONDecodeError, TypeError, AttributeError):
            validation = "preview JSON unreadable"

    db.decide_heal_attempt(
        conn, attempt.attempt_id,
        status="awaiting_approval" if proc.returncode == 0 else "error",
        decided_at=datetime.datetime.now().isoformat(timespec="seconds"),
        preview_payload=preview, validation_result=validation, view_url=view_url,
    )
    return proc.returncode


def cmd_approve(args) -> int:
    conn = _open(args)
    argv = ["bdata", "scraper", "approve", args.collector, "--json"]
    if args.reject:
        argv.append("--reject")
    if args.auto_save:
        argv.append("--auto-save")
    if args.url:
        argv += ["--url", args.url]
    print(f"$ {' '.join(argv[:4])}{' --reject' if args.reject else ''}{' --auto-save' if args.auto_save else ''}")
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=args.timeout + 100)
    (sys.stdout if proc.returncode == 0 else sys.stderr).write(proc.stdout or proc.stderr)
    now = datetime.datetime.now().isoformat(timespec="seconds")
    latest = conn.execute(
        "SELECT attempt_id FROM heal_attempts ORDER BY attempt_id DESC LIMIT 1"
    ).fetchone()
    if latest:
        db.decide_heal_attempt(
            conn, latest["attempt_id"],
            status="rejected" if args.reject else ("approved" if proc.returncode == 0 else "error"),
            decided_at=now,
            decision_reason="operator --reject" if args.reject else "operator approve",
        )
    if proc.returncode == 0 and not args.reject:
        conn.execute(
            "UPDATE signals SET resolution = ? WHERE resolution = ?",
            (models.RES_APPROVED, models.RES_PENDING),
        )
        conn.commit()
    elif proc.returncode == 0 and args.reject:
        conn.execute(
            "UPDATE signals SET resolution = ? WHERE resolution = ?",
            (models.RES_REJECTED, models.RES_PENDING),
        )
        conn.commit()
    return proc.returncode


def cmd_status(args) -> int:
    """Operator envelope: never describe stale data as safe."""
    conn = _open(args)
    latest = db.get_latest_run(conn, args.source)
    if latest is None:
        print("data_status=empty")
        print("verified_as_of=-")
        print("latest_run_status=-")
        print("age_seconds=-")
        return 0
    verified = db.get_last_known_good(conn, args.source)
    if latest.status == models.RUN_OK:
        data_status = "current"
        served = latest
    elif verified is not None:
        data_status = "degraded"
        served = verified
    else:
        data_status = latest.status
        served = latest
    stamp = served.completed_at or served.started_at
    try:
        age = int((datetime.datetime.now() - datetime.datetime.fromisoformat(stamp)).total_seconds())
    except (TypeError, ValueError):
        age = None
    pending = conn.execute(
        "SELECT COUNT(*) AS n FROM signals WHERE resolution = 'pending'"
    ).fetchone()["n"]
    print(f"data_status={data_status}")
    print(f"verified_as_of={stamp}")
    print(f"latest_run_status={latest.status}")
    print(f"age_seconds={age if age is not None else '-'}")
    print(f"verified_run_id={verified.run_id if verified else '-'}")
    print(f"latest_run_id={latest.run_id}")
    print(f"pending_signals={pending}")
    if data_status == "degraded":
        print("NOTE: serving last verified snapshot; latest run is not safe to promote.")
    return 0


def cmd_history(args) -> int:
    conn = _open(args)
    rows = conn.execute(
        "SELECT run_id, started_at, status, row_count, input_count FROM runs "
        "WHERE source = ? ORDER BY run_id", (args.source,)
    ).fetchall()
    for r in rows:
        print(f"#{r['run_id']:>3} {r['started_at']} {r['status'].upper():8} "
              f"rows={r['row_count']} inputs={r['input_count']}")
    return 0


# --------------------------------------------------------------------------- parser

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="canary", description="Supervise a recall scraper.")
    p.add_argument("--db", help="SQLite path (default: $CANARY_DB or data/canary.db)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init-db").set_defaults(func=cmd_init_db)

    ing = sub.add_parser("ingest", help="ingest a run (fixture or --live) and detect signals")
    ing.add_argument("path", help="fixture JSON, or --input-file when --live")
    ing.add_argument("--source", default=config.SOURCE)
    ing.add_argument("--collector", default=config.COLLECTOR_ID)
    ing.add_argument("--live", action="store_true", help="scrape via bdata instead of reading a fixture")
    ing.add_argument("--version", help="collector version, e.g. dev (for the controlled-break run)")
    ing.add_argument("--timeout", type=int, default=900)
    ing.set_defaults(func=cmd_ingest)

    sig = sub.add_parser("signals", help="list pending signals")
    sig.add_argument("--source", default=config.SOURCE)
    sig.set_defaults(func=cmd_signals)

    h = sub.add_parser("heal", help="show (or --apply) the heal prompt for a signal")
    h.add_argument("signal_id", type=int)
    h.add_argument("--apply", action="store_true")
    h.add_argument("--collector", default=config.COLLECTOR_ID)
    h.add_argument("--url", help="verify URL woven into the next-step hint")
    h.add_argument("--timeout", type=int, default=1200)
    h.set_defaults(func=cmd_heal)

    ap = sub.add_parser("approve", help="approve or --reject a heal awaiting approval")
    ap.add_argument("--collector", default=config.COLLECTOR_ID)
    ap.add_argument("--reject", action="store_true")
    ap.add_argument("--auto-save", action="store_true",
                    help="publish the approved template after the operator inspects the preview")
    ap.add_argument("--url")
    ap.add_argument("--timeout", type=int, default=600)
    ap.set_defaults(func=cmd_approve)

    hi = sub.add_parser("history", help="list stored runs")
    hi.add_argument("--source", default=config.SOURCE)
    hi.set_defaults(func=cmd_history)

    st = sub.add_parser("status", help="operator envelope: current vs last verified snapshot")
    st.add_argument("--source", default=config.SOURCE)
    st.set_defaults(func=cmd_status)

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
