# DECISIONS.md — why Canary is built the way it is

This file exists so every non-obvious choice can be explained out loud (rules 11/12).
"The agent wrote it" is a losing Q&A answer. If a decision here stops being true, fix it here.

---

## What Canary is (and is not)

Canary is **not** a recall aggregator. It is a supervision layer that watches a live Bright Data
Scraper Studio collector on **IKEA US product recall notices** and **proves it is still telling the
truth**. A broken scraper does not crash — it returns 200, exits 0, and silently drops a field.
Three weeks later someone searches recalls by article number, gets nothing, and a tip-over-prone
KULLEN dresser stays in a child's room. Everything here exists to catch that failure mode.

**The product is the closed loop**, not the detectors:
> silent-failure evidence → precise heal prompt → Scraper Studio preview → validate → approve/reject
> → **same `c_*` Collector ID** → verified recovery.

The five signals (null-rate, cardinality, row-count, schema-drift, format) are the **sensors**.
They are standard data-quality checks; they are not the innovation and are not sold as such.

---

## Load-bearing structural decisions

**Runs are immutable snapshots. Never upsert.**
Detection compares a run against the last *verified* run. Upserting destroys the baseline and makes
the core feature impossible. This is the single most load-bearing choice in the repo.

**Baseline = last known-good run, not run N−1.**
If run N is broken and N+1 is also broken, comparing to N−1 would let the broken run become the new
normal and the alert would go silent — the exact failure Canary exists to catch, implemented
backwards. Each signal records the `baseline_run_id` it compared against.

**Store the scraped payload raw as JSON; do not normalize into typed columns.**
A rigid column schema silently drops fields the site adds — the exact class of blind failure we
detect. Introducing our own version of the bug is indefensible in Q&A.

**Field contracts are written from real collector output, never guessed.**
Hardcoding field names or regexes before the collector exists reintroduces the blind-schema bug and
risks a format alert firing on a healthy baseline. Contracts come from the keys the collector
actually returns; empty nested values (`[]`/`{}`/`""`) count as null.

**`ok | empty | partial | failed` are distinct.**
An absent run and a failed run must be distinguishable, or the dashboard cannot tell "nothing broke"
from "everything broke". `empty` = HTTP 200 with `[]`; `failed` = timeout/4xx and writes **no**
records, leaving the prior run intact. `partial` = a required field fell below its contract.

**Stale data is never labeled safe.** Degraded reads carry `data_status`, `verified_as_of`,
`latest_run_status`, `age_seconds`. The suspect snapshot is quarantined, not promoted.

---

## Scraper Studio integration

**CLI mode, driven from the coding agent.** The three build modes produce the same collector; CLI is
chosen because the supervision layer must create, run, and heal programmatically (criterion 4).

**Collector ID (`c_*`) is treated as a stable production API endpoint**, pinned in CLAUDE.md so the
agent never creates a second collector and splits the story.

**Batched PDP collector, not Discovery→PDP.** The monitored cohort is a fixed list of 6 IKEA recall
notice URLs, run through one PDP collector. Discovery (crawling the recalls index) is a separate,
riskier capability and is out of scope this week. Honest type in the writeup.

**Why IKEA and not a government recall registry.** Health Canada / CPSC / FDA are the obvious recall
sources, but Bright Data's proxy network policy **blocks government domains** (verified: production
runs 403 with a government-classification block). IKEA recall notices are commercial, public, and
proxyable, they are a long-tail page family (catalog/price scrapers may exist; recall notices under
`/customer-service/product-support/recalls/` do not), and — crucially — they are HTML with **no
official JSON dump**, so Scraper Studio is doing real extraction work.

**Heals are human-in-the-loop by default.** `--auto-approve` is never used. Detection is our job;
approval is the operator's. The `--reject` path (bad preview → sharper prompt → retry) is surfaced
as a first-class flow and recorded in `heal_attempts` — most submissions will only demo approve.

**The CLI runner is a deliberate temporary adapter.** `POST /dca/trigger` returns a `j_*` collection
id that must be polled, not rows; the `bdata` CLI polls for us. Invoked via
`subprocess.run([...], shell=False, timeout=...)` — never a shell string with interpolated URLs or
prompts. A stdlib `urllib` direct-API path is a P1/stretch, only if it earns its keep.

---

## Why scrape at all?

IKEA publishes its recall notices only as **HTML pages — there is no official JSON API or bulk
dump**. So Scraper Studio is doing genuine extraction the operator cannot get any other way; there
is no "just use the feed" objection to answer. The trade-off is that Canary has **no membership
oracle**: without an authoritative list of expected recalls, a row-count drop is reported only as a
**volume anomaly** — we never claim "a recall was omitted" without evidence. If we later scrape the
recalls *index* page, that index becomes the membership oracle and row-count can name exact missing
notices; until then, honesty over the stronger-sounding claim.

---

## AI disclosure (rule 10)

Architecture and code were developed with AI assistance (Claude Code), and the plan was
stress-tested against two independent AI reviews (Grok, Codex) whose corrections are folded into the
build. Every file is human-reviewed and explainable; anything that cannot be explained is deleted.

## Out of scope this week (CLAUDE.md §10)
Cross-source entity matching, user accounts/auth, email/SMS delivery, ML anomaly detection,
additional sources (CPSC/FDA), deployment infra, a generalized "any website" framework.
