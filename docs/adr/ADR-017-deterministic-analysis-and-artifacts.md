# ADR-017 — Bounded CSV analysis and fenced artifact publication

Status: Accepted, 2026-11-20. Scope: M1.3; no AI or frontend changes.

## Inputs and calculations

Add `csv_analysis` alongside the existing `diagnostic` request. Its typed input names
one stored CSV in the same project, 1–8 unique numeric columns, an optional distinct
group column, one numeric chart column and up to four named ratios. Ratios name selected
numerator/denominator columns and a scale of 1 or 100. No formulas, expressions, generated
code, automatic column selection or natural-language interpretation are accepted.
Required request UUID and existing diagnostic semantics remain unchanged.

Use the standard CSV parser with the M1.1 limits, then Pandas for fixed statistics:
count, missing, sum, mean, median, min, max, and group sums. Preserve original headers
and nonblank group values. Empty/whitespace-only cells are missing. Numeric conversion
rejects invalid/nonfinite values, including formula strings; no coercion that hides
bad values. Each input magnitude is at most 1e15; arithmetic uses Float64 and is not an
exact decimal accounting engine. Nonfinite aggregates fail rather than serialize NaN.
All-missing sums/statistics are null. Negative numbers are allowed for generic datasets.
Only explicitly selected columns are typed numeric; other columns remain text.

Ratios use **paired nonmissing rows**, sum numerator and denominator separately, then
divide and scale. Record paired/excluded row counts. Empty pairs or zero denominators
produce null, never zero or Infinity. CTR therefore uses sum(clicks)/sum(impressions)*100;
CPC uses sum(cost)/sum(clicks), not averages of row-level ratios.

Keep a missing group as null, distinct from literal group names. Reject more than 100
groups rather than silently omit report data. The report includes all accepted groups.
The PNG plots the first 30 in sorted label order (missing last), shortens displayed
labels to 40 characters and discloses these presentation limits. Report labels remain
complete. All-missing bars are marked N/A. Matplotlib creates a static PNG, with user
label math parsing disabled; no script/HTML renderer or external plotting service.

References: [Pandas numeric conversion](https://pandas.pydata.org/pandas-docs/stable/generated/pandas.to_numeric.html),
[Matplotlib savefig](https://matplotlib.org/stable/api/_as_gen/matplotlib.figure.Figure.savefig.html).
Pinned tested versions are in the lockfile; no provider SDK is introduced.

## Execution and failures

The Worker reads at most 10 MiB through a read-only source mount and verifies the saved
SHA-256. A spawned child runs only the fixed calculation function, receives bytes and
typed inputs, and has no database handles or artifact-writing responsibility. The parent
maintains existing 3-second heartbeats and checks ownership again before publication.
It terminates the child on shutdown, lost ownership or a 30-second calculation timeout.
Linux child limits are 2 GiB virtual memory and 25 CPU seconds; the container is the
supported runtime for those limits. The existing 45-second attempt deadline remains.
This is a bounded trusted-code process, not a sandbox for arbitrary user code.

Expected failures use stable codes: `unknown_column`, `invalid_numeric`, `numeric_overflow`,
`too_many_groups`, `source_unavailable`, `source_changed`, `analysis_timeout`,
`artifact_too_large`, `analysis_failed`. They finish the run as failed without publishing
artifacts; event details contain no private column names or values. Storage/database
failure leaves the attempt recoverable through lease expiry and bounded retry.
No placeholder agent registration, model call, usage/cost value or AI interpretation.

## Atomic publication and recovery

Persist bounded JSON report and PNG bytes (each at most 2 MiB) in a separate local
`artifact_data` volume through the existing UUID blob adapter, using `.bin` keys.
Metadata retains run/attempt IDs, kind, MIME, byte size, hash and UTC creation time.
The source reference belongs to the run. Output contains artifact IDs, not disk paths.

Acquire the run row lock, verify current attempt/lease/deadline, acquire a separate
artifact publication advisory lock and recheck ownership. Write/fsync both blobs, insert
both metadata rows, recheck ownership after the blob writes, mark completed and append
the event in one database transaction. Expiry during writes rolls back publication.
Until commit, downloads cannot see either artifact. Unique `(run_id, kind)` prevents
multiple published reports/charts; expired/duplicate publication returns without writes.

Filesystem and database still do not share an atomic transaction. Under the artifact
lock, reconciliation removes UUID blobs not referenced by committed metadata and `.part`
files. Reconcile at startup, before publication and after a failed publication. If DB
state is unavailable, defer cleanup; never blindly delete after an ambiguous commit.
A process crash can temporarily leave invisible orphans. Unknown filenames are untouched.
Source and artifact directories are distinct; artifact cleanup never visits source files.

Downloads join completed runs and current attempt IDs, verify size/hash, and use fixed
attachment filenames, no-store and nosniff headers. API and Worker share artifact storage;
only API writes source storage. Preserve database, original-file and artifact volumes
as one installation when backing up/restoring. Backups remain separately scoped work.

## Alternatives and next boundary

Storing results inline in PostgreSQL would avoid compensation but diverge from the
existing volume-backed artifact direction. Shared temporary result filenames would let
stale attempts overwrite newer outputs. The bounded in-memory child result plus fenced
UUID publication keeps these risks local without a broker or object-storage service.
No generic tool/plugin engine or additional microservice is needed. M1.4 can interpret
these verified results through a provider adapter; tool-call tracing/usage arrives with
that agent integration, not fabricated events in this fixed deterministic pipeline.
