# Codex verdict on Claude's Wed Aug 19 plan

## Decision

Proceed with Canary, but do **not** execute the plan in its current order.

The offline health engine is valuable, but it is not the highest-risk unknown. The project cannot qualify without a real Scraper Studio collector, and hand-authored fixtures may force the health engine to be rewritten once the actual collector schema is known. The shortest defensible route is one real vertical slice first, followed by the remaining offline signals.

The winning product is not a recall aggregator. It is an auditable control plane that detects a silently corrupt scraper result, quarantines it, creates a precise Scraper Studio repair, validates the proposed repair, and restores the same Collector ID.

## What is already right

Keep these decisions:

- Python standard library plus `pytest` only.
- Immutable run snapshots and plain `INSERT`, never upsert.
- Raw collector payloads preserved as JSON.
- A health engine with zero network calls.
- Human approval as the default for a safety-sensitive repair.
- Saved fixtures and offline tests.
- Explicit `empty`, `partial`, and `failed` run states.
- A first-class rejection path.
- No auth, notifications, multiple national sources, or ML anomaly detection during the hackathon.
- A fresh Git repository inside `canary/`; do not stage it through the home-directory repository.

These choices support technical excellence, reliability, and clean-code judging without unnecessary scope.

## Required corrections before coding

### 1. Phase B is mandatory, not optional

Delete this fallback from the plan:

> If not authenticated or low on time, Phase A stands alone and is fully demoable.

It is testable, but it is not a valid hackathon submission. Scraper Studio is mandatory, and the judges expect a real create, run, heal, and same-Collector-ID recovery flow.

The first milestone today must be:

1. Authenticate with `bdata login`.
2. Create one real collector.
3. Run it on a small, fixed cohort.
4. Save the real output as the canonical healthy fixture.
5. Derive broken fixtures from that exact output shape.
6. Implement one null/schema failure end to end.
7. Trigger a real heal and capture raw footage as soon as it works.

Only after that should the other four signal implementations be filled in.

### 2. Narrow the target to one Health Canada page family

Do not mix food, vehicles, consumer products, public advisories, drugs, and medical devices in one baseline. Their page templates and legitimately optional fields differ, so global null and schema rules will create false alarms.

Recommended MVP cohort: **recent Health Canada medical-device recalls**.

This cohort provides a coherent and high-impact schema:

- `identification_number`
- `product`
- `brand`
- `company`
- `affected_products` with lot/serial and model/catalogue values
- `issue`
- `recall_class`
- `recall_date`
- `source_url`

The demo failure should target `affected_products` or `company`, not a fictional generic `manufacturer` field. Missing affected lot/model data is concrete, safety-relevant, and visually persuasive.

### 3. Do not hand-author an imaginary collector schema

`hc_baseline.json` must come from a real Scraper Studio run. The proposed fields do not match all live Health Canada PDPs, and collector output naming cannot be assumed before the collector exists.

Once the real baseline is saved:

- Copy it to create deterministic broken fixtures.
- Change exactly one dimension per fixture.
- Keep recall keys, cohort, and unaffected values identical.
- Add a small fixture manifest explaining the intentional mutation.

Fetching a live page for realism is not optional. The fixture corpus must represent the actual collector contract judges will see.

### 4. The five signals are not the IP

Keep the five signals, but stop describing null rate, cardinality, volume, schema, and format checks as novel IP. These are standard data-quality checks.

Canary's differentiated contribution is the closed loop:

> temporal and source-aware evidence -> precise repair prompt -> Scraper Studio preview -> validation -> approval/rejection -> same Collector ID -> verified recovery

That is the story to encode in `README.md`, `DECISIONS.md`, and the demo.

### 5. Compare against the last verified baseline, not blindly against N-1

Replace `get_previous_run(...)` as the health baseline with `get_last_known_good(...)`.

A broken or partial run must never become the next baseline. Otherwise a persistent failure becomes the new normal and stops alerting.

Each signal should record the `baseline_run_id` it used. For this hackathon, a rolling statistical model is unnecessary; the last operator-approved healthy run is sufficient and easier to explain.

### 6. Add field contracts and cohort rules

Threshold constants alone are insufficient. The Runner needs to know which fields are critical, which are optional, and which checks apply to which cohort.

Use one small standard-library structure in `config.py`, not a new framework or YAML parser. For example:

```python
FIELD_CONTRACTS = {
    "identification_number": {"required": True, "format": r"^RA-\d+$"},
    "product": {"required": True},
    "company": {"required": True},
    "affected_products": {"required": True},
    "recall_date": {"required": True, "parser": "iso_date"},
}
```

Use these contracts to derive `partial` status and format checks. Do not infer criticality from whatever keys happened to occur in one run.

### 7. Make row-count evidence honest

The offline rule cannot claim "no corresponding delisting on the source" unless it has source-membership evidence.

Health Canada already publishes an official daily JSON/CSV feed. Use it as a structural oracle for expected recall IDs, URLs, archive state, and core fields. Scraper Studio remains central because it extracts richer PDP-only content such as companies and affected lot/model tables.

For the minimum implementation:

- Save a small official-feed fixture for the same medical-device cohort.
- Pass it into the pure health engine as optional expected membership.
- When present, report exact missing IDs.
- When absent, label the signal only as a row-count anomaly; do not claim a confirmed scraper omission.

This converts the judge's likely "why scrape when JSON exists?" objection into Canary's strongest reliability proof.

### 8. Preserve the real Bright Data job lifecycle

The production Runner should not pretend `POST /dca/trigger` immediately returns records. It returns a collection/snapshot ID that must be polled until ready.

Use the CLI for `create`, `heal`, and `approve`, because those actions demonstrate the coding-agent workflow. For scheduled production runs, retain the original architecture decision and call the Collection API directly with the standard library. At minimum, persist:

- `collection_id`
- `completed_at`
- `input_count`
- `baseline_run_id`
- `error_code`
- `error_detail`

If direct API integration cannot fit today, the CLI wrapper is acceptable for the first vertical slice, but mark it as a deliberate temporary adapter. Invoke it with an argument list through `subprocess.run(..., shell=False, timeout=...)`; never build a shell command string containing URLs or prompts.

### 9. Add a heal-attempt audit trail

The current three-table model cannot represent the proposed reject -> sharper prompt -> retry workflow. One `heal_prompt` and one `resolution` on `signals` would overwrite history or lose it.

Add one minimal table:

```sql
CREATE TABLE heal_attempts (
  attempt_id        INTEGER PRIMARY KEY,
  signal_id         INTEGER NOT NULL REFERENCES signals(signal_id),
  created_at        TEXT    NOT NULL,
  prompt            TEXT    NOT NULL,
  status            TEXT    NOT NULL,
  preview_payload   TEXT,
  validation_result TEXT,
  view_url           TEXT,
  decided_at         TEXT,
  decision_reason    TEXT
);
```

The heal command should save the preview and validate it with the same contracts before approval. Human approval remains the default; validation gives the operator evidence rather than a blind yes/no choice.

### 10. Quarantine degraded data explicitly

`get_last_known_good` is correct, but stale data must never look current. The eventual UI/API must return health metadata with the records:

- `data_status`
- `verified_as_of`
- `latest_run_status`
- `age_seconds`

The suspect snapshot is stored for diagnosis but not promoted. The last verified snapshot may be displayed with a prominent degraded state, never described as safe or current.

## Revised execution order for Wed Aug 19

### P0 — prove eligibility and the hero loop

1. Initialize the repository and secret-safe scaffold.
2. Log in to Bright Data.
3. Create a medical-device Discovery -> PDP collector with a deliberately small input cohort.
4. Run it and commit the sanitized real output fixture.
5. Implement the minimum immutable database path.
6. Implement field contracts plus one null/schema signal against the last-known-good run.
7. Generate one evidence-rich heal prompt.
8. Break the collector honestly, run it, detect the failure, heal it, inspect the preview, approve it, and verify recovery using the same Collector ID.
9. Record the raw terminal and UI evidence immediately.

### P1 — complete the promised reliability surface

10. Derive the remaining four broken fixtures from the real baseline.
11. Implement and test all five pure signal functions.
12. Add empty, partial, failed, and degraded-path tests.
13. Add `heal_attempts` persistence and rejection/retry coverage.
14. Add the official-feed membership fixture and exact missing-ID evidence.

### P2 — only if P0 and P1 are green

15. Improve CLI table formatting.
16. Expand `DECISIONS.md` and README explanations.
17. Prepare the operator-focused dashboard for Friday.

Do not add more sources, a rolling anomaly model, deployment infrastructure, alerts, accounts, or a generalized plugin system.

## Acceptance gates for today

Today's work is complete only when all of these are true:

- A real `c_*` Collector ID exists and is recorded without exposing a token.
- A real Scraper Studio output fixture defines the schema used by the tests.
- One healthy and one silently broken immutable run exist in SQLite.
- The broken run completes but is marked `partial` or `empty` by Canary.
- A critical signal compares against the last verified run and includes numerical evidence plus failing URLs.
- The generated prompt names the broken field, previous coverage, current coverage, expected shape, examples, and the instruction to preserve the output schema.
- A real heal reaches the approval gate.
- The preview is checked before approval.
- The same Collector ID returns a healthy recovery run.
- The before/after numbers and terminal evidence are captured for the demo.
- Offline tests pass without network access.

## Final verdict to Claude

The proposed components are mostly correct; the sequencing and evidence model are not. Do not spend the day perfecting five detectors against invented JSON while the mandatory collector remains optional. Build the smallest real break -> detect -> heal -> validate -> recover loop first. Once that proof exists, completing the other deterministic signals is low-risk offline work.

The winning sentence is:

> Canary catches silent loss of safety-critical recall fields, quarantines the suspect snapshot, validates a Scraper Studio repair, and restores the same production collector before corrupt data reaches downstream users.

---

## Verdict 1.1 — final execution gate

### Decision: GO after six corrections

The v2 plan is much stronger—roughly **9/10 as an execution plan**. Its core sequence is now correct: real collector first, hero loop immediately, offline reliability afterward.

Apply these corrections before coding:

### 1. Call the P0 collector a batched PDP collector

A fixed list of detail-page URLs is not Discovery -> PDP. It is a PDP collector run against multiple inputs. That is sufficient for the competition and is the safer scope today. Discovery can remain out of scope until the hero loop works.

Create the scraper from one representative medical-device PDP, then run the fixed cohort through an input file.

### 2. Correct the live run command

The installed Bright Data CLI requires a positional URL, `--urls`, or `--input-file`. The command currently shown without any of these is incomplete.

Commit a small URL manifest because it defines the monitored cohort, and run:

```bash
bdata scraper run <c_id> \
  --input-file fixtures/hc_device_urls.json \
  --pretty \
  -o fixtures/hc_baseline.json
```

The create command still receives one representative PDP URL and a description of the output contract.

### 3. Make the development/production version path explicit

Editing a draft and then running the collector normally may execute the healthy production version instead of the deliberately broken draft. Choose one path and use it consistently:

- Publish the deliberately broken parser, then run the default production version; or
- Keep the break in development and run it explicitly with `--version dev`.

After inspecting and validating the heal preview, publish the approved repair explicitly:

```bash
bdata scraper approve <c_id> \
  --auto-save \
  --url <verification_url> \
  --pretty
```

`--auto-save` does not bypass human approval. It publishes only after the operator deliberately executes the approve command.

### 4. Put `baseline_run_id` in one correct place

The v2 plan first calls `baseline_run_id` a `runs` column, then says every signal stores it and expects it in a signal row. Store it on `signals`:

```sql
baseline_run_id INTEGER REFERENCES runs(run_id)
```

Remove it from `runs` unless the implementation deliberately assigns one shared baseline to the entire run. For the current acceptance test, the signal-level column is clearer.

### 5. Remove the commit and fixture-duplication contradictions

P0 says to commit the real fixture, while final verification says nothing is committed without user approval. Change P0 to **save and sanitize** the fixture. Commit only when requested.

Use `fixtures/hc_baseline.json` as the single canonical healthy example today. Do not duplicate the same payload as `examples/run_ok.json` unless the README or UI later needs a deliberately smaller presentation sample.

### 6. Correct the criteria mapping

Criterion 2 is creativity and innovation, not UI. The degraded/quarantine experience maps to:

- Criterion 2: creative operator experience and fail-safe presentation.
- Criterion 3: complete edge-state handling.
- Criterion 5: reliability and preventing corrupt snapshots from being promoted.
- Best UI track: independently, when the Friday operator interface is polished.

### Two non-blocking refinements

- Finalize which fields are strictly required only after inspecting the real collector output across the selected cohort. Do not assume every medical-device recall legitimately contains `company` and `affected_products` in the same form.
- Replace promised `50/50 -> 0/50 -> 50/50` figures with observed `N/N -> 0/N -> N/N`. A small real cohort is more credible than an invented large result.

### Final 1.1 instruction to Claude

After these six edits, start implementation. Do not reopen the architecture or add features before the real PDP batch can complete the break -> detect -> heal -> validate -> approve -> same-Collector-ID recovery loop.
