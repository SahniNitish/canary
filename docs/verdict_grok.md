# Grok verdict on Claude's Wed Aug 19 plan

**Source reviewed:** Claude's "Canary — Wed Aug 19 Execution Plan" (the truncated TUI dump plus the full plan in `~/.claude/plans/scalable-knitting-crown.md`).
**Checked against:** WeMakeDevs Into the Scrape-Verse pages (overview, rules, resources, kickoff guide, 2026-08-19), Bright Data CLI / Collection API / self-heal docs, Health Canada Recalls & Safety Alerts open dataset.

---

## Verdict

**Do not execute this plan in the order it is written.**

The architecture in `CLAUDE.md` is a winning idea. This Wednesday plan would spend the last buffer day building a beautiful offline detector against **invented JSON**, while the thing that decides eligibility and the grand prize is still marked optional.

If Phase B slips, Canary is a data-quality CLI with pytest. That fails **Rule 3** (Scraper Studio is mandatory), fails **criterion 4** (Use of Scraper Studio), and leaves **criterion 5** (self-healing) as a screenshot of a prompt string, not a healed collector. Criteria 4 and 5 are one third of the score. The demo is scored as hard as the code. A fixture-ingest demo is not the demo they asked for.

**Winning product (keep this sentence, kill every feature that does not serve it):**

> Canary watches a live Scraper Studio collector on Health Canada medical-device recalls, catches silent field loss against the last verified run, quarantines the bad snapshot, writes a precise heal prompt, previews the repair, human-approves it, and recovers **the same `c_*` Collector ID** with before/after numbers.

That is official idea #4 ("Self-healing scraper — the hero project") plus idea #2 (Collector ID as a production API). Many teams will attempt #4. The team that shows **break → detect → heal → same ID → N rows recovered**, with a judge-reproducible repo, wins Web-Slinger.

---

## What is already right (do not "improve" these)

Keep these. They are why Canary can still win.

| Decision | Why it scores |
|---|---|
| Not a recall aggregator | Matches the thesis. Breadth is a trap. |
| Immutable runs, never upsert | Load-bearing. Temporal compare dies without it. |
| Store raw JSON payloads | Do not invent our own silent-drop bug. |
| Health engine: zero network | Testable, credit-safe, Q&A-clean. |
| Human approve / first-class `--reject` | Organizers document `--reject`. Most teams will only demo approve. Safety-critical data makes HITL a feature, not a delay. Never `--auto-approve`. |
| `ok \| empty \| partial \| failed` | Absent ≠ failed. Judges notice empty/error/degraded. |
| Stdlib + pytest only | Spider-Sense (clean code) prize. Justify every dep. |
| Fresh git repo **inside** `canary/` | Home-dir git root is `/Users/NitishSahni`. One `git add` from `$HOME` is a career-ending commit. |
| Public Health Canada pages | Rule 6. Long-tail: no Bright Data pre-built scraper for this site. |
| Out of scope: auth, SMS, ML, CPSC/FDA this week | Correct. Those lose the week. |

`DECISIONS.md` is also correct. Rule 11/12: you must explain every non-obvious choice out loud. "The agent wrote it" is a losing Q&A answer.

---

## Issues that can lose the hackathon

Ranked. P0 = ineligible or grand-prize-dead. P1 = score left on the table. P2 = Q&A landmines.

### P0 — Phase B is treated as optional

Plan text to delete:

> If not authenticated or low on time, Phase A stands alone and is fully demoable.

That sentence is false under the published rules.

- **Rule 3:** project must use Scraper Studio to **create and run** a custom scraper.
- **Rule 5:** library scrapers do not qualify. Custom collector required.
- **Rule 9:** public repo, README, **example structured output**, demo video, **how Scraper Studio was used**.
- Kickoff / "What you're expected to do": at least one real create + run. **`c_*` Collector ID is the proof.** Demonstrate `bdata scraper heal` if you can. Judges will look for it. Wire the Collector ID into something real.

An offline health engine with hand-authored fixtures is a unit-test suite. It is not a submission.

`bdata login` is not a maybe. It is the first action today. No token is already confirmed in the plan. That is the blocker, not the signal math.

### P0 — Tuesday already slipped; this plan spends Wednesday on the wrong unknown

Schedule from `CLAUDE.md`:

| Day | Must ship |
|---|---|
| Tue 18 | Collector + runner + real fixtures |
| **Wed 19 (today)** | Health engine |
| **Thu 20** | Break → detect → heal → approve → recover. **Record it.** LinkedIn |
| Fri 21 | UI states |
| Sat 22 | README / writeup |
| Sun 23 | Demo video, submit **early** |

The collector does not exist. Today's plan still does five detectors against fake records first, and the live collector "if time remains."

Thursday is the highest-value day in *our own* spec. Healing is not instant: `create` is 5–15 minutes (up to 25), `heal` can take up to 15 minutes, and you must review preview → approve → re-run. If the first real collector is created Thursday afternoon, the recording has no slack.

**Correct order today:** one real vertical slice of the hero loop, then fill the other four signals offline from that real schema.

### P0 — Hand-authored schema will be the wrong schema

Plan fields: `recall_number`, `title`, `date_published`, `category`, `manufacturer`, `product`, `hazard`, `recall_url`.

Demo signal: null-rate on **`manufacturer`**.

Health Canada PDPs, especially medical devices, do not speak that vocabulary. You will get some mix of `company` / company name, `identification_number` / RA- numbers, affected-product tables (lot, serial, model, catalogue), recall class, issue text. The AI-generated collector will name columns. We do not.

If tests lock to `manufacturer` today, Phase B forces a rewrite tomorrow — the day you needed for footage.

**Rule:** `hc_baseline.json` is the sanitized output of a real `bdata scraper run`. Broken fixtures are copies of that file with **one** mutation each. No invented keys.

Optional `WebFetch` "for realism" is not a substitute. Judges will compare fixtures to the collector.

### P0 — "The five signals are the IP" is the wrong story

They are standard data-quality checks (completeness, cardinality, volume, schema, format). A judge who has seen a warehouse DQ dashboard will not give Creativity + Innovation for a null-rate threshold.

The original work, and the thing the kickoff page is selling, is:

**silent-failure evidence → specific heal prompt → Scraper Studio preview → validate → approve/reject → same Collector ID → verified recovery.**

Put that in README, DECISIONS.md, demo script, and LinkedIn. Keep the five signals as the *sensors*. They are not the product.

### P0 — The judge question you have not prepared: "Why scrape? Canada already publishes JSON."

This is the single most likely impact/originality objection, and the plan never mentions it.

Official feed (updated daily):

- JSON: `https://recalls-rappels.canada.ca/sites/default/files/opendata-donneesouvertes/HCRSAMOpenData.json`
- Portal: open.canada.ca dataset `d38de914-c94c-429b-8ab1-8776c31643e3`
- The public site itself links "Access recall and alert data in CSV and JSON formats."

If a judge believes we re-scraped a government dump, criterion 1 and 4 both die: "use the feed" and "why Scraper Studio?"

**The honest answer, which must be in the writeup:**

The open dataset is a **membership oracle** (IDs, URLs, archive state, coarse fields). Scraper Studio is for **PDP-only safety fields the dump does not reliably carry** — affected lots/serials/models, company on the notice, structured issue text. Canary uses the feed to prove a missing row is a scraper omission, not a delisting. That is the opposite of "we ignored the official data."

Until that oracle is in the engine, **do not claim** "rows vanished with no corresponding delisting on the source." The plan already admits this is stretch, then still encodes CLAUDE.md's wording. Dishonest `detail` text in a heal prompt is a Q&A kill shot.

Offline: fire `rowcount_delta` as a volume anomaly. When the feed fixture is present, name the missing IDs. Never over-claim.

### P0 — No plan for *how* to break the collector on Thursday

The demo needs a real heal against a real `c_*`, not `ingest hc_null_spike.json`.

Health Canada will not rename a CSS class on cue. You must break it **on purpose**, detect it, heal it:

1. Run healthy → save numbers (field populated 50/50).
2. Break extraction for one critical field (selector sabotage in IDE, or a heal prompt that *removes* the field, then treat that as the broken state — the cleaner path is: edit the generated parser so `company` / `affected_products` returns null; save draft; run).
3. Canary marks the run `partial`, raises critical, generates the prompt.
4. `bdata scraper heal <id> "<prompt>" --url <one PDP url>`
5. Inspect `preview_result`. Validate against field contracts. Approve.
6. Re-run **same Collector ID**. Show 50/50 restored.

Record the terminal the first time it works. Do not wait for a clean retake on Saturday.

The Wednesday plan's verification section never includes this loop. It verifies fixture ingest. That is practice, not the demo.

---

## P1 — Plan bugs that will fail Q&A or criterion 5 even if the collector exists

### 1. Baseline must be last-known-good, not N−1

The plan adds `get_last_known_good` for the UI, then runs `detect` against `get_previous_run`.

If run N is `partial` and run N+1 is also broken, N becomes the baseline and the alert goes quiet. That is the failure mode Canary exists to catch, implemented backwards.

Every signal row should record `baseline_run_id`. For this week, last operator-verified `ok` run is enough. No rolling statistics.

### 2. Thresholds without field contracts

`NULL_RATE_FLOOR = 0.70` on the union of keys will false-alarm on legitimately sparse fields (French titles, optional hazard, category-specific columns). Medical-device pages and food pages do not share a schema. Mixing them in one baseline is how you get pager noise in the demo.

Pin **one cohort**: recent **medical-device** recalls. One page family. One contract:

- required: identification number, product, company, affected_products, recall_date, source_url
- format: recall-number pattern, date parser
- `partial` = required field below contract, not "whatever key appeared in run 1"

Demo the break on `affected_products` or `company`, not a fictional `manufacturer`. Lot/model blank on a device recall is a sentence a judge feels.

### 3. `bdata scraper run` is not always `POST /dca/trigger`

Plan: *"`bdata scraper run --urls` routes via `/dca/trigger` — the CLI *is* the POST /dca/trigger path."*

Official CLI docs:

- small input → `POST /dca/trigger_immediate` then `GET /dca/get_result` (realtime)
- large input → fallback `POST /dca/trigger` then poll `GET /dca/dataset?id=j_*`

`POST /dca/trigger` returns `{ collection_id: "j_..." }`, not rows. If the runner assumes rows come back on the trigger call, live ingest will look like `empty`/`failed` and you will "heal" a healthy scraper.

For the first slice, wrapping `bdata scraper run` is acceptable (the CLI already polls). Mark it as an adapter. Invoke `subprocess.run([argv], shell=False, timeout=...)`. Never interpolate URLs or heal prompts into a shell string.

If there is time after the hero loop: one stdlib `urllib` POST + poll, so the writeup can show the Collector ID as an API. Do **not** add `requests` unless you must; the official Bright Data Python starter uses it, but §8 said justify every addition. Stdlib is the Spider-Sense answer.

Persist on each run: `collection_id` (`j_*`), `completed_at`, `input_count`, `baseline_run_id`, `error_code`, `error_detail`. The three-table schema in CLAUDE.md cannot explain a hung job.

### 4. Heal wrapper is missing flags the CLI actually needs

Docs:

```text
bdata scraper heal <collector_id> "<what broke>" --url https://...
```

Prompt cap: **1,000 characters**. Vague prompts produce vague heals; 4,000-character dumps get truncated or refused.

Plan's `heal --apply` does not pass `--url`, does not save `preview_result`, does not validate preview against contracts before `approve`.

Approve/reject is:

```text
bdata scraper approve <id> --url <url>
bdata scraper approve <id> --reject
```

`--reject` is a differentiator only if the audit trail shows: bad preview → reject → sharper prompt → good preview → approve. One `signals.heal_prompt` + one `resolution` column **overwrites** that history.

Add `heal_attempts` (prompt, preview_payload, validation_result, status, decision_reason). Cheap, and it is the reject-path proof.

### 5. Create-from-listing will burn credits and wander off-schema

Plan: `bdata scraper create "<HC recalls listing URL>" "<≤500-char extract description>"`.

A Discovery scrape of the index can fan out across food, vehicles, consumer products, drugs, devices. That is how you get mixed schemas, 25-minute generation, and a credit spike.

Create against **one medical-device PDP** (or a tiny explicit URL list), and put in the description: Discovery+PDP, this cohort only, these fields, do not follow unrelated categories. Cap the run to a handful of URLs. Save the `c_*` into `CLAUDE.md` as `SCRAPER_STUDIO_COLLECTOR_ID=...` (official getting-started step 5: pin it so the agent does not rebuild a scraper every session).

Promo code is `wemakedevs` (all lowercase) for **$50**, on top of 5k free page-loads. CLAUDE.md's "$53 promo" is a slip. If credits are missing, billing profile, then email contact@wemakedevs.org — they said they will top up.

### 6. Degraded data that looks current

`get_last_known_good` is necessary and not sufficient. Serving yesterday's rows without `data_status`, `verified_as_of`, `latest_run_status`, `age_seconds` is how a dashboard lies. The interesting UI state on Friday is **degraded**, not empty. The API/CLI must already return that envelope so Friday is paint, not a rewrite.

Never describe stale data as safe.

---

## P1 — Submission and judging gaps the Wednesday plan does not mention

Rule 9 and the kickoff page are a checklist. Today's plan covers git init and pytest. It does not cover the packet judges actually open.

| Required | Plan? | What to do |
|---|---|---|
| Public source repo | git init only | Own repo in `canary/`. GitHub public before Saturday. |
| Clear README | No (DECISIONS.md instead) | README: problem, 60-second run, collector ID, heal loop, screenshot/gif. DECISIONS.md is Q&A, not the front door. |
| Example structured output | No | Commit `examples/run_ok.json` and `examples/run_partial.json` from real collector output (secrets stripped). |
| Demo video ~ problem → scraper → structured output → product | Verification is fixture ingest | Script it around Thursday's recording. Criterion 6 is equal weight. |
| How Scraper Studio was used | "record collector_id later" | Collector ID, scraper type (Discovery+PDP), schema, **one heal with a number**: "company 50/50 → 0/50 → healed 50/50, same `c_*`." |
| AI disclosure | Missing | Rule 10. One README section: Claude/Codex/Grok used; human verified; you can explain it. |
| Participant understands the code | Implied | If you cannot explain a file, delete it. Rule 12 allows rejection of fully-generated unreviewed work. |

Also missing, small but real:

- **Registration.** Raffle is drawn from valid registrations. Confirm the Google Form is filed.
- **Pin collector ID in CLAUDE.md.** Official instruction. Prevents the agent from `scraper create`-ing a second collector and splitting the story.
- **`.gitignore` of `data/`** is fine; do **not** gitignore `fixtures/` or `examples/`. Those are the proof.
- **`.env.example` key name.** Official API snippets use `BRIGHT_DATA_API_TOKEN` / `BRIGHTDATA_API_KEY`. Pick one, document it, never commit the value, never show it in the video (Rule / best practice 4).
- **Python 3.14.3** is what this machine has. Judges will not. Pin `requires-python = ">=3.11"` and test that you are not using 3.14-only syntax.
- **Daily Bugle:** LinkedIn only, tag **WeMakeDevs**, can post more than once. Thursday footage is the post (before/after numbers + terminal). Separate Galaxy Watch prize, ~20 minutes, do not skip.
- **Tracks:** every project is auto-entered in Web-Slinger (Best Use of Bright Data), Suit-Up (Best UI, iPad), Spider-Sense (clean code, Keychron). There is nothing to opt into. Grand prize is one DGX Spark **to the team** (solo = you). Daily Bugle is a post, not a project.

### Track strategy (so we do not optimize the wrong prize)

- **Web-Slinger (grand prize)** is the target. Score it with: custom long-tail collector, coding-agent CLI workflow, real heal, Collector ID used as an API, structured output powering Canary (not a dead JSON file).
- **Spider-Sense** is almost free if we stay stdlib, tests, DECISIONS.md, no junk abstractions. Do not add a plugin framework.
- **Suit-Up** is Friday. A polished degraded-state UI can steal the iPad *if* the loop already works. A pretty aggregator UI with no heal footage will not win Web-Slinger and may not win Suit-Up either — they said "looks finished," not "has 12 pages."
- Do not build ideas 6–9 (RAG, search-keyword agent, subagent battle). Off-thesis.

---

## P2 — Small details (judges and future-you)

1. **`FORMAT_FIELDS` keys must come from the collector**, not `date_published` / `recall_number` guessed today.
2. **Cardinality on a low-diversity field** (recall_class has ~3 values) will false-fire. `CARDINALITY_MIN_BASELINE = 5` is a start; still exclude contracted enum fields.
3. **Row-count 50% drop** on a 8-URL cohort is one timeout. Need either a larger fixed cohort or pair row-count with the membership oracle.
4. **Empty run vs failed run:** collector HTTP 200 with `[]` is `empty`; timeout/4xx is `failed` and writes **no** records. Do not ingest a truncated file as empty.
5. **Heal prompt quality bar** from CLAUDE.md is correct. Bad: "the scraper is broken." Good: field, previous coverage, current coverage, expected shape, example URLs, "preserve the output schema." Stay under 1,000 characters.
6. **Do not shell `bdata` with a concatenated prompt.** Argument list only.
7. **Do not commit `*.db`.** Correct in gitignore. Provide `canary init-db` in README.
8. **Never commit tokens.** Scrub terminal recordings; CLI login prints `Key: 2e75****12bf` — still crop it.
9. **Criterion mapping in the plan over-credits Phase A.** A5/A6 wrapping `bdata` is not "Use of Scraper Studio" until a collector exists. Wrapping the CLI is plumbing.
10. **Main work must start after Aug 17** (Rule 7). Notes/architecture beforehand are allowed. `CLAUDE.md` is fine. Shipping a pre-built app is not. We are empty except CLAUDE.md — that is actually the eligible state. Good.
11. **Pakistan/Iran restriction** does not apply. Canada is fine.
12. **Do not add CPSC/FDA** until primary + heal footage exist. CLAUDE.md already said this. Stretch sources are how solo projects die on Saturday.
13. **Friday UI must include loading / empty / error / degraded.** Degraded is the one they have not seen. Plan correctly defers UI — do not sneak a dashboard in today.
14. **LinkedIn post is not "nice to have."** It is a second lottery ticket and marketing for judges who skim social.
15. **Submit Sunday early.** Form appears on the hackathon page before deadline. Packet: repo, video, description, Scraper Studio writeup. Do not discover the form at 11pm ET.

---

## Corrected Wednesday order

Do this, in this order. Stop when the hero loop is recorded; then fill signals.

### P0 — eligibility + hero loop (today, before anything pretty)

1. `git init` inside `canary/` (not `$HOME`). `.gitignore` first. `.env.example`. `pyproject.toml` (pytest only, `requires-python = ">=3.11"`).
2. User: `bdata login`. Confirm promo `wemakedevs` if balance is empty.
3. Create **one** medical-device Discovery→PDP collector. Tiny URL cohort. Wait for `c_*`. Pin it in `CLAUDE.md`.
4. Run it. Commit sanitized `fixtures/hc_baseline.json` + `examples/run_ok.json`.
5. Minimal SQLite: immutable `runs` / `records` / `signals`. Last-known-good lookup. Field contracts from the **real** keys.
6. One signal: null-rate or schema-drift on a required field vs last `ok` run.
7. Heal-prompt generator that names field, coverage, shape, examples, schema-preserve, ≤1000 chars.
8. Honest break → ingest → detect → `heal` → inspect preview → approve → same `c_*` healthy run.
9. Capture terminal + numbers immediately. That file is Thursday's video and the LinkedIn post.

### P1 — reliability surface (after P0 is green)

10. Derive four more broken fixtures from the real baseline (one mutation each) + empty/failed.
11. Remaining four pure signals. Offline tests, no network.
12. `heal_attempts`, reject → rewrite prompt → retry test.
13. Official-feed membership fixture; exact missing IDs when present; anomaly-only wording when not.
14. Run envelope: `data_status`, `verified_as_of`, `latest_run_status`, `age_seconds`.

### P2 — only then

15. CLI tables, README, DECISIONS.md, AI disclosure, Scraper Studio writeup stub.
16. Friday: operator UI with degraded banner. Not a recall browser.

Do not add sources, ML, plugins, notifications, auth, or a generalized "any website" framework.

---

## Today's acceptance gate (replace the plan's verification block)

Wednesday is not done when pytest is green on fake manufacturer data. It is done when all of these are true:

- [ ] Real `c_*` exists, pinned in `CLAUDE.md`, no token in git
- [ ] Real collector JSON is the fixture schema
- [ ] One `ok` run and one silently-broken run stored as immutable snapshots
- [ ] Broken run is `partial` or `empty`, not silently `ok`
- [ ] Signal compares to last **verified** run, with numbers and failing URLs
- [ ] Heal prompt is specific and ≤1000 chars
- [ ] Real `bdata scraper heal` reached awaiting-approval with a preview
- [ ] Preview checked against contracts before approve
- [ ] Same Collector ID produced a healthy recovery run
- [ ] Before/after counts saved for the demo
- [ ] `pytest` passes offline
- [ ] `canary/` is its own git repo; `$HOME` was never staged

---

## Bottom line

Claude's plan is a strong **offline engine design** and a weak **hackathon strategy**. Codex is right that Phase B is mandatory and that last-known-good, real fixtures, heal audit trail, and the official feed-as-oracle belong in the product.

The additional losses I care about, on top of that: no controlled-break/heal recording plan, CLI-vs-trigger lifecycle confusion, missing Rule 9 artifacts (example output, README, AI disclosure), inventing `manufacturer`, credit-unsafe listing-page create, and treating five DQ checks as the innovation story.

**Execute the hero loop today. Then the five signals. Then the UI.** Anything else is how a good thesis becomes a non-qualifying repo on Sunday.

---

# Verdict 1.1 — Claude plan v2 (post-verdict)

**Source reviewed:** Claude's "Canary — Wed Aug 19 Execution Plan (v2, post-verdict)", which folded in `verdict_grok.md` and `verdict_codex.md`.
**Question asked:** Ready to code?

## Verdict

**Almost. This is the plan to execute.** Do not start the Python package until four things are locked. The strategy is now correct. The leftover bugs are the kind that make the first live run look like a failed product.

v2 fixed the actual loss conditions from verdict 1.0: live `c_*` first, last-known-good, real fixtures, membership oracle, `--reject` audit, degraded envelope, no invented `manufacturer` demo. That matches both reviews and the WeMakeDevs rules.

**Ready-to-code rule:** start P0.1–P0.2 now (git init inside `canary/`, gitignore, `pyproject.toml`, `.env.example`, `DECISIONS.md` stub). Do **not** write `signals.py` or lock `FIELD_CONTRACTS` until `bdata login` has succeeded and `fixtures/hc_baseline.json` is real collector output.

Wednesday is not "pytest green." Wednesday is **same `c_*`, before/after numbers, terminal captured**.

If login cannot happen in this session: scaffold + wait. **Do not** invent `hc_baseline.json`. That is v1 again.

---

## What v2 got right (do not reopen)

- Live create → run → heal → same-Collector-ID recovery is P0, not optional.
- Winning sentence: closed loop is the product; five signals are sensors.
- Tiny explicit PDP cohort, not the listing index.
- Pin `SCRAPER_STUDIO_COLLECTOR_ID` in `CLAUDE.md`.
- `get_last_known_good`, not N−1.
- Official Health Canada JSON as membership oracle; never claim "no delisting" without it.
- `heal_attempts` + first-class `--reject`.
- Degraded envelope (`data_status`, `verified_as_of`, `latest_run_status`, `age_seconds`).
- `empty` (200 + `[]`) vs `failed` (timeout/4xx, no records).
- `subprocess.run([...], shell=False)`. CLI wrapper marked as a temporary adapter.
- Promo code `wemakedevs` = $50. `requires-python = ">=3.11"`.
- Own git repo inside `canary/`; never stage from `$HOME`.
- Do not ignore `fixtures/` or `examples/`.
- Out of scope: CPSC/FDA, ML, notifications, auth, plugin framework.
- Wrapping the CLI is plumbing until a real `c_*` exists.
- Acceptance gate matches verdict 1.0.

---

## Still wrong if you code v2 as written

### 1. `FIELD_CONTRACTS` is still a guessed schema

v2 hardcodes:

```python
FIELD_CONTRACTS = {
  "identification_number": {"required": True, "format": r"^RA-\d+$"},
  "product": {"required": True}, "company": {"required": True},
  "affected_products": {"required": True}, "recall_date": {"required": True, "parser": "iso_date"},
}
```

`identification_number` + `r"^RA-\d+$"` is the old `manufacturer` bug in a nicer coat. Health Canada device notices do not reliably use `RA-123` as the stable key. If that regex runs on a healthy first scrape, **format_violation fires on the baseline** and the demo is a false alarm.

Create prompt may *ask* for company / affected products / date. Contracts are written **after** `fixtures/hc_baseline.json` exists, using the keys the collector actually returned. `recall_key` = whatever stable id came back (often the notice URL). Empty nested values (`[]`, `{}`, `""`) count as null.

### 2. "Edit the generated parser" has no CLI step

The collector lives in Bright Data, not in `src/`. There is no local parser file to patch. Pick one break method *before* scaffolding:

- **Preferred (stays in terminal):** heal-to-break. `bdata scraper heal` with "return `company` as null / stop extracting it", approve, run, Canary detects, heal-to-fix, approve, same `c_*`. Two heals, extra 15–30 min, fully recordable.
- **Faster:** 60 seconds in the Studio IDE, null one field, save to production, back to CLI. Say so in the demo ("we sabotaged the selector").

Do **not** mutate a fixture and call that the hero loop.

### 3. Heal timeout will kill P0.9

CLI default `--timeout` is **600s**. Heal can take **15 min**. `subprocess.run(..., timeout=60)` or the CLI default will SIGTERM the heal and you will think Scraper Studio is broken.

Set `bdata scraper heal ... --timeout 1200` and `subprocess.run(..., timeout=1300)`. Never `shell=True`.

### 4. `--url` on heal is a hint, not the API

v2 env note is right (CLI command reference: *woven into the next-step hint; not sent to the heal call*). Passing `--url` is fine; putting the PDP URL **inside the 1000-char prompt** is what actually steers the model. Do not treat a missing `--url` as a failed heal, and do not skip the URL in the prompt.

P0.9 writing `bdata scraper heal <c_id> "<prompt>" --url <pdp>` is therefore optional sugar, not the mechanism.

---

## Small, still worth changing

| Item | Change |
|---|---|
| Login fallback | If `bdata login` is blocked: scaffold + wait. Do not invent fixtures. |
| `heal_attempts` | Create the table in **P0.5**, persist the first heal. Schema is cheap; Thursday's DB should show the attempt. |
| Scraper type | A handful of PDP URLs is a **PDP** collector. Do not force Discovery+PDP unless you have a *device-filtered* listing URL. Honest type in the writeup. |
| Seed URLs | Pick 5–8 recent medical-device notice URLs from the official JSON feed. Do not scrape the index to find them. |
| README | 15-line stub in P0 (problem, how to run, `c_*` placeholder, AI disclosure). Full README can wait. Empty repo + great footage still fails Rule 9 if Saturday slips. |
| Impact sentence | Control-plane line is for engineers. Criterion 1 needs the CLAUDE.md story: blank company → search returns nothing → recalled device still ships. One sentence in README. |
| Daily Bugle | P0.10 clip **is** the LinkedIn post. Tag **WeMakeDevs**, LinkedIn only. |
| Step 4 "commit" vs "nothing committed until you ask" | Write files; user gates `git commit`. Fine. |
| Registration | Confirm the Google Form is filed (raffle + eligibility). Not a code task. |
| Duplicate numbering (two "6.", two "13.") | Ignore. |

---

## Bottom line (1.1)

v2 is a winning strategy with four execution landmines: guessed contracts, no real break method, 10-minute heal timeout, and `--url` superstition.

Start scaffold now. Lock schema and signals to the first real collector JSON. Break the collector on purpose (heal-to-break or IDE), with timeouts that survive a 15-minute heal. Record the first success. Then P1.

That is the only order that still makes Sunday a submission rather than a pytest repo.
