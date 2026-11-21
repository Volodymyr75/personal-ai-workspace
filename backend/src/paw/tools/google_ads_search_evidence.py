"""Fixed search-row metrics and within-report coverage; no joins or allocation."""

from dataclasses import asdict
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from typing import Literal

from paw.domain.files import InputError
from paw.domain.google_ads_evidence import (
    CampaignObservation,
    DerivedEvidence,
    SearchObservation,
    SearchSummary,
)
from paw.tools.google_ads_evidence import metric_evidence, ratio_evidence

MAX_SEARCH_EVIDENCE_ROWS = 1000
_ACCOUNT = "Усього: Обліковий запис"
_VISIBLE = "Усього: Пошукові терміни"
_OTHER = "Усього: Інші пошукові терміни"
Metric = Literal["impressions", "clicks", "cost"]


def _derived(
    rows: list[CampaignObservation],
    metric: Metric,
    *,
    signs: tuple[int, ...],
    percent: bool = False,
) -> DerivedEvidence:
    values: list[int | Decimal] = []
    for row in rows:
        value: int | Decimal | None = getattr(row, metric)
        if value is None:
            return DerivedEvidence(None, (), "missing_values")
        values.append(value)
    if metric == "cost" and any(row.currency is None for row in rows):
        return DerivedEvidence(None, (), "currency_unverified")
    if percent:
        denominator = values[-1]
        if denominator == 0:
            return DerivedEvidence(None, (), "zero_denominator")
        value = (Decimal(sum(values[:-1])) / Decimal(denominator) * 100).quantize(
            Decimal("0.000001"), rounding=ROUND_HALF_EVEN
        )
    else:
        value = sum(v * s for v, s in zip(values, signs, strict=True))
    return DerivedEvidence(value, tuple(row.row_id for row in rows))


def _comparison(
    details: list[CampaignObservation],
    totals: list[SearchSummary],
    labels: tuple[str, ...],
    metric: Metric,
    *,
    include_details: bool,
    percent: bool = False,
) -> DerivedEvidence:
    selected: list[CampaignObservation] = []
    for label in labels:
        matches = [s.metrics for s in totals if s.label == label]
        if len(matches) != 1:
            reason = "missing_summary" if not matches else "ambiguous_summary"
            return DerivedEvidence(None, (), reason)
        selected += matches
    if include_details:
        if not details:
            # Absence of disclosed rows is not proof of an observed zero sum.
            return DerivedEvidence(None, (), "no_visible_rows")
        if percent:
            return _derived(details + selected, metric, signs=(), percent=True)
        # Difference is account minus disclosed rows, or disclosed rows minus visible summary.
        if labels == (_ACCOUNT,):
            return _derived(selected + details, metric, signs=(1,) + (-1,) * len(details))
        return _derived(details + selected, metric, signs=(1,) * len(details) + (-1,))
    return _derived(selected, metric, signs=(1,) + (-1,) * (len(selected) - 1))


def summarize_search(
    rows: tuple[SearchObservation, ...], totals: tuple[SearchSummary, ...], *, terms: bool
) -> tuple[dict[str, object], tuple[str, ...]]:
    """All rows are retained; missing/ambiguous coverage remains unknown, not an error."""
    if len(rows) + len(totals) > MAX_SEARCH_EVIDENCE_ROWS:
        raise InputError("too_many_search_evidence_rows")
    if not rows and not totals:
        raise InputError("no_evidence_rows")
    warnings = {"inventory_unverified", "export_snapshot_time_not_collected"}
    seen: set[tuple[object, ...]] = set()
    for row in rows:
        key: tuple[object, ...] = (row.metrics.campaign, row.ad_group, row.keyword, row.match_type)
        if terms:
            key += (row.search_term, row.close_variant)
        if key in seen:
            raise InputError("duplicate_search_evidence_rows")
        seen.add(key)
        if terms and row.keyword is None:
            warnings.add("keyword_link_unavailable")
    metrics = [r.metrics for r in rows]
    entries: list[dict[str, object]] = []
    coverage: dict[str, object] = {}
    with localcontext() as context:
        context.prec = 64
        for row in rows:
            entries.append(
                {
                    "row_id": row.metrics.row_id,
                    "campaign": row.metrics.campaign,
                    "ad_group": row.ad_group,
                    "keyword": row.keyword,
                    "search_term": row.search_term,
                    "match_type": row.match_type,
                    "match_type_text": row.match_type_text,
                    "close_variant": row.close_variant,
                    "keyword_status": row.keyword_status,
                    "added_or_excluded": row.added_or_excluded,
                    "currency": row.metrics.currency,
                    "impressions": row.metrics.impressions,
                    "clicks": row.metrics.clicks,
                    "cost": row.metrics.cost,
                    "ctr_percent": asdict(
                        ratio_evidence([row.metrics], "clicks", "impressions", 100)
                    ),
                    "cpc": asdict(ratio_evidence([row.metrics], "cost", "clicks", 1)),
                }
            )
        for metric in ("impressions", "clicks", "cost"):
            total_list = list(totals)
            remainder = _comparison(metrics, total_list, (_ACCOUNT,), metric, include_details=True)
            share = _comparison(
                metrics, total_list, (_ACCOUNT,), metric, include_details=True, percent=True
            )
            values = {
                "observed_detail": asdict(metric_evidence(metrics, metric)),
                "account_minus_visible_detail": asdict(remainder),
                "visible_detail_share_percent": asdict(share),
            }
            derived = [remainder, share]
            if terms:
                visible_delta = _comparison(
                    metrics, total_list, (_VISIBLE,), metric, include_details=True
                )
                reconciliation = _comparison(
                    metrics, total_list, (_ACCOUNT, _VISIBLE, _OTHER), metric, include_details=False
                )
                values.update(
                    {
                        "visible_detail_minus_reported_visible": asdict(visible_delta),
                        "reported_account_minus_visible_minus_other": asdict(reconciliation),
                    }
                )
                derived += [visible_delta, reconciliation]
                if visible_delta.value is not None and visible_delta.value != 0:
                    warnings.add("visible_summary_discrepancy")
                if reconciliation.value is not None and reconciliation.value != 0:
                    warnings.add("reported_totals_discrepancy")
            if remainder.value is not None and remainder.value < 0:
                warnings.add("detail_exceeds_account_total")
            for value in derived:
                if value.unavailable_reason:
                    warnings.add("coverage_" + value.unavailable_reason)
            coverage[metric] = values
    reported = [
        {
            "summary_label": t.label,
            "row_id": t.metrics.row_id,
            "currency": t.metrics.currency,
            "impressions": t.metrics.impressions,
            "clicks": t.metrics.clicks,
            "cost": t.metrics.cost,
        }
        for t in totals
    ]
    document: dict[str, object] = {
        "rows": entries,
        "detail_row_ids": [row.row_id for row in metrics],
        "reported_totals": reported,
        "coverage": coverage,
    }
    return document, tuple(sorted(warnings))
