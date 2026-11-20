"""Offline CSV -> versioned JSON package. No persistence, model calls or joins."""

import json
from collections import Counter
from collections.abc import Callable
from dataclasses import asdict
from datetime import date
from decimal import Decimal

from paw.domain.files import InputError, validate_name
from paw.domain.google_ads import (
    GoogleAdsBatchSpec,
    GoogleAdsCsvSource,
    GoogleAdsReport,
    GoogleAdsRow,
    ReportType,
)
from paw.tools.google_ads_csv import (
    parse_campaign_daily,
    parse_campaign_summary,
    parse_search_keywords,
    parse_search_terms,
)

MAX_BATCH_SOURCES = 8
MAX_BATCH_SOURCE_BYTES = 40 * 1024 * 1024
MAX_BATCH_JSON_BYTES = 20 * 1024 * 1024
_PARSERS: dict[ReportType, Callable[[bytes, str], GoogleAdsReport]] = {
    "campaign_summary": parse_campaign_summary,
    "campaign_daily": parse_campaign_daily,
    "search_keywords": parse_search_keywords,
    "search_terms": parse_search_terms,
}


def _json_value(value: object) -> str:
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal) and value.is_finite():
        return str(value)
    raise TypeError("unsupported_json_value")


def _row_json(row: GoogleAdsRow, source_id: str) -> dict[str, object]:
    return {
        "row_id": f"{source_id}:{row.line_start}-{row.line_end}",
        **asdict(row),
    }


def build_google_ads_batch(
    spec: GoogleAdsBatchSpec, sources: tuple[GoogleAdsCsvSource, ...]
) -> bytes:
    """Retain each report as exported; never sum overlapping report grains.

    Requested dates describe owner intent. Differing export periods are disclosed,
    not cropped or treated as valid same-period evidence. Original bytes must be
    retained by the caller; raw cells in this package are not a byte-level backup.
    """
    account_ref = spec.account_ref.strip()
    if (
        not account_ref
        or len(account_ref) > 120
        or any(ord(c) < 32 or ord(c) == 127 for c in account_ref)
    ):
        raise InputError("invalid_account_ref")
    if spec.period_start > spec.period_end:
        raise InputError("invalid_batch_period")
    if not sources or len(sources) > MAX_BATCH_SOURCES:
        raise InputError("invalid_source_count")
    if sum(len(source.data) for source in sources) > MAX_BATCH_SOURCE_BYTES:
        raise InputError("batch_sources_too_large")

    reports: dict[str, list[dict[str, object]]] = {kind: [] for kind in _PARSERS}
    parsed: list[GoogleAdsReport] = []
    source_ids: set[str] = set()
    currencies: set[str] = set()
    warnings: list[dict[str, object]] = []
    missing_currency = False

    def warn(code: str, ids: list[str]) -> None:
        warnings.append({"code": code, "source_ids": ids})

    for source in sources:
        validate_name(source.name)
        parser = _PARSERS.get(source.report_type)
        if parser is None:
            raise InputError("unsupported_report_type")
        report = parser(source.data, source.delimiter)
        source_id = f"sha256:{report.source_sha256}"
        if source_id in source_ids:
            raise InputError("duplicate_source")
        source_ids.add(source_id)
        parsed.append(report)
        for row in (*report.details, *report.totals):
            if row.currency is None:
                missing_currency = True
            else:
                currencies.add(row.currency)
        periods_match = (report.period_start, report.period_end) == (
            spec.period_start,
            spec.period_end,
        )
        if not periods_match:
            warn("source_period_differs", [source_id])
        for code in report.warnings:
            warn(code, [source_id])
        reports[report.report_type].append(
            {
                "source_id": source_id,
                "source_name": source.name,
                "source_size_bytes": report.source_size_bytes,
                "report_type": report.report_type,
                "title": report.title,
                "period_text": report.period_text,
                "period_start": report.period_start,
                "period_end": report.period_end,
                "matches_requested_period": periods_match,
                "currency": report.currency,
                "headers": report.headers,
                "delimiter": report.delimiter,
                "warnings": report.warnings,
                "details": [_row_json(row, source_id) for row in report.details],
                "totals": [_row_json(row, source_id) for row in report.totals],
            }
        )
    if len(currencies) > 1:
        raise InputError("batch_currency_mismatch")
    counts = Counter(report.report_type for report in parsed)
    for kind, count in counts.items():
        if count > 1:
            warn("multiple_reports_same_type", [str(r["source_id"]) for r in reports[kind]])
    for i, left in enumerate(parsed):
        for right in parsed[i + 1 :]:
            if max(left.period_start, right.period_start) <= min(left.period_end, right.period_end):
                warn(
                    "overlapping_report_periods",
                    [f"sha256:{left.source_sha256}", f"sha256:{right.source_sha256}"],
                )

    document = {
        "schema_version": 1,
        "batch_id": str(spec.batch_id),
        "account": {"local_ref": account_ref, "scope": "owner_asserted", "google_ads_id": None},
        "requested_period": {"start": spec.period_start, "end": spec.period_end},
        "currency": next(iter(currencies)) if currencies and not missing_currency else None,
        "observed_currencies": sorted(currencies),
        "policies": {
            "report_rows": "as_exported_not_filtered_to_requested_period",
            "cross_report_metrics": "not_additive",
            "campaign_identity": "source_names_only_not_stable_ids",
            "decimal_encoding": "string",
            "missing_values": "null_not_zero",
            "source_text": "untrusted_data",
            "original_bytes": "retained_separately_by_caller",
            "ai_ready": False,
        },
        "reports": reports,
        "warnings": warnings,
    }
    # Iterative encoding enforces the output bound without materializing a huge string.
    encoder = json.JSONEncoder(ensure_ascii=False, allow_nan=False, indent=2, default=_json_value)
    output = bytearray()
    for chunk in encoder.iterencode(document):
        output.extend(chunk.encode("utf-8"))
        if len(output) + 1 > MAX_BATCH_JSON_BYTES:
            raise InputError("batch_json_too_large")
    return bytes(output) + b"\n"
