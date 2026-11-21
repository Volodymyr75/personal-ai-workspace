# ADR-019 — Bounded campaign evidence from a selected JSON source

Status: Accepted, 2026-11-21. Scope: M1.4 local deterministic evidence, no AI/API changes.

## Decision

Consume schema-v1 batch JSON with an explicit campaign `source_id` and requested
inclusive period. Select exactly one campaign summary or daily report. Other sources,
CSV summary rows, keyword/search-term rows and their metrics never enter arithmetic.
JSON validation covers the envelope and consumed selected-source fields, not full
revalidation of ignored reports. Reject malformed JSON, duplicate keys, invalid counts,
nonfinite/unsupported decimals, broken row references and non-campaign sources.

Daily evidence explicitly selects rows by date, retaining excluded-row counts. A period
may extend beyond the export; missing dates remain disclosed, not zero-filled. Summary
evidence requires an exact whole-period match: no prorating. A campaign with no selected
rows is not fabricated as zero activity; disclose the excluded campaign count. No
selected rows fails with `no_evidence_rows`. Repeated campaign/day keys (or repeated
campaign names in an aggregate) fail before summation. Campaign names remain unverified
source identities; grouping does not prove stable external identity or account coverage.

Per campaign, retain row IDs, observed sums for impressions/clicks/cost, present-row
counts and missing-row references. All-missing sums are null; partial sums describe
observed values only. CTR is paired sum(clicks)/sum(impressions)*100; CPC is paired
sum(cost)/sum(clicks). Disclose paired rows, excluded row IDs and paired numerator/
denominator sums. Empty pairs and zero denominators return null with distinct reasons.
Every result is traceable to the parent row IDs minus its missing/excluded row IDs.

Money remains exact Decimal, serialized as a plain decimal string. Consumed values
have at most 18 effective decimal places and 1e15 magnitude; support the uppercase
scientific notation emitted by the batch Decimal serializer. A local precision of 64
preserves bounded sums independent of ambient context. Ratios alone round to six places
using half-even. Counts remain integers. Mixed selected-row currencies fail; missing
currency makes output currency null, never defaults to UAH. Known codes remain listed.

Daily coverage counts observed dates and lists missing requested dates per campaign.
Summary daily coverage is null/not collected. Present dates do not prove final Google
statistics: export snapshot time and inventory completeness remain unverified. Keep
whole-source warnings separately from selected-evidence warnings; a duplicate/unknown
currency in excluded data must not mislabel the chosen calculation.

Limits: existing 20 MiB batch input, 100,000 selected-source input rows, at most 10,000
in-period observations, 100 campaigns, 366 requested days and 2 MiB encoded evidence.
Oversize results fail instead of silently dropping references or campaigns. The CLI
reads bounded input and creates a new output exclusively. Evidence includes a hash of
its exact batch input and source/line references, not raw cells, full headers or notes.
Reference consistency does not authenticate the original CSV bytes; retain originals
and batch together. Included campaign/account labels remain untrusted source text.

## Alternatives and next boundary

Auto-selecting/combining exports risks double-counting snapshots and grains. Averaging
row-level rates or treating missing values as zero hides coverage and changes answers.
Explicit selection, paired arithmetic and missingness references make limits inspectable.

This slice calculates campaign evidence only. No overall-account total, conversions
ranking, inter-period comparison, keyword/query evidence, provider invocation, automatic
collection, database writes, migrations or runtime lifecycle events. Evidence creation
does not authorize model submission; provider/data-sharing/budget choices remain M1.5.
