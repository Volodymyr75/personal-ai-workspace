"""Fixed campaign calculations on validated, explicitly selected observations."""

from collections import defaultdict
from datetime import timedelta
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from typing import Literal

from paw.domain.files import InputError
from paw.domain.google_ads_evidence import (
    CampaignEvidence,
    CampaignEvidenceSpec,
    CampaignObservation,
    MetricEvidence,
    RatioEvidence,
)

MAX_EVIDENCE_ROWS = 10_000
MAX_EVIDENCE_CAMPAIGNS = 100
MAX_EVIDENCE_DAYS = 366


def metric_evidence(
    rows: list[CampaignObservation], field: Literal["impressions", "clicks", "cost"]
) -> MetricEvidence:
    values: list[int | Decimal] = []
    missing = []
    for row in rows:
        value: int | Decimal | None = getattr(row, field)
        if value is None:
            missing.append(row.row_id)
        else:
            values.append(value)
    return MetricEvidence(sum(values) if values else None, len(values), tuple(missing))


def ratio_evidence(
    rows: list[CampaignObservation],
    numerator: Literal["clicks", "cost"],
    denominator: Literal["impressions", "clicks"],
    scale: int,
) -> RatioEvidence:
    pairs = [
        r for r in rows if getattr(r, numerator) is not None and getattr(r, denominator) is not None
    ]
    excluded = tuple(
        r.row_id for r in rows if getattr(r, numerator) is None or getattr(r, denominator) is None
    )
    if not pairs:
        return RatioEvidence(None, None, None, 0, excluded, "no_paired_rows")
    n = metric_evidence(pairs, numerator).observed_sum
    d = metric_evidence(pairs, denominator).observed_sum
    assert n is not None and d is not None
    if d == 0:
        return RatioEvidence(None, n, d, len(pairs), excluded, "zero_denominator")
    value = (Decimal(n) / Decimal(d) * scale).quantize(
        Decimal("0.000001"), rounding=ROUND_HALF_EVEN
    )
    return RatioEvidence(value, n, d, len(pairs), excluded, None)


def summarize_campaigns(
    rows: tuple[CampaignObservation, ...], spec: CampaignEvidenceSpec, *, daily: bool
) -> tuple[CampaignEvidence, ...]:
    """All sums cover supplied observed rows; absent days are never zero-filled."""
    days = (spec.period_end - spec.period_start).days + 1
    if not 1 <= days <= MAX_EVIDENCE_DAYS:
        raise InputError("invalid_evidence_period")
    if not rows:
        raise InputError("no_evidence_rows")
    if len(rows) > MAX_EVIDENCE_ROWS:
        raise InputError("too_many_evidence_rows")
    groups: dict[str, list[CampaignObservation]] = defaultdict(list)
    seen: set[tuple[str, object]] = set()
    for row in rows:
        key = (row.campaign, row.day if daily else None)
        if key in seen:
            raise InputError("duplicate_campaign_rows")
        seen.add(key)
        groups[row.campaign].append(row)
    if len(groups) > MAX_EVIDENCE_CAMPAIGNS:
        raise InputError("too_many_evidence_campaigns")
    expected_days = {spec.period_start + timedelta(days=i) for i in range(days)}
    output = []
    # Bounded input decimals have <=18 places and <=1e15 magnitude. 64 digits
    # preserve their sums exactly; ratios alone are rounded to six places.
    with localcontext() as context:
        context.prec = 64
        for campaign, selected in sorted(groups.items()):
            observed_days = {r.day for r in selected if r.day is not None}
            output.append(
                CampaignEvidence(
                    campaign=campaign,
                    row_ids=tuple(r.row_id for r in selected),
                    impressions=metric_evidence(selected, "impressions"),
                    clicks=metric_evidence(selected, "clicks"),
                    cost=metric_evidence(selected, "cost"),
                    ctr_percent=ratio_evidence(selected, "clicks", "impressions", 100),
                    cpc=ratio_evidence(selected, "cost", "clicks", 1),
                    observed_day_count=len(observed_days) if daily else None,
                    missing_days=tuple(sorted(expected_days - observed_days)) if daily else None,
                )
            )
    return tuple(output)
