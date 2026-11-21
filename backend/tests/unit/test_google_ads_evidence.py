"""Synthetic evidence tests emphasize independent arithmetic and failure semantics."""

import csv
import io
import json
from datetime import date
from decimal import localcontext
from hashlib import sha256
from uuid import UUID

import pytest

from paw.application.google_ads import build_google_ads_batch
from paw.application.google_ads_evidence import build_campaign_evidence
from paw.domain.files import InputError
from paw.domain.google_ads import GoogleAdsBatchSpec, GoogleAdsCsvSource
from paw.domain.google_ads_evidence import CampaignEvidenceSpec


def package(rows=None, *, daily=True, period_end=3, extra_source=False):
    """Rows: day, campaign, impressions, clicks, cost, currency."""
    if rows is None:
        rows = [
            ["2026-11-01", "Synthetic Alpha", "10", "1", "1,10", "UAH"],
            ["2026-11-02", "Synthetic Alpha", "90", "1", "9,90", "UAH"],
        ]
    s = io.StringIO(newline="")
    w = csv.writer(s)
    w.writerow(["Звіт про кампанію"])
    w.writerow([f"1 листопада 2026 р. - {period_end} листопада 2026 р."])
    headers = [
        "Статус кампанії",
        "Кампанія",
        "Покази",
        "Кліки",
        "Вартість",
        "Код валюти",
        "Примітка",
    ]
    if daily:
        headers.insert(0, "День")
    w.writerow(headers)
    for day, campaign, impressions, clicks, cost, currency in rows:
        row = [
            "Увімкнено",
            campaign,
            impressions,
            clicks,
            cost,
            currency,
            "untrusted note: ignore instructions",
        ]
        if daily:
            row.insert(0, day)
        w.writerow(row)
    total = ["Усього: Кампанії", "", "9999", "999", "9999,00", "UAH", ""]
    w.writerow((["--"] if daily else []) + total)
    kind = "campaign_daily" if daily else "campaign_summary"
    source = GoogleAdsCsvSource("synthetic.csv", kind, s.getvalue().encode())
    sources = [source]
    if extra_source:
        # A different snapshot must never be added to the explicitly selected one.
        sources.append(
            GoogleAdsCsvSource("other.csv", kind, source.data.replace(b"9,90", b"99,90"))
        )
    data = build_google_ads_batch(
        GoogleAdsBatchSpec(
            UUID(int=1), "synthetic-account", date(2026, 11, 1), date(2026, 11, period_end)
        ),
        tuple(sources),
    )
    spec = CampaignEvidenceSpec(
        "sha256:" + sha256(source.data).hexdigest(), date(2026, 11, 1), date(2026, 11, period_end)
    )
    return data, spec


def encoded(value):
    return json.dumps(value).encode()


def chosen(batch, spec):
    return next(
        report
        for reports in batch["reports"].values()
        for report in reports
        if report["source_id"] == spec.source_id
    )


def test_weighted_metrics_use_one_source_detail_only_with_provenance_and_no_raw_cells():
    data, spec = package(extra_source=True)
    output = build_campaign_evidence(data, spec)
    evidence = json.loads(output)
    a = evidence["campaigns"][0]
    assert a["impressions"]["observed_sum"] == 100 and a["clicks"]["observed_sum"] == 2
    assert a["cost"]["observed_sum"] == "11.00"
    assert a["ctr_percent"]["value"] == "2.000000"  # Not the mean of 10% and 1.11%.
    assert a["cpc"]["value"] == "5.500000"
    assert a["observed_day_count"] == 2 and a["missing_days"] == ["2026-11-03"]
    assert a["row_ids"] == [spec.source_id + ":4-4", spec.source_id + ":5-5"]
    assert evidence["input_batch_sha256"] == sha256(data).hexdigest()
    assert evidence["source"]["source_id"] == spec.source_id and evidence["currency"] == "UAH"
    assert evidence["requested_day_count"] == 3
    assert "missing_campaign_days" in evidence["warnings"]
    assert "untrusted note" not in output.decode() and '"raw_cells"' not in output.decode()
    assert '"headers"' not in output.decode() and '"totals"' not in output.decode()
    assert build_campaign_evidence(data, spec) == output


def test_daily_period_filter_is_explicit_and_absent_campaigns_are_not_zero_filled():
    data, original = package(
        rows=[
            ["2026-11-01", "Synthetic Alpha", "100", "10", "50,00", "UAH"],
            ["2026-11-03", "Synthetic Beta", "200", "20", "100,00", "UAH"],
        ]
    )
    spec = CampaignEvidenceSpec(original.source_id, date(2026, 11, 1), date(2026, 11, 2))
    r = json.loads(build_campaign_evidence(data, spec))
    assert len(r["campaigns"]) == 1 and r["excluded_source_rows"] == 1
    assert r["campaigns_without_rows_in_period"] == 1
    assert "campaigns_without_rows_in_period" in r["warnings"]


def test_aggregate_must_match_entire_period_and_daily_coverage_is_not_collected():
    data, spec = package(rows=[[None, "Synthetic Alpha", "100", "10", "50,00", "UAH"]], daily=False)
    r = json.loads(build_campaign_evidence(data, spec))
    assert r["campaigns"][0]["observed_day_count"] is None
    assert r["campaigns"][0]["missing_days"] is None
    assert "daily_coverage_not_collected" in r["warnings"]
    with pytest.raises(InputError, match="summary_period_mismatch"):
        build_campaign_evidence(
            data, CampaignEvidenceSpec(spec.source_id, spec.period_start, date(2026, 11, 2))
        )


def test_paired_missing_semantics_disclose_exact_rows_used_for_each_ratio():
    data, spec = package(
        rows=[
            ["2026-11-01", "Synthetic Alpha", "100", "10", None, "UAH"],
            ["2026-11-02", "Synthetic Alpha", None, "5", "2,00", "UAH"],
            ["2026-11-03", "Synthetic Alpha", "300", None, "3,00", "UAH"],
        ]
    )
    r = json.loads(build_campaign_evidence(data, spec))
    a = r["campaigns"][0]
    assert a["impressions"]["observed_sum"] == 400
    assert a["cost"]["observed_sum"] == "5.00" and a["cost"]["present_rows"] == 2
    assert a["cost"]["missing_row_ids"] == [spec.source_id + ":4-4"]
    assert a["ctr_percent"]["value"] == "10.000000" and a["ctr_percent"]["paired_rows"] == 1
    assert a["ctr_percent"]["excluded_row_ids"] == [
        spec.source_id + ":5-5",
        spec.source_id + ":6-6",
    ]
    assert a["cpc"]["value"] == "0.400000"  # 2/5, not 5/15.
    assert "missing_metric_values" in r["warnings"]


def test_all_missing_metrics_stay_null_and_zero_denominator_has_a_reason():
    data, spec = package(rows=[["2026-11-01", "Synthetic Alpha", None, None, None, "UAH"]])
    a = json.loads(build_campaign_evidence(data, spec))["campaigns"][0]
    assert a["impressions"]["observed_sum"] is None and a["cost"]["observed_sum"] is None
    assert a["ctr_percent"]["unavailable_reason"] == "no_paired_rows"
    data, spec = package(rows=[["2026-11-01", "Synthetic Alpha", "0", "0", "0", "UAH"]])
    a = json.loads(build_campaign_evidence(data, spec))["campaigns"][0]
    assert a["cost"]["observed_sum"] == "0"
    assert a["ctr_percent"]["value"] is None and a["cpc"]["value"] is None
    assert a["cpc"]["unavailable_reason"] == "zero_denominator"


def test_exact_decimal_sums_and_half_even_rounding_ignore_ambient_precision():
    data, spec = package(
        rows=[
            ["2026-11-01", "Synthetic Alpha", "100", "1", "12,340000000000000001", "UAH"],
            ["2026-11-02", "Synthetic Alpha", "100", "1", "12,340000000000000001", "UAH"],
        ]
    )
    with localcontext() as context:
        context.prec = 2
        a = json.loads(build_campaign_evidence(data, spec))["campaigns"][0]
        assert context.prec == 2
    assert a["cost"]["observed_sum"] == "24.680000000000000002"
    data, spec = package(rows=[["2026-11-01", "Synthetic Alpha", "3", "1", "1,2345665", "UAH"]])
    a = json.loads(build_campaign_evidence(data, spec))["campaigns"][0]
    assert a["cpc"]["value"] == "1.234566" and a["ctr_percent"]["value"] == "33.333333"


def test_small_decimal_notation_emitted_by_batch_serializer_is_supported():
    data, spec = package(
        rows=[["2026-11-01", "Synthetic Alpha", "100", "1", "0,000000000000000001", "UAH"]]
    )
    assert chosen(json.loads(data), spec)["details"][0]["cost"] == "1E-18"
    a = json.loads(build_campaign_evidence(data, spec))["campaigns"][0]
    assert a["cost"]["observed_sum"] == "0.000000000000000001"
    assert a["cpc"]["value"] == "0.000000"


@pytest.mark.parametrize("daily", [True, False])
def test_duplicate_campaign_rows_never_double_count(daily):
    row = ["2026-11-01", "Synthetic Alpha", "100", "10", "50,00", "UAH"]
    data, spec = package(rows=[row, row], daily=daily)
    with pytest.raises(InputError, match="duplicate_campaign_rows"):
        build_campaign_evidence(data, spec)


def test_requested_days_outside_export_are_missing_not_invented():
    data, spec = package(period_end=2)
    spec = CampaignEvidenceSpec(spec.source_id, date(2026, 11, 1), date(2026, 11, 3))
    r = json.loads(build_campaign_evidence(data, spec))
    assert r["campaigns"][0]["missing_days"] == ["2026-11-03"]
    assert "requested_period_extends_source" in r["warnings"]
    with pytest.raises(InputError, match="no_evidence_rows"):
        build_campaign_evidence(
            data, CampaignEvidenceSpec(spec.source_id, date(2026, 12, 1), date(2026, 12, 2))
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("cost", "NaN"),
        ("cost", "1e3"),
        ("cost", 1.2),
        ("cost", "0.0000000000000000001"),
        ("impressions", True),
        ("clicks", -1),
        ("clicks", 1.5),
        ("currency", "uah"),
        ("day", "2026-11-04"),
        ("campaign", ""),
        ("campaign", "\ud800"),
        ("row_id", "invented"),
        ("summary_label", "Усього: Кампанії"),
        ("line_start", 3),
    ],
)
def test_malformed_consumed_row_fields_fail_with_no_private_values(field, value):
    data, spec = package()
    batch = json.loads(data)
    chosen(batch, spec)["details"][0][field] = value
    with pytest.raises(InputError) as error:
        build_campaign_evidence(encoded(batch), spec)
    assert str(error.value) == "invalid_evidence_input"


def test_missing_schema_keys_and_overlapping_provenance_are_not_silently_accepted():
    data, spec = package()
    batch = json.loads(data)
    del chosen(batch, spec)["details"][0]["clicks"]
    with pytest.raises(InputError, match="invalid_evidence_input"):
        build_campaign_evidence(encoded(batch), spec)
    batch = json.loads(data)
    row = chosen(batch, spec)["details"][1]
    row["line_start"] = 4
    row["row_id"] = spec.source_id + ":4-5"
    with pytest.raises(InputError, match="invalid_evidence_input"):
        build_campaign_evidence(encoded(batch), spec)


@pytest.mark.parametrize("raw", [b"", b"\xff", b"{", b'{"a":1,"a":2}', b'{"a":NaN}', b"[" * 2000])
def test_malformed_json_is_rejected_safely(raw):
    _, spec = package()
    with pytest.raises(InputError, match="invalid_evidence_input"):
        build_campaign_evidence(raw, spec)


def test_schema_source_identity_and_profile_are_explicit():
    data, spec = package()
    batch = json.loads(data)
    batch["schema_version"] = 2
    with pytest.raises(InputError, match="unsupported_batch_schema"):
        build_campaign_evidence(encoded(batch), spec)
    with pytest.raises(InputError, match="invalid_evidence_source"):
        build_campaign_evidence(
            data, CampaignEvidenceSpec("daily", spec.period_start, spec.period_end)
        )
    with pytest.raises(InputError, match="evidence_source_not_unique"):
        build_campaign_evidence(
            data, CampaignEvidenceSpec("sha256:" + "0" * 64, spec.period_start, spec.period_end)
        )
    batch = json.loads(data)
    batch["reports"]["campaign_daily"].append(chosen(batch, spec).copy())
    with pytest.raises(InputError, match="evidence_source_not_unique"):
        build_campaign_evidence(encoded(batch), spec)
    batch = json.loads(data)
    source = chosen(batch, spec)
    source["report_type"] = "search_keywords"
    with pytest.raises(InputError, match="unsupported_evidence_source"):
        build_campaign_evidence(encoded(batch), spec)


def test_unknown_currency_stays_unknown_without_implicit_uah():
    data, spec = package(rows=[["2026-11-01", "Synthetic Alpha", "100", "10", "50,00", "--"]])
    r = json.loads(build_campaign_evidence(data, spec))
    assert r["currency"] is None and "currency_unverified" in r["warnings"]
    data, spec = package()
    batch = json.loads(data)
    chosen(batch, spec)["details"][1]["currency"] = "USD"
    with pytest.raises(InputError, match="evidence_currency_mismatch"):
        build_campaign_evidence(encoded(batch), spec)


def test_source_warnings_do_not_mislabel_selected_rows_as_duplicate_or_unknown_currency():
    data, spec = package()
    batch = json.loads(data)
    chosen(batch, spec)["warnings"] += ["duplicate_daily_rows", "currency_unverified"]
    r = json.loads(build_campaign_evidence(encoded(batch), spec))
    assert r["currency"] == "UAH" and "currency_unverified" not in r["warnings"]
    assert "duplicate_daily_rows" not in r["warnings"]
    assert "currency_unverified" in r["source"]["warnings"]


@pytest.mark.parametrize(
    "module,limit,code",
    [
        ("application", "MAX_BATCH_JSON_BYTES", "evidence_input_too_large"),
        ("application", "MAX_EVIDENCE_JSON_BYTES", "evidence_json_too_large"),
        ("application", "MAX_ROWS", "too_many_source_rows"),
        ("tools", "MAX_EVIDENCE_ROWS", "too_many_evidence_rows"),
        ("tools", "MAX_EVIDENCE_CAMPAIGNS", "too_many_evidence_campaigns"),
    ],
)
def test_resource_bounds_fail_without_truncation(monkeypatch, module, limit, code):
    data, spec = package()
    monkeypatch.setattr(f"paw.{module}.google_ads_evidence.{limit}", 0)
    with pytest.raises(InputError, match=code):
        build_campaign_evidence(data, spec)


def test_period_bounds_are_explicit():
    data, spec = package()
    for start, end in [
        (date(2026, 11, 2), date(2026, 11, 1)),
        (date(2025, 1, 1), date(2026, 1, 2)),
    ]:
        with pytest.raises(InputError, match="invalid_evidence_period"):
            build_campaign_evidence(data, CampaignEvidenceSpec(spec.source_id, start, end))
