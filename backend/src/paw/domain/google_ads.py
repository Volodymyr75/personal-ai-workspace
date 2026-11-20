"""Framework-independent contracts for the first, single-report import slice."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

ReportType = Literal["campaign_summary", "campaign_daily", "search_keywords", "search_terms"]
MatchType = Literal["exact", "phrase", "broad"]


@dataclass(frozen=True)
class GoogleAdsRow:
    # Physical source lines are inclusive, including quoted multiline records.
    line_start: int
    line_end: int
    raw_cells: tuple[str, ...]
    # Summary rows may have no campaign; never use their label as an identity.
    campaign: str | None
    impressions: int | None
    clicks: int | None
    cost: Decimal | None
    currency: str | None
    conversions: Decimal | None
    ctr_percent: Decimal | None
    average_cpc: Decimal | None
    summary_label: str | None = None
    day: date | None = None
    keyword: str | None = None
    ad_group: str | None = None
    match_type: MatchType | None = None
    keyword_status: str | None = None
    search_term: str | None = None
    match_type_text: str | None = None
    close_variant: bool | None = None
    added_or_excluded: str | None = None


@dataclass(frozen=True)
class GoogleAdsReport:
    source_sha256: str
    source_size_bytes: int
    title: str
    period_text: str
    period_start: date
    period_end: date
    headers: tuple[str, ...]
    delimiter: str
    currency: str | None
    details: tuple[GoogleAdsRow, ...]
    totals: tuple[GoogleAdsRow, ...]
    # Never infer identity from report title, campaign names or currency.
    account_id: None = None
    report_type: ReportType = "campaign_summary"
    warnings: tuple[str, ...] = ("account_scope_unverified", "coverage_unverified")


@dataclass(frozen=True)
class GoogleAdsCsvSource:
    name: str
    report_type: ReportType
    data: bytes
    delimiter: str = ","


@dataclass(frozen=True)
class GoogleAdsBatchSpec:
    batch_id: UUID
    # Local owner-supplied account reference, not an inferred Google Ads ID.
    account_ref: str
    period_start: date
    period_end: date
