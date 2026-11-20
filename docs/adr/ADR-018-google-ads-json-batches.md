# ADR-018 — Local Google Ads JSON batches

Status: Accepted, 2026-11-20. Scope: M1.4 offline assembly, without API/storage changes.

## Decision

Build a UTF-8 JSON package (`schema_version: 1`) from explicitly typed CSV sources
using the four supported Ukrainian parsers. Caller supplies batch UUID, local account
reference and requested period. Account scope is **owner asserted**, not verified
against Google Ads; campaign/group names are source labels, not stable external IDs.

Keep separate report arrays by profile, including multiple distinct exports of a
profile. Each report retains actual period/title, source name, SHA-256-based source ID,
size, delimiter, headers, normalized detail/totals and original cells/physical lines.
Row references combine source hash and line range. Original bytes remain separately
owned by the caller; raw parsed cells cannot reproduce a byte-identical original.

Requested period describes intent. Different source periods warn without cropping,
prorating, merging or pretending the exports form same-period evidence. Overlapping
periods and multiple reports of one profile warn. No cross-report sum, join, canonical
campaign total or duplicate-row resolution is performed. Exact byte-identical sources
are rejected even under different filenames; distinct snapshots remain visible.

Preserve incomplete coverage, summary-only search terms, other-term totals and
source parser warnings without inventing allocation. Mixed observed currencies fail;
no currency conversion or default. `observed_currencies` lists known values while
batch `currency` is null if any row lacks currency. Decimal values serialize as exact
strings; counts are integers, dates ISO strings, missing values null.

Bounds: 1–8 files, existing per-file limits, 40 MiB combined source bytes, 20 MiB
encoded JSON including trailing newline. Fail without a partial returned document.
The CLI reads bounded files and creates a new output path exclusively, never overwrites.
No database writes, lifecycle events, model calls or credentials. This full local
package contains untrusted source text and is explicitly `ai_ready: false`; a later
bounded evidence projection must select/compute data before model submission.

## Alternatives and consequences

A flattened CSV would mix report grains and lose nested provenance/coverage. Rejecting
every period or coverage difference would discard useful data; silently reconciling
would invent facts. JSON preserves structure and limitations for later calculations.
Decimal strings require consumers to parse decimal arithmetic explicitly.

This does not complete durable batch upload, account verification, automatic collection,
cross-report reconciliation, evidence calculations or M1.5 AI interpretation. Those
remain separately scoped work using existing API ownership and Worker fencing.
