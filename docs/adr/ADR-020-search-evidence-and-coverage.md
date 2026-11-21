# ADR-020 — Keyword/query evidence and within-report coverage

Status: Accepted, 2026-11-21. Scope: M1.4 offline evidence, no provider/API integration.

## Decision

Select at most one keyword and one search-term source explicitly from schema-v1 batch
JSON. At least one is required; an unselected profile is null/not collected. Each
selected export must exactly match the requested period (<=366 days). These aggregate
reports cannot be cropped/prorated; matching periods do not prove matching export
snapshots/account filters. Account remains owner asserted, source identities unverified.

Retain all selected detail rows, including zero activity, with campaign/group, full
keyword/query, match type/close-variant flag and source status. Never join query strings
to keyword reports or infer missing links. Per-row CTR/CPC use the existing paired
nonmissing arithmetic and six-place half-even rounding. Exact Decimal money remains
strings. Conversions/relevance evaluation are outside this slice.

Repeated campaign/group/keyword/match identities fail before detail arithmetic. Query
identities additionally include query and close-variant flag. Different keyword links
remain distinct. Source/physical-line references are checked jointly across details
and summaries so summary references cannot alias detail rows. Checks do not authenticate
original CSV bytes. Shared internal JSON validation/metric helpers preserve campaign
evidence behavior; its checked-in artifact remains byte-identical.

## Coverage facts, not invented attribution

Compute each report independently. Preserve every supplied summary (label, row ID,
counts/cost/currency) separately; never sum duplicate/overlapping summary categories.
Known account label is `Усього: Обліковий запис`; search-term visible/other labels are
`Усього: Пошукові терміни` and `Усього: Інші пошукові терміни`.

For impressions/clicks/cost, expose observed detail sums and missing references, account
minus detail, and detail/account percentage. For queries also expose detail minus the
reported visible summary, and account minus reported visible minus reported other.
Each derived value carries all contributing row IDs. Reported other-term activity
remains its own source fact; account-minus-detail is not automatically attributed to it.

Coverage arithmetic needs complete contributing values and exactly one summary for
each required label. Missing or ambiguous summaries/values produce null with explicit
reasons; rows and unaffected comparisons remain available. No visible rows means
observed sum/derived detail coverage is unknown, not invented zero. Summary-only query
reports can still reconcile their reported totals. Zero denominators yield null.
Signed deltas and percentages over 100 are retained with discrepancy warnings, not
clamped, hidden, assigned a cause or automatically rejected. Unknown currency suppresses
money comparisons; known mixed currencies across selected data fail without conversion.

## Limits and boundary

Existing 20 MiB batch input; <=100,000 rows per source; <=1,000 combined selected
detail/summary rows; 2 MiB encoded output. Fail rather than truncate entities or
references. Original cells/notes/headers are omitted, but included query/keyword/source
labels remain untrusted data. Keep exact batch hash, source IDs, actual periods and
source warnings separate from calculated warnings. No cross-report total or join.

The CLI creates a new file exclusively and never submits it to a provider. No database,
Worker, runtime lifecycle events or new dependencies. Durable platform ingestion/run
integration remains M1.4 work; M1.5 still requires explicit provider/data-sharing/budget
decisions and business context for relevance recommendations.
