"""Bounded batch JSON -> campaign evidence; never executes source text or calls AI."""

import json
import re
from dataclasses import asdict
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
from paw.domain.google_ads_evidence import CampaignEvidenceSpec, CampaignObservation
from paw.tools.google_ads_evidence import MAX_EVIDENCE_DAYS, summarize_campaigns

MAX_EVIDENCE_JSON_BYTES = 2 * 1024 * 1024
_SOURCE_ID = re.compile(r"sha256:[0-9a-f]{64}")


def build_campaign_evidence(data: bytes, spec: CampaignEvidenceSpec) -> bytes:
    """Validate consumed schema-v1 fields, select exactly one campaign source and calculate.

    This validates references inside the package, not original CSV authenticity.
    Unselected reports and source totals never contribute to campaign arithmetic.
    """
    if len(data) > MAX_BATCH_JSON_BYTES:
        raise InputError("evidence_input_too_large")
    if not _SOURCE_ID.fullmatch(spec.source_id):
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
    if not account_ref.strip() or any(ord(c) < 32 or ord(c) == 127 for c in account_ref):
        raise _invalid()
    if account.get("scope") != "owner_asserted":
        raise _invalid()
    reports = _object(batch.get("reports"))
    selected: list[tuple[str, dict[str, object]]] = []
    for kind, values in reports.items():
        for value in _list(values):
            report = _object(value)
            if report.get("source_id") == spec.source_id:
                selected.append((kind, report))
    if len(selected) != 1:
        raise InputError("evidence_source_not_unique")
    kind, source = selected[0]
    if kind not in ("campaign_daily", "campaign_summary") or source.get("report_type") != kind:
        raise InputError("unsupported_evidence_source")
    start, end = _date(source.get("period_start")), _date(source.get("period_end"))
    if start > end:
        raise _invalid()
    daily = kind == "campaign_daily"
    if not daily and (start, end) != (spec.period_start, spec.period_end):
        raise InputError("summary_period_mismatch")
    warning_codes = _list(source.get("warnings"))
    if len(warning_codes) > 32 or any(
        not isinstance(code, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,79}", code)
        for code in warning_codes
    ):
        raise _invalid()
    details = _list(source.get("details"))
    if len(details) > MAX_ROWS:
        raise InputError("too_many_source_rows")
    observations = []
    all_campaigns: set[str] = set()
    last_line = 3
    for value in details:
        row = _object(value)
        if not {
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
        }.issubset(row):
            raise _invalid()
        first, last = row.get("line_start"), row.get("line_end")
        if type(first) is not int or type(last) is not int or first <= last_line or last < first:
            raise _invalid()
        last_line = last
        row_id = f"{spec.source_id}:{first}-{last}"
        if row.get("row_id") != row_id or row.get("summary_label") is not None:
            raise _invalid()
        campaign = _text(row.get("campaign"))
        if not campaign.strip() or campaign.strip() == "--":
            raise _invalid()
        day = _date(row.get("day")) if daily else None
        if daily and day is not None and not start <= day <= end:
            raise _invalid()
        if not daily and row.get("day") is not None:
            raise _invalid()
        currency = row.get("currency")
        if currency is not None and (
            not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency)
        ):
            raise _invalid()
        observation = CampaignObservation(
            row_id,
            campaign,
            day,
            _count(row.get("impressions")),
            _count(row.get("clicks")),
            _cost(row.get("cost")),
            currency,
        )
        all_campaigns.add(campaign)
        if not daily or (day is not None and spec.period_start <= day <= spec.period_end):
            observations.append(observation)
    currencies = {row.currency for row in observations if row.currency is not None}
    if len(currencies) > 1:
        raise InputError("evidence_currency_mismatch")
    results = summarize_campaigns(tuple(observations), spec, daily=daily)
    # Whole-source warnings can concern excluded rows or totals. Keep them as
    # source context, separate from warnings computed for the selected evidence.
    warnings = {
        "account_scope_unverified",
        "campaign_identity_unverified",
        "campaign_inventory_unverified",
        "export_snapshot_time_not_collected",
    }
    if any(row.currency is None for row in observations):
        warnings.add("currency_unverified")
    if any(result.missing_days for result in results):
        warnings.add("missing_campaign_days")
    if not daily:
        warnings.add("daily_coverage_not_collected")
    if spec.period_start < start or spec.period_end > end:
        warnings.add("requested_period_extends_source")
    excluded_campaigns = len(all_campaigns - {r.campaign for r in observations})
    if excluded_campaigns:
        warnings.add("campaigns_without_rows_in_period")
    if any(m.missing_row_ids for r in results for m in (r.impressions, r.clicks, r.cost)):
        warnings.add("missing_metric_values")
    document = {
        "schema_version": 1,
        "evidence_type": "campaign_summary",
        "input_batch_id": batch_id,
        "input_batch_sha256": sha256(data).hexdigest(),
        "account": {"local_ref": account_ref, "scope": "owner_asserted"},
        "source": {
            "source_id": spec.source_id,
            "report_type": kind,
            "period_start": start,
            "period_end": end,
            "warnings": warning_codes,
        },
        "period": {"start": spec.period_start, "end": spec.period_end},
        "requested_day_count": (spec.period_end - spec.period_start).days + 1,
        "currency": next(iter(currencies))
        if currencies and all(r.currency for r in observations)
        else None,
        "observed_currencies": sorted(currencies),
        "excluded_source_rows": len(details) - len(observations),
        "campaigns_without_rows_in_period": excluded_campaigns,
        "policies": {
            "metrics_scope": "observed_detail_rows_only",
            "ratios": "sums_of_paired_nonmissing_rows",
            "ratio_decimal_places": 6,
            "ratio_rounding": "half_even",
            "missing_days": "not_zero_filled",
            "summary_rows": "excluded",
            "source_text": "untrusted_data",
            "provider_submission": "not_authorized_by_evidence_creation",
        },
        "campaigns": [asdict(result) for result in results],
        "warnings": sorted(warnings),
    }
    output = bytearray()
    encoder = json.JSONEncoder(ensure_ascii=False, allow_nan=False, indent=2, default=_encode)
    for chunk in encoder.iterencode(document):
        output.extend(chunk.encode("utf-8"))
        if len(output) + 1 > MAX_EVIDENCE_JSON_BYTES:
            raise InputError("evidence_json_too_large")
    return bytes(output) + b"\n"
