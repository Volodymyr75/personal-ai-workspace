"""Campaign evidence contracts; no framework or provider dependencies."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

from paw.domain.google_ads import MatchType


@dataclass(frozen=True)
class CampaignEvidenceSpec:
    source_id: str
    period_start: date
    period_end: date


@dataclass(frozen=True)
class CampaignObservation:
    row_id: str
    campaign: str
    day: date | None
    impressions: int | None
    clicks: int | None
    cost: Decimal | None
    currency: str | None


@dataclass(frozen=True)
class MetricEvidence:
    observed_sum: int | Decimal | None
    present_rows: int
    missing_row_ids: tuple[str, ...]


@dataclass(frozen=True)
class RatioEvidence:
    value: Decimal | None
    numerator_sum: int | Decimal | None
    denominator_sum: int | Decimal | None
    paired_rows: int
    excluded_row_ids: tuple[str, ...]
    unavailable_reason: Literal["no_paired_rows", "zero_denominator"] | None


@dataclass(frozen=True)
class CampaignEvidence:
    campaign: str
    row_ids: tuple[str, ...]
    impressions: MetricEvidence
    clicks: MetricEvidence
    cost: MetricEvidence
    ctr_percent: RatioEvidence
    cpc: RatioEvidence
    observed_day_count: int | None
    missing_days: tuple[date, ...] | None


@dataclass(frozen=True)
class SearchEvidenceSpec:
    period_start: date
    period_end: date
    keyword_source_id: str | None = None
    search_term_source_id: str | None = None


@dataclass(frozen=True)
class SearchObservation:
    metrics: CampaignObservation
    ad_group: str
    keyword: str | None
    search_term: str | None
    match_type: MatchType
    match_type_text: str | None
    close_variant: bool | None
    keyword_status: str | None
    added_or_excluded: str | None


@dataclass(frozen=True)
class SearchSummary:
    label: str
    metrics: CampaignObservation


@dataclass(frozen=True)
class DerivedEvidence:
    value: int | Decimal | None
    row_ids: tuple[str, ...]
    unavailable_reason: str | None = None
