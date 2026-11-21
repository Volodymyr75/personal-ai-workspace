# Development and verification

## Tools

For the complete container workflow, install and start Docker Desktop (Apple Silicon on M-series Macs), plus Git. No AI account, API key, hosting account or n8n integration credentials are needed for M0–M1.2.

For native code checks, install Python 3.13.18 through uv 0.13.9 and Node.js 24.22.3 with npm. Versions are recorded in `backend/.python-version` and `.node-version`. `uv sync --frozen` and `npm ci` install the committed dependency sets. Project-local `.tools/` installations are ignored and optional; they are not part of the repository.

## Container workflow (from repository root)

```sh
python3 scripts/init_local_env.py
docker compose --env-file .env -f infrastructure/compose.yaml config --quiet
docker compose --env-file .env -f infrastructure/compose.yaml up --build -d api worker web
docker compose --env-file .env -f infrastructure/compose.yaml exec api python -m paw.cli bootstrap
curl --fail http://127.0.0.1:8000/api/v1/health
curl --fail http://127.0.0.1:8000/api/v1/ready
```

Open `http://127.0.0.1:3000`. The foundation pages are English, responsive and explicitly mark unavailable workflows. The shell does not query or imply live health. API docs are at `http://127.0.0.1:8000/docs`.

Compose runs migrations before starting the API. Run bootstrap again: it should log `bootstrap_unchanged`. Verify the actual database counts and timestamps without printing credentials:

```sh
docker compose --env-file .env -f infrastructure/compose.yaml exec postgres psql -U paw -d paw -c "SELECT event_type, entity_key, sequence, recorded_at FROM system_events ORDER BY sequence;"
```

Expected foundation-only installation: two nodes, one link and three events. Once Worker initializes, its node/link bring the total to five events. The times are when this installation actually registered the components, not the repository creation date. A database volume reset loses this installation's history; do not remove volumes casually.

## Checks

```sh
cd backend
uv sync --frozen
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest tests/unit -q
cd ../frontend
npm ci
npm run lint
npm run format:check
npm run typecheck
npm run build
cd ..
docker compose --env-file .env -f infrastructure/compose.yaml --profile test run --build --rm tests
```

Docker tests use a separate `paw_test` database with temporary storage and a fresh random schema per test. They never drop/reset the live `paw` database. Native integration tests require `PAW_TEST_DATABASE_URL` pointing to a dedicated database named exactly `paw_test`; without it they are skipped, which is not evidence of database correctness. CI and the Compose test service set it and run the full suite.

The integration suite verifies migrations, real readiness, concurrent bootstrap, retry idempotency, full event after-state, rollback after an injected failure, append-only enforcement and server-controlled timestamps. A missing historical event for an existing registry entry is rejected rather than backfilled.

## Standalone M1.4 parser check (no API upload yet)

From the repository root, using the installed backend virtual environment:

```sh
backend/.venv/bin/python -c 'from pathlib import Path; from paw.tools.google_ads_csv import parse_campaign_summary; r = parse_campaign_summary(Path("examples/google_ads_campaign_summary_synthetic.csv").read_bytes()); print(r.period_start, r.period_end, r.currency, len(r.details), len(r.totals)); print(r.warnings)'
```

Expected: `2026-11-01 2026-11-07 UAH 2 1`, with account scope and coverage unverified.
Detail cost sums to 50.00; the separate total is 50.00, not additional spend.
Summary markers are read from `Статус кампанії` or `Кампанія`; the normalized
`summary_label` is separate from optional campaign identity. Conflicting labels
fail with `ambiguous_summary`. Source cells remain unchanged. A blank/`--`
campaign is permitted only for summaries, never for detail rows.
This synthetic file is for the standalone parser; the existing upload API still
requires a generic CSV without preambles. The parser does not persist originals.
Explicit Ukrainian campaign-summary, campaign-daily, search-keyword and search-term
profiles are supported. Unknown columns remain source text. One private aggregate,
two private daily exports, one keyword and one search-term export were verified locally.
Date ranges accept full Ukrainian dates or `DD.MM.YYYY`, separated by a spaced dash.
Delimiter defaults to comma; semicolon requires an explicit argument.

For the daily profile, run from the repository root:

```sh
backend/.venv/bin/python -c 'from pathlib import Path; from paw.tools.google_ads_csv import parse_campaign_daily; r = parse_campaign_daily(Path("examples/google_ads_campaign_daily_synthetic.csv").read_bytes()); print(r.report_type, len(r.details), len(r.totals), sum(x.cost for x in r.details)); print([x.day for x in r.totals])'
```

Expected: `campaign_daily 4 3 28.00`. The three summary dates are November 1,
November 2 and `None` (whole-period summary). Each detail needs a `День` value in
`YYYY-MM-DD` format within the inclusive preamble period. Blank/`--` dates are
allowed only for summaries. Invalid/missing/out-of-period dates fail with
`invalid_report_day`, `missing_report_day` or `report_day_out_of_period`.
Missing days are not filled with zeroes. Duplicate campaign/day detail rows are
preserved with `duplicate_daily_rows`; callers must resolve them before aggregating.
Different dates/campaigns and repeated summary rows do not trigger this warning.
Detail/summary discrepancies are retained without automatic reconciliation or
blocking for incomplete coverage. These are pure parsers, not batch JSON assembly.

For search keywords, run from the repository root:

```sh
backend/.venv/bin/python -c 'from pathlib import Path; from paw.tools.google_ads_csv import parse_search_keywords; r = parse_search_keywords(Path("examples/google_ads_search_keywords_synthetic.csv").read_bytes()); print(r.report_type, r.currency, len(r.details), len(r.totals), sum(x.cost for x in r.details)); print([(x.keyword, x.match_type) for x in r.details])'
```

Expected: `search_keywords UAH 2 1 150.00`, with keyword text `[synthetic exact]`
and `"synthetic phrase"`, normalized match types `exact` and `phrase`.
The exact title is `Звіт про ключові слова для пошуку`; detail rows additionally
require `Ключове слово`, `Група оголошень` and `Тип відповідності`. Supported
match labels are `Точна відповідність`, `Фразова відповідність`, `Широка відповідність`.
Unknown match labels fail with `unsupported_match_type`; missing keyword/group
values fail with `missing_keyword`/`missing_ad_group`. Quotes/brackets are preserved
as keyword text, not used to infer match type. Status remains source text.
Summary labels are recognized in keyword status, keyword or campaign columns.
Repeated campaign/group/keyword/match tuples remain intact with `duplicate_keyword_rows`;
no row is silently deleted or aggregated. Summaries and detail may differ in coverage.
Row contracts are shared as `GoogleAdsRow`/`GoogleAdsReport` with explicit `report_type`.
All public Google Ads examples now use `UAH` (hryvnia), matching the owner's account.
Currency is read from the source; there is no conversion or default to UAH when absent.

For search terms, run from the repository root:

```sh
backend/.venv/bin/python -c 'from pathlib import Path; from paw.tools.google_ads_csv import parse_search_terms; r = parse_search_terms(Path("examples/google_ads_search_terms_synthetic.csv").read_bytes()); print(r.report_type, r.currency, len(r.details), len(r.totals), sum(x.cost for x in r.details)); print([(x.summary_label, x.cost) for x in r.totals])'
```

Expected: `search_terms UAH 2 3 150.00`. Separate totals contain 150.00 UAH for
visible terms, 250.00 for other terms and 400.00 for the account. Do not sum these
overlapping totals or distribute other-term activity to invented queries/keywords.
Parser output retains source numbers; cross-report coverage calculation belongs
to the later batch/evidence step, and a discrepancy alone does not reject a file.
Summary-only search-term exports are accepted with empty `details`; a file with
neither detail nor summary rows fails with `empty_report`.

The exact title is `Звіт "Пошукові терміни"`; required extra columns are
`Пошуковий запит`, `Група оголошень`, `Тип відповідності`. Search term and optional
linked keyword text remain verbatim; added/excluded status remains source text.
Missing query/group values fail with `missing_search_term`/`missing_ad_group`.
Missing/blank/`--` keyword links produce `keyword_link_unavailable`, never an inferred link.
Exact/phrase/broad labels are supported, with exact/phrase close variants
(` (наближений варіант)`) retained as `close_variant=True` plus original `match_type_text`.
Unknown labels fail with `unsupported_match_type`. Summary labels are recognized
in query/campaign columns. Summary rows have no query/keyword/match identity.
Repeated campaign/group/query/keyword/match-label detail keys remain intact with
`duplicate_search_term_rows`; nothing is silently aggregated or removed.

## M1.4 local JSON batch

From the repository root, with the backend environment installed:

```sh
backend/.venv/bin/python scripts/build_google_ads_batch.py \
  --account-ref synthetic-account \
  --period-start 2026-11-01 --period-end 2026-11-07 \
  --source campaign_summary=examples/google_ads_campaign_summary_synthetic.csv \
  --source campaign_daily=examples/google_ads_campaign_daily_synthetic.csv \
  --source search_keywords=examples/google_ads_search_keywords_synthetic.csv \
  --source search_terms=examples/google_ads_search_terms_synthetic.csv \
  --output /tmp/paw-synthetic-batch.json
```

Use a new output path; an existing file fails with `output_exists` and is untouched.
The checked-in `examples/google_ads_batch_synthetic.json` shows the same four sources
with a fixed example UUID. CLI generates a UUID unless `--batch-id` is supplied.
Private output must stay outside Git, alongside the original private exports.

Inspect JSON with `python3 -m json.tool /tmp/paw-synthetic-batch.json`.
Expect `schema_version: 1`, `UAH` and four separate report arrays. Daily example covers
November 1–2 while the requested interval is November 1–7: it explicitly gets
`source_period_differs` and keeps its actual period. This intentionally demonstrates
that a requested period does not overwrite source facts. Example reports also have
synthetic, independently chosen values; never add their spend together.

The account reference is a local owner assertion, not a verified Google account ID.
Sources are identified by SHA-256; row IDs include their source's physical line range.
Decimal metrics are JSON strings (use Decimal, not float, for later arithmetic),
counts remain integers and missing values null. Headers/raw cells are retained.
Known currency values are listed in `observed_currencies`; batch `currency` is null
if any source row lacks currency. Conflicting observed currencies fail rather than
convert or combine. Identical source bytes fail with `duplicate_source`, even with
different filenames. Multiple distinct reports of one type are kept and warned about.
Source period mismatches, overlapping intervals and parser warnings are retained.

Bounds: eight files, 40 MiB combined input, existing 10 MiB per-file parser limits,
20 MiB encoded JSON. File types must be explicitly declared; no filename guessing.
The CLI supports one explicit delimiter for all inputs. The application function
`build_google_ads_batch(spec, sources)` supports per-source delimiters and returns
bytes without writing files. Neither path uploads, calls AI, or modifies platform data.
The package has `ai_ready: false`: it includes raw source text and needs a bounded
deterministic evidence projection before later model submission. See ADR-018.

CLI code checks from `backend`: `.venv/bin/ruff check . ../scripts/build_google_ads_batch.py`,
`.venv/bin/ruff format --check . ../scripts/build_google_ads_batch.py`,
`MYPYPATH=src .venv/bin/mypy ../scripts/build_google_ads_batch.py`.

## M1.4 campaign evidence

From the repository root, select the daily source explicitly from the synthetic batch:

```sh
backend/.venv/bin/python scripts/build_google_ads_evidence.py \
  --input examples/google_ads_batch_synthetic.json \
  --source-id sha256:e65649ef33b6c6952a36444c0e97d807a54c3263c1a5502af2aabbe9fd22c79c \
  --period-start 2026-11-01 --period-end 2026-11-07 \
  --output /tmp/paw-campaign-evidence.json
```

Use a new output path. An existing path fails with `output_exists` and is untouched.
For another source, inspect its `source_id` in the batch's report arrays and pass it
explicitly; the command never guesses a source or combines multiple campaign exports.
The expected output is also in `examples/google_ads_campaign_evidence_synthetic.json`.

Expected synthetic evidence (UAH): Alpha has 300 impressions, 5 clicks, cost 10.00,
CTR 1.666667% and CPC 2.000000; Beta has 700 impressions, 9 clicks, cost 18.00,
CTR 1.285714% and CPC 2.000000. Each has two observed days and five missing dates
(November 3–7); there is no claim those dates had zero activity. Output is 3,831
bytes versus the 27,931-byte batch, with source/row references and no raw cells.

Sums are named `observed_sum`: they cover present values in observed selected rows,
not guaranteed complete account/period totals. Inspect `present_rows`, `missing_row_ids`
and campaign `missing_days`. CTR/CPC use paired nonmissing rows and disclose their
paired sums, counts and `excluded_row_ids`. Referenced contributing rows are the
campaign's `row_ids` minus the metric's missing/excluded IDs. Empty pairs and zero
denominators produce null with `no_paired_rows` or `zero_denominator`.
Exact money strings are not rounded; ratios alone round half-even to six places.

Daily sources can be filtered explicitly, including a requested interval beyond the
export (missing dates are disclosed). Aggregate sources require the exact export
period or fail with `summary_period_mismatch`; daily coverage is not collected there.
Duplicate campaign/day rows in the selected period, or repeated campaigns in an
aggregate, fail with `duplicate_campaign_rows`. No silent deduplication/merging.
Campaigns with no in-period rows are counted as excluded, not invented as zero rows.
No in-period rows fails with `no_evidence_rows`. Source-level warnings stay under
`source.warnings`; top-level warnings describe the selected evidence. Export snapshot
time and campaign inventory remain unverified even when every date is present.

Only the selected report's consumed fields are validated. The batch hash identifies
the exact input document, and row IDs must agree with source/line references, but this
does not authenticate originals. Keep original CSVs/batch separately. Unknown selected
currency remains null, with observed codes listed; no conversion. Consumed metrics
must have <=1e15 magnitude and money <=18 effective decimal places. Missing numeric
keys, malformed/nonfinite values and invalid provenance fail with `invalid_evidence_input`.

Bounds: 20 MiB input, 100,000 source detail rows, 10,000 in-period observations,
100 campaigns, 366 days, 2 MiB output. Oversize fails, never truncates evidence.
Application entry point: `build_campaign_evidence(data, CampaignEvidenceSpec(...))`.
The CLI does not call API/Worker/model providers, modify DB state or submit data.
Keyword/query evidence, conversions analysis and AI interpretation are later slices.
See ADR-019 for arithmetic, precision and provenance decisions.

From `backend`, add `../scripts/build_google_ads_evidence.py` to Ruff checks;
`MYPYPATH=src .venv/bin/mypy ../scripts/build_google_ads_evidence.py` checks the CLI.

## M1.4 keyword/search-term evidence

From the repository root, select both synthetic sources explicitly:

```sh
backend/.venv/bin/python scripts/build_google_ads_search_evidence.py \
  --input examples/google_ads_batch_synthetic.json \
  --keyword-source-id sha256:a567c294d41c6a1c28838889dd9b183913e71a5cc2ca674a61030312437a2bdd \
  --search-term-source-id sha256:bc3336222712db92832fc70ca1643eaa93d25a0ac13b356d2c8c215d4693f028 \
  --period-start 2026-11-01 --period-end 2026-11-07 \
  --output /tmp/paw-search-evidence.json
```

Use a new path; existing output fails with `output_exists` without changing it.
The expected synthetic document is `examples/google_ads_search_evidence_synthetic.json`.
Either source flag can be omitted; the other is then required. The unselected report
is null/not collected. All selected sources must exactly match the requested period
or fail with `search_evidence_period_mismatch`; aggregate reports are never prorated.

Expected: two keyword rows and two query rows, UAH, in separate report sections.
The synthetic query details have 15 clicks / 150.00 cost; the account summary has
40 clicks / 400.00 cost. Both visible shares are 37.500000%; account minus visible
is 25 clicks / 250.00 cost. Reported visible+other reconciles to account with zero
delta. The independently synthetic keyword report has its own 15-click account
summary: do not add it to the query account or infer that the reports reconcile.

Each detail retains full keyword/query text, campaign/group, normalized match type,
close-variant flag and relevant source status. CTR/CPC use paired nonmissing values.
Repeated detail identities fail with `duplicate_search_evidence_rows`; different
query-to-keyword links remain separate. No automatic keyword/query join is performed.

For each report, `coverage` exposes observed detail sums/missing refs, account minus
visible detail and detail/account percentage for impressions/clicks/cost. Query reports
also show detail minus reported-visible summary and account minus reported-visible
minus reported-other. `reported_totals` retains every summary separately. Derived
values carry contributing row IDs, including their supporting summary rows.
These are within-report facts; matching source periods do not verify snapshot/filter
comparability or authorize cross-report totals.

Null comparisons have explicit reasons: `missing_summary`, `ambiguous_summary`,
`missing_values`, `no_visible_rows`, `zero_denominator` or `currency_unverified`.
Unavailable comparisons do not discard report rows. Summary-only query exports are
valid; absent detail is not an observed zero sum. Signed discrepancies and shares
above 100 remain visible with warnings; no cause/allocation is invented. Reported
other-term activity is not distributed among queries, keywords or campaigns.

Bounds: existing 20 MiB input, 100,000 rows/source, 1,000 combined selected detail/
summary rows, 366 days and 2 MiB output; fail instead of silently selecting top rows.
Exact Decimal sums/strings, six-place half-even ratios, provenance and source-text
handling follow ADR-019/020. Unknown currency suppresses monetary comparisons; known
mixed currencies fail. Raw cells/notes/headers are omitted; text labels remain data.
`build_search_evidence(data, SearchEvidenceSpec(...))` is the application entry point.
No API/DB/Worker/model calls occur, and evidence creation does not submit data.

For native checks from `backend`, include `../scripts/build_google_ads_search_evidence.py`
in Ruff check/format and `MYPYPATH=src .venv/bin/mypy` commands. CI includes these checks.

## One-off local AI experiment (Ministral 3 3B)

This owner-authorized experiment uses a local open-weight model, no paid API or key.
It does not implement DB history, API/Worker integration or scheduled collection.
The optional Compose project is separate from the existing PAW services/volumes:

```sh
docker compose -f infrastructure/compose.local-ai.yaml up -d --wait
docker compose -f infrastructure/compose.local-ai.yaml exec -T ollama ollama pull ministral-3:3b
docker compose -f infrastructure/compose.local-ai.yaml exec -T ollama ollama list
```

The image is digest-pinned; the adapter also requires installed model digest
`f04aa1c738f64e13c625b82ae92504fc0260fa6723b509ed1ece0fa188179b1d`.
Cloud features are disabled; only `127.0.0.1:11434` is exposed. The container receives
no advertising file mounts. Downloads need network access, generation is local.
Current resource settings: six CPUs, 6 GiB memory; one loaded model/request at a time.
On macOS Docker this is CPU inference without Metal. Model download is around 3 GB;
that is not the full RAM requirement. Weights remain in their own Docker volume.

Run a synthetic complete one-off analysis from the repository root:

```sh
backend/.venv/bin/python scripts/analyze_google_ads_once.py \
  --account-ref synthetic-account \
  --period-start 2026-11-01 --period-end 2026-11-07 \
  --source campaign_daily=examples/google_ads_campaign_daily_synthetic.csv \
  --source search_keywords=examples/google_ads_search_keywords_synthetic.csv \
  --source search_terms=examples/google_ads_search_terms_synthetic.csv \
  --model ministral-3:3b \
  --output-dir artifacts/one-off/synthetic-trial
```

Use a new directory. Add `--prepare-only` to write exact prepared facts/provenance
without invoking a model (the service need not be running). Optional `--service`
(repeatable) and `--geography` supply owner-confirmed business context; absent context
remains unknown. The fixed objective is traffic-quality review, not conversion/ROI
optimization. A supplied campaign name does not prove which services are offered.

Exactly one campaign CSV is required; select its type explicitly. Search profiles are
optional and limited to one each. Daily campaign data filters to requested dates;
aggregate periods must match. This is a self-contained package, not history merging.
All campaigns (<=20) are represented. Search details are selected by highest observed
cost, <=15 per profile, with counts of included/omitted rows. Coverage facts still use
the full local reports; selection is disclosed to the model. Full-row model input is
not enabled merely because local processing was authorized.

Output files are local/private: `prepared.json`, `request.json`, `model-response.json`,
`response-metadata.json`, `report.json` and readable `report.md`. On invalid output,
`failure.json` records a safe code; any received model answer remains available for
inspection. Default output is a fresh UUID directory under ignored `artifacts/one-off`.
Never commit real outputs. Model names/digest, runtime version, available tokens,
call ID, measured duration and prompt/payload hashes are retained. Unavailable costs
are null; no external API fee is incurred by the local provider.

One generation is performed per invocation, with no automatic retry. Current options
are temperature 0, seed 42, context 16,384, six threads and immediate unload after
generation. CLI defaults: output limit 1,800 tokens, timeout 900 seconds (max 1,800).
Structured-output/citation validation does not verify the truth of every model-written
numeric or semantic claim. The Markdown report includes calculated facts and review
limitations. A tiny model can still recommend unsupported changes: review the result.
Provenance checks identify input/reference consistency, not original CSV authenticity.

Unit tests use deterministic doubles and mocked HTTP; they never pull a model or make
paid/live calls. Add `../scripts/analyze_google_ads_once.py` to Ruff and MYPYPATH CLI
checks. The optional runtime can be stopped with:

```sh
docker compose -f infrastructure/compose.local-ai.yaml stop
```

Keep volumes to avoid re-downloading weights. See ADR-021 for scope/tradeoffs and the
distinction from the still-planned platform Data Analyst agent.

## M1.1 manual CSV check



Open [API docs](http://127.0.0.1:8000/docs). Use **Try it out** on `POST /api/v1/projects` with `{"name":"CSV practice","description":"Synthetic example"}`. Copy the returned `id`, then use `POST /api/v1/files`: enter it as `project_id`, leave delimiter as comma and select `examples/sample_campaigns.csv` from this repository. A successful upload returns HTTP 201, three data rows, column count and a SHA-256 checksum.

Use `GET /api/v1/projects/{project_id}/files` and `GET /api/v1/files/{file_id}` to retrieve metadata. Restart the API and repeat the GET: metadata and original bytes should persist. The web frontend remains the foundation shell; it has no upload controls yet. Upload does not start analysis or call an AI provider.

CSV must be UTF-8 (BOM allowed), with unique nonblank headers and consistent columns. Maximum: 10 MiB, 100,000 data rows, 200 columns, 256 characters per header and 32,768 characters per cell. Semicolon requires explicitly selecting `;`. Unsupported file media types return 415, invalid CSV returns 422, oversize returns 413 and unavailable persistence returns 503. Errors do not echo source contents. Project/file lists support `limit` (1–100) and `offset` (0–100000).

Originals use server UUID names in the dedicated `file_data` Docker volume. Database and file volumes form one installation and must be preserved together. Cleanup after failed writes is tested; recovery details and limitations are in [ADR-015](adr/ADR-015-projects-and-csv-storage.md). Download, delete, editing, runs and analysis remain unimplemented.

## Stop and recover

```sh
docker compose --env-file .env -f infrastructure/compose.yaml stop
```

Named live volumes persist. Start again with `up -d api worker web`; registration must remain unchanged. To test readiness failure manually, stop only `postgres`: `/ready` returns 503 while `/health` returns 200. Start `postgres` again and wait for readiness recovery. Do not run destructive volume-removal commands on history you intend to preserve.

## Optional n8n

See [automation/n8n/README.md](../automation/n8n/README.md). It is deliberately inactive in the default workflow. No scheduled automation, integration endpoint or AI agent is implemented yet. M1.2 Worker executes diagnostics only.


## M1.2 manual execution check

Start the stack including `worker` as shown above. In [API docs](http://127.0.0.1:8000/docs),
use `POST /api/v1/runs`. Paste an existing project UUID and generate a fresh `request_id`
with `python3 -c 'import uuid; print(uuid.uuid4())'`:

```json
{
  "project_id": "<your-project-uuid>",
  "request_id": "<new-request-uuid>",
  "task_type": "diagnostic",
  "input": {"delay_seconds": 5, "outcome": "success"}
}
```

Expect 202 and `run_id`. Query `GET /api/v1/runs/{run_id}`: it progresses from `queued`
to `running` to `completed`. The output explicitly says no analysis or AI call occurred.
`GET /api/v1/runs/{run_id}/events` shows `queued`, `started`, `completed` with UTC times
and an attempt ID. Polling may miss a brief state; persisted events retain it.
Repeat the identical POST: it returns the same ID and current status. Changing input
while reusing that request ID returns 409. A new request ID with `outcome: "failure"`
produces a terminal `failed` run with `error_code: "diagnostic_failed"`.

`correlation_id` is an optional UUID. Event pagination uses `after` (last sequence) and
`limit` (1–100). Missing runs return 404, invalid task/input returns 422 and database
unavailability returns 503 without SQL or exception details.

Run the synthetic automated smoke check with `python3 scripts/smoke_runs.py`.
It creates one synthetic project and two diagnostic runs, and requires a running Worker.
It never reads uploaded files or contacts an AI provider.

To verify restart durability manually (only while no important work is running):

1. Stop `worker` using Compose, submit a diagnostic run and confirm it stays queued.
2. Restart `api`; confirm the same run remains queued.
3. Start `worker`; confirm the run completes.
4. Submit another run with `delay_seconds: 30`. Once running, stop Worker, then start it.
   The old lease expires within approximately 15 seconds; a new attempt completes after
   its own 30-second delay. Expect `lease_expired` and a second `started` event.

The Worker does not publish a network port. Database leases use server time. Current
limits are three attempts and a 45-second absolute deadline per attempt; explicit
failures do not retry. Restarting Worker does not add duplicate lifecycle events.
`/ready` describes API database readiness, not Worker availability. While Worker is
stopped or the Mac sleeps, work may remain queued until it runs again.
See [ADR-016](adr/ADR-016-durable-diagnostic-execution.md) for guarantees and limitations.

## M1.3 manual CSV analysis

No AI credentials are required. Start `api worker web` with the current build. Upload
`examples/sample_campaigns.csv` as in M1.1, then use `POST /api/v1/runs` in API docs.
Select the `csv_analysis` request variant and supply the project/file IDs returned by
those operations, plus a new request UUID:

```json
{
  "project_id": "<your-project-uuid>",
  "request_id": "<new-request-uuid>",
  "task_type": "csv_analysis",
  "input": {
    "file_id": "<uploaded-file-uuid>",
    "numeric_columns": ["impressions", "clicks", "cost"],
    "group_by": "campaign",
    "chart_column": "cost",
    "ratios": [
      {"name": "CTR", "numerator": "clicks", "denominator": "impressions", "scale": 100},
      {"name": "CPC", "numerator": "cost", "denominator": "clicks", "scale": 1}
    ]
  }
}
```

Expect 202 and a run ID. Poll `GET /api/v1/runs/{run_id}` until completed; its `output`
contains `report_artifact_id` and `chart_artifact_id`. Download each using
`GET /api/v1/artifacts/{artifact_id}`: report is JSON, chart is PNG. Open the PNG in a
normal image viewer. A completed analysis means deterministic calculation only, not
AI interpretation. The web frontend still has no upload/results controls.

Expected sample totals: impressions 3500, clicks 130, cost 53. Synthetic Search totals
are 1500/70/35, CTR approximately 4.666667%, CPC 0.5. Synthetic Social totals are
2000/60/18, CTR 3%, CPC 0.3. The chart plots grouped cost: 35 and 18.

For a generic CSV, select 1–8 numeric columns explicitly and one of them as the chart
column. `group_by` is optional; omitting it gives one aggregate over all rows. Ratios
are optional. Empty/whitespace values are missing; invalid numeric strings fail the
run. All-missing sums and ratios with zero denominator return null. Reports retain
up to 100 groups; the chart shows at most 30, explicitly disclosed. See
[ADR-017](adr/ADR-017-deterministic-analysis-and-artifacts.md) for all semantics/limits.

Repeat an identical request UUID/input to get the same run; use a new UUID for a new
analysis. A missing column produces `failed/unknown_column`. A file from a different
project is rejected with 404 before enqueue. API input errors return 422. Dataset
contents, column values and filesystem paths are not included in error messages.

Run `python3 scripts/smoke_analysis.py` for synthetic upload/calculation/download checks.
It creates a synthetic project and run without reading private sources. Restart API and
Worker, then repeat the artifact GETs: downloads remain available with the same IDs.
Originals and artifacts live in distinct `file_data` and `artifact_data` volumes;
preserve both alongside PostgreSQL. Never reset volumes casually.

Native Matplotlib checks may use `MPLCONFIGDIR=/tmp/paw-matplotlib` to keep font caches
in a writable directory. Container builds set this automatically. The Linux child has
30-second wall-clock, 25-second CPU and 2 GiB virtual-memory bounds; failed/interrupted
attempts cannot overwrite already published artifacts.
