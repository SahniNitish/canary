# CLAUDE.md — Canary

Context file for Claude Code. Read this before doing anything in this repo.

> **Pinned Scraper Studio collector — do NOT create a second one.**
> `SCRAPER_STUDIO_COLLECTOR_ID=c_mt07a4h921tnzr8kvt` (name `canary-ikea-recalls`, batched PDP,
> IKEA US product recall notices). Dashboard: https://brightdata.com/cp/scrapers/c_mt07a4h921tnzr8kvt
> Monitored cohort: `fixtures/ikea_recall_urls.json` (6 URLs). Output schema (from real run):
> `article_numbers` (list), `hazard`, `remedy`, `source_url`.
> NOTE: government recall registries (Health Canada / CPSC / FDA) are blocked by Bright Data's proxy
> AUP as "Government"; IKEA is commercial + proxyable. `c_mt06i9om1im1onnuac` (Health Canada) is dead.

---

## 1. What this project is

**Canary** — a supervision layer for Bright Data Scraper Studio collectors, applied to
product recall and safety-bulletin monitoring.

**One-sentence pitch:** Recall data goes stale silently — the scraper still returns 200,
the dashboard still loads, and nobody notices a field stopped extracting until someone
ships a recalled product.

**Critical framing:** this is NOT a recall aggregator. It is the thing that watches a
recall scraper and proves it is still telling the truth. If a change makes the project
feel more like an aggregator and less like a supervisor, that change is wrong.

### The thesis

A broken scraper does not crash. It lies.

Concrete case: Health Canada renames a CSS class. The scraper runs at 3am, returns 50
rows, exits 0. The `manufacturer` field is now blank on all 50. No error, no alert, no
red X. Three weeks later someone searches recalls by manufacturer, gets zero results,
and concludes there are none. There were eleven.

Everything in this repo exists to catch that failure mode.

---

## 2. Hard constraints — do not violate

- **Deadline:** submission Sun Aug 23, 2026. Buffer required; do not plan to finish at the wire.
- **Solo developer.** Scope accordingly. Prefer one thing that works over three that half-work.
- **Public data only.** No login-walled, paywalled, or personal data. Non-negotiable eligibility rule.
- **Never commit tokens or `.env`.** They must also not be visible in the demo video. Scrub before recording.
- **Bright Data Scraper Studio is mandatory.** If the project would still work with `requests` +
  BeautifulSoup, the submission has already failed criterion 4.
- **Credits are finite** (~5,000/month free tier + $53 promo). Build against saved fixtures, not live runs.
- **Every technical decision must be defensible out loud.** AI tooling is explicitly allowed, but
  "the agent wrote it" is a losing answer in Q&A. If you generate something non-obvious, explain
  the reasoning in a comment or leave a note in `DECISIONS.md`.

### Judging criteria (six, equally weighted)

1. Potential impact — clear, useful problem
2. Creativity and innovation — original angle on web-data collection
3. Technical excellence — complete, reliable, well structured
4. Use of Scraper Studio — central, not bolted on
5. Reliability and self-healing — survives site changes, missing data, extraction failures
6. Presentation — demo explains problem → scraper workflow → structured output → product

Criteria 4 and 5 are one third of the score and they are the same feature here. Any work that
does not map to a numbered criterion above should be flagged, not silently done.

---

## 3. Data source

- **Primary:** Health Canada Recalls & Safety Alerts (public, no pre-built Bright Data scraper exists)
- **Stretch only:** US CPSC, FDA enforcement reports (cosmetics/OTC)

Do not add sources unless the primary is fully working and the heal footage is recorded.
Second and third sources add breadth; the score comes from depth on criterion 5.

**Scraper type:** Discovery (listing/index pages) → PDP (individual recall detail pages).

Target choice is deliberate: Bright Data ships 800+ pre-built scrapers and judges penalize
targets that already have one. Government recall registries are long-tail. Say so in the writeup.

---

## 4. Architecture

```
Scraper Studio collector (built + healed via CLI)
        │  POST /dca/trigger
        ▼
  Runner  ──────────────►  SQLite (immutable run snapshots)
                                  │
                                  ▼
                          Health engine (5 signals)
                                  │  signal fires
                                  ▼
                       Heal-prompt generator
                                  │
                                  ▼
                   Human approval gate (approve / --reject)
                                  │
                                  ▼
                    bdata scraper heal <collector_id>
```

Dashboard/UI reads from SQLite. It never triggers the collector directly.

### Decision log — the reasoning, not just the rule

**Runs are immutable snapshots. Never upsert.**
Temporal reconciliation compares run N against run N−1. Upserting destroys the baseline, which
makes the core feature impossible. This is the load-bearing structural choice in the repo.

**Store the scraped payload raw as JSON; do not normalize into typed columns yet.**
A rigid column schema silently drops fields the site adds — the exact class of blind failure
this project exists to detect. Introducing our own version of the bug we are detecting is
indefensible in Q&A.

**CLI mode, driven from the coding agent — not the dashboard.**
All three Scraper Studio build modes (AI Agent, JS IDE, CLI) produce the same underlying
collector and are interchangeable. CLI is chosen because the supervision layer must create,
run, and heal programmatically, and because criterion 4 is explicitly about driving the
platform from a coding agent. The dashboard is used only to confirm collector IDs and inspect
generated parser code once, for explainability.

**Collector invoked over `POST /dca/trigger`, not by shelling out per run.**
The collector ID is a stable API endpoint. Treating it as one is what makes this look like a
real pipeline rather than a script.

**Heals are human-in-the-loop by default. `--auto-approve` is not used.**
Bright Data's CLI never decides on its own that a scraper is broken — detection is our job,
approval is the operator's. Surfacing `--reject` as a first-class path (bad heal → sharper
prompt → retry) is a differentiator; most submissions will only demo approve.

---

## 5. Data model

```sql
CREATE TABLE runs (
  run_id       INTEGER PRIMARY KEY,
  collector_id TEXT    NOT NULL,
  source       TEXT    NOT NULL,
  started_at   TEXT    NOT NULL,
  row_count    INTEGER,
  status       TEXT    NOT NULL   -- ok | empty | partial | failed
);

CREATE TABLE records (
  run_id      INTEGER NOT NULL REFERENCES runs(run_id),
  recall_key  TEXT    NOT NULL,   -- stable identity: recall number or notice URL
  payload     TEXT    NOT NULL,   -- raw JSON, unmodified
  PRIMARY KEY (run_id, recall_key)
);

CREATE TABLE signals (
  signal_id   INTEGER PRIMARY KEY,
  run_id      INTEGER NOT NULL REFERENCES runs(run_id),
  kind        TEXT    NOT NULL,   -- see section 6
  field       TEXT,
  severity    TEXT    NOT NULL,   -- info | warn | critical
  detail      TEXT    NOT NULL,   -- human-readable, feeds the heal prompt
  heal_prompt TEXT,
  resolution  TEXT               -- pending | approved | rejected | ignored
);
```

`status` on `runs` matters: an absent run and a failed run must be distinguishable, or the
dashboard cannot tell "nothing broke" from "everything broke."

---

## 6. The five signals

This is the actual IP of the project. Each maps to one heal-prompt template.

| # | Signal | Trigger condition |
|---|---|---|
| 1 | Null-rate spike | Field ≥90% populated in run N−1, drops below threshold in run N |
| 2 | Cardinality collapse | Distinct values for a field fall sharply (e.g. 30 manufacturers → 2) |
| 3 | Row-count delta | Rows vanish with no corresponding delisting on the source |
| 4 | Schema drift | A key present in N−1 is absent entirely in N |
| 5 | Format violation | Values stop parsing to expected type (dates, recall-number pattern) |

Thresholds must be configurable constants in one place, not scattered magic numbers.
Every signal must be unit-testable against fixture files with no network access.

### Heal prompts must be specific

Vague prompts produce vague heals. Generated prompts must name the field, the expected
shape, and what changed.

Bad: `"the scraper is broken"`
Good: `"the manufacturer field returns null on all 50 rows; it should contain the
company name, previously extracted from the element adjacent to the product title"`

---

## 7. Failure paths — required, not optional

The app must behave correctly *before* a heal has run. This is simultaneously a
technical-excellence and a reliability signal.

- Collector returns zero rows → record run as `empty`, raise a signal, serve last-known-good
  data in the UI with a visible staleness banner. Do not show a blank page.
- Collector returns partial data → record as `partial`, flag affected fields, still store rows.
- Collector errors/times out → record as `failed`, do not write a `records` row, keep prior run intact.
- UI must have real loading, empty, error, and **degraded** states. Degraded is the interesting
  one and the one judges will not have seen elsewhere.

---

## 8. Conventions

- Python. Standard library plus minimal dependencies; justify every addition.
- `src/` for the package, `tests/` for tests, `fixtures/` for saved collector output.
- Health engine has **zero network calls** — it takes run data in, emits signals out. This makes it
  testable, and makes it fast to iterate without burning credits.
- Type hints on public functions. Docstrings explain *why*, not *what*.
- Fixtures are committed. They are the test corpus and they prove the signals work.
- No secrets in code. `.env` is gitignored; `.env.example` is committed.

---

## 9. Build schedule

| Day | Focus | Criteria |
|---|---|---|
| Tue 18 | Collector created, runner + SQLite, fixtures dumped | 3, 4 |
| Wed 19 | Health engine against fixtures — all five signals, offline | 3, 5 |
| Thu 20 | Break → detect → heal → approve → recover. **Record it.** LinkedIn post | 5, 6 |
| Fri 21 | UI: loading / empty / error / degraded | 2, 3 |
| Sat 22 | Repo hygiene, README, edge cases, Scraper Studio writeup | 3, 4, 6 |
| Sun 23 | Demo video, submit early | 6 |

**Thursday is the highest-value day.** The heal recording gates the demo video and the LinkedIn
post. Do not let it slip to the weekend.

---

## 10. Out of scope — do not build these

- Cross-source entity matching between Health Canada / CPSC / FDA taxonomies (fuzzy, multi-day, low score)
- User accounts, auth, multi-tenancy
- Email/SMS notification delivery
- ML-based anomaly detection — the five statistical signals are sufficient and explainable.
  Explainable beats clever here; a judge can follow a null-rate threshold, not a model.
- Anything requiring login-walled data

If a request would pull work toward this list, say so before building it.

---

## 11. Submission deliverables

- [ ] Public repo, real README, runnable by a stranger
- [ ] Demo video: problem → scraper workflow → heal moment (before/after numbers) → product
- [ ] Project description
- [ ] "How Scraper Studio was used" writeup — collector ID, schema, scraper type, at least one
      real heal event with a number attached ("N rows recovered after a selector change")
- [ ] Public data only, no secrets exposed
- [ ] Real empty/error/loading/degraded states
- [ ] LinkedIn post tagging WeMakeDevs (Daily Bugle track — separate prize, ~20 min of work)
