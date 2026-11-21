"""Selected keyword/query JSON evidence, preserving within-report coverage facts."""

import json
import re
from hashlib import sha256
from uuid import UUID

from paw.application._google_ads_evidence_json import (
    _constant,
    _cost,
    _count,
    _date,
    _encode,
    _invalid,
    _list,
    _object,
    _pairs,
    _text,
)
from paw.application.google_ads import MAX_BATCH_JSON_BYTES
from paw.domain.files import MAX_ROWS, InputError
from paw.domain.google_ads import MatchType
from paw.domain.google_ads_evidence import (
    CampaignObservation,
    SearchEvidenceSpec,
    SearchObservation,
    SearchSummary,
)
from paw.tools.google_ads_evidence import MAX_EVIDENCE_DAYS
from paw.tools.google_ads_search_evidence import MAX_SEARCH_EVIDENCE_ROWS, summarize_search

MAX_SEARCH_EVIDENCE_JSON_BYTES = 2 * 1024 * 1024
_SOURCE_ID = re.compile(r"sha256:[0-9a-f]{64}")
_MATCH_LABELS: dict[MatchType, str] = {
    "exact": "Точна відповідність",
    "phrase": "Фразова відповідність",
    "broad": "Широка відповідність",
}


def _optional_text(value: object) -> str | None:
    return None if value is None else _text(value)


def _metrics(row: dict[str, object], source_id: str, *, summary: bool) -> CampaignObservation:
    required = {
        "row_id",
        "line_start",
        "line_end",
        "campaign",
        "day",
        "impressions",
        "clicks",
        "cost",
        "currency",
        "summary_label",
    }
    if not required.issubset(row) or row["day"] is not None:
        raise _invalid()
    first, last = row["line_start"], row["line_end"]
    if type(first) is not int or type(last) is not int or first < 4 or last < first:
        raise _invalid()
    row_id = f"{source_id}:{first}-{last}"
    if row["row_id"] != row_id:
        raise _invalid()
    if summary:
        if not _text(row["summary_label"]).startswith("Усього:"):
            raise _invalid()
        campaign = _optional_text(row["campaign"]) or ""
    else:
        if row["summary_label"] is not None:
            raise _invalid()
        campaign = _text(row["campaign"])
        if not campaign.strip() or campaign.strip() == "--":
            raise _invalid()
    currency = row["currency"]
    if currency is not None and (
        not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency)
    ):
        raise _invalid()
    return CampaignObservation(
        row_id,
        campaign,
        None,
        _count(row["impressions"]),
        _count(row["clicks"]),
        _cost(row["cost"]),
        currency,
    )


def _search_row(row: dict[str, object], source_id: str, *, terms: bool) -> SearchObservation:
    metrics = _metrics(row, source_id, summary=False)
    if not {
        "keyword",
        "ad_group",
        "match_type",
        "search_term",
        "close_variant",
        "match_type_text",
    }.issubset(row):
        raise _invalid()
    group = _text(row["ad_group"])
    if not group.strip() or group.strip() == "--":
        raise _invalid()
    match = row["match_type"]
    if match == "exact":
        match_type: MatchType = "exact"
    elif match == "phrase":
        match_type = "phrase"
    elif match == "broad":
        match_type = "broad"
    else:
        raise _invalid()
    keyword = _optional_text(row["keyword"])
    if keyword is not None and keyword.strip() in ("", "--"):
        raise _invalid()
    query = None
    close = None
    label = None
    if terms:
        query = _text(row["search_term"])
        if query.strip() in ("", "--"):
            raise _invalid()
        if type(row["close_variant"]) is not bool:
            raise _invalid()
        close = row["close_variant"]
        label = _text(row["match_type_text"])
        expected = _MATCH_LABELS[match_type] + (" (наближений варіант)" if close else "")
        if label != expected or (close and match_type == "broad"):
            raise _invalid()
    elif keyword is None or row["search_term"] is not None:
        raise _invalid()
    return SearchObservation(
        metrics,
        group,
        keyword,
        query,
        match_type,
        label,
        close,
        _optional_text(row.get("keyword_status")) if not terms else None,
        _optional_text(row.get("added_or_excluded")) if terms else None,
    )


def build_search_evidence(data: bytes, spec: SearchEvidenceSpec) -> bytes:
    """Select one source of each requested profile; no cross-report join or summation."""
    if len(data) > MAX_BATCH_JSON_BYTES:
        raise InputError("evidence_input_too_large")
    requested = [
        ("search_keywords", spec.keyword_source_id),
        ("search_terms", spec.search_term_source_id),
    ]
    ids = [source_id for _, source_id in requested if source_id is not None]
    if not ids or len(set(ids)) != len(ids):
        raise InputError("invalid_search_source_selection")
    if any(not _SOURCE_ID.fullmatch(source_id) for source_id in ids):
        raise InputError("invalid_evidence_source")
    if not 1 <= (spec.period_end - spec.period_start).days + 1 <= MAX_EVIDENCE_DAYS:
        raise InputError("invalid_evidence_period")
    try:
        batch = _object(
            json.loads(data.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_constant)
        )
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise _invalid() from None
    if type(batch.get("schema_version")) is not int or batch["schema_version"] != 1:
        raise InputError("unsupported_batch_schema")
    batch_id = _text(batch.get("batch_id"), 36)
    try:
        UUID(batch_id)
    except ValueError:
        raise _invalid() from None
    account = _object(batch.get("account"))
    account_ref = _text(account.get("local_ref"), 120)
    if (
        not account_ref.strip()
        or any(ord(c) < 32 or ord(c) == 127 for c in account_ref)
        or account.get("scope") != "owner_asserted"
    ):
        raise _invalid()
    reports = _object(batch.get("reports"))
    output_reports: dict[str, object] = {"search_keywords": None, "search_terms": None}
    known_currencies: set[str] = set()
    missing_currency = False
    consumed_rows = 0
    for expected, source_id in requested:
        if source_id is None:
            continue
        matches = []
        for kind, values in reports.items():
            for value in _list(values):
                source = _object(value)
                if source.get("source_id") == source_id:
                    matches.append((kind, source))
        if len(matches) != 1:
            raise InputError("evidence_source_not_unique")
        kind, source = matches[0]
        if kind != expected or source.get("report_type") != expected:
            raise InputError("unsupported_evidence_source")
        start, end = _date(source.get("period_start")), _date(source.get("period_end"))
        if (start, end) != (spec.period_start, spec.period_end):
            raise InputError("search_evidence_period_mismatch")
        source_warnings = _list(source.get("warnings"))
        if len(source_warnings) > 32 or any(
            not isinstance(code, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,79}", code)
            for code in source_warnings
        ):
            raise _invalid()
        details, totals = _list(source.get("details")), _list(source.get("totals"))
        if len(details) + len(totals) > MAX_ROWS:
            raise InputError("too_many_source_rows")
        consumed_rows += len(details) + len(totals)
        if consumed_rows > MAX_SEARCH_EVIDENCE_ROWS:
            raise InputError("too_many_search_evidence_rows")
        rows = tuple(
            _search_row(_object(row), source_id, terms=expected == "search_terms")
            for row in details
        )
        summaries = tuple(
            SearchSummary(
                _text(_object(row).get("summary_label")),
                _metrics(_object(row), source_id, summary=True),
            )
            for row in totals
        )
        # Validate physical references jointly so totals cannot alias detail rows.
        ranges = sorted(
            (_object(row)["line_start"], _object(row)["line_end"]) for row in details + totals
        )
        last_line = 3
        for first, last in ranges:
            if type(first) is not int or type(last) is not int or first <= last_line:
                raise _invalid()
            last_line = last
        observations = [row.metrics for row in rows] + [row.metrics for row in summaries]
        for observation in observations:
            if observation.currency is None:
                missing_currency = True
            else:
                known_currencies.add(observation.currency)
        if len(known_currencies) > 1:
            raise InputError("evidence_currency_mismatch")
        result, warnings = summarize_search(rows, summaries, terms=expected == "search_terms")
        warning_set = set(warnings)
        if any(r.currency is None for r in observations):
            warning_set.add("currency_unverified")
        if any(r.impressions is None or r.clicks is None or r.cost is None for r in observations):
            warning_set.add("missing_metric_values")
        output_reports[expected] = {
            "source": {
                "source_id": source_id,
                "report_type": expected,
                "period_start": start,
                "period_end": end,
                "warnings": source_warnings,
            },
            **result,
            "warnings": sorted(warning_set),
        }
    document = {
        "schema_version": 1,
        "evidence_type": "search_detail",
        "input_batch_id": batch_id,
        "input_batch_sha256": sha256(data).hexdigest(),
        "account": {"local_ref": account_ref, "scope": "owner_asserted"},
        "period": {"start": spec.period_start, "end": spec.period_end},
        "currency": next(iter(known_currencies))
        if known_currencies and not missing_currency
        else None,
        "observed_currencies": sorted(known_currencies),
        "policies": {
            "cross_report_metrics": "not_additive",
            "keyword_query_joins": "not_performed",
            "ratios": "paired_nonmissing_rows",
            "ratio_decimal_places": 6,
            "ratio_rounding": "half_even",
            "unreported_activity": "not_allocated",
            "missing_values": "null_not_zero",
            "daily_coverage": "not_collected",
            "source_text": "untrusted_data",
            "provider_submission": "not_authorized_by_evidence_creation",
        },
        "reports": output_reports,
        "warnings": [
            "account_scope_unverified",
            "source_identity_unverified",
            "cross_report_totals_not_additive",
        ],
    }
    output = bytearray()
    encoder = json.JSONEncoder(ensure_ascii=False, allow_nan=False, indent=2, default=_encode)
    for chunk in encoder.iterencode(document):
        output.extend(chunk.encode("utf-8"))
        if len(output) + 1 > MAX_SEARCH_EVIDENCE_JSON_BYTES:
            raise InputError("evidence_json_too_large")
    return bytes(output) + b"\n"
