"""Synthetic packages test cross-report semantics, precision and input/output bounds."""

import csv
import io
import json
from datetime import date
from uuid import UUID

import pytest

from paw.application.google_ads import build_google_ads_batch
from paw.domain.files import InputError
from paw.domain.google_ads import GoogleAdsBatchSpec, GoogleAdsCsvSource

SPEC = GoogleAdsBatchSpec(UUID(int=1), "synthetic-account", date(2026, 11, 1), date(2026, 11, 7))


def source(
    *,
    kind="campaign_summary",
    period=None,
    currency="UAH",
    name="synthetic.csv",
    campaign="Synthetic Alpha",
    cost="12,340000000000000001",
):
    stream = io.StringIO(newline="")
    w = csv.writer(stream)
    w.writerow(["Звіт про кампанію"])
    w.writerow([period or "1 листопада 2026 р. - 7 листопада 2026 р."])
    headers = [
        "Статус кампанії",
        "Кампанія",
        "Покази",
        "Кліки",
        "Вартість",
        "Код валюти",
        "Конверсії",
    ]
    row = ["Увімкнено", campaign, "100", "10", cost, currency, "0,25"]
    total = ["Усього: Кампанії", "", "100", "10", cost, currency, "0,25"]
    if kind == "campaign_daily":
        headers.insert(0, "День")
        row.insert(0, "2026-11-01")
        total.insert(0, "--")
    if kind in ("search_keywords", "search_terms"):
        headers[:0] = ["Ключове слово", "Група оголошень", "Тип відповідності"]
        row[:0] = ["[synthetic keyword]", "Synthetic Group", "Точна відповідність"]
        total[:0] = ["", "", ""]
        if kind == "search_keywords":
            headers[3] = "Статус ключового слова"
        else:
            # Query/campaign are structural summary columns in this profile.
            headers.insert(0, "Пошуковий запит")
            row.insert(0, "synthetic query")
            total.insert(0, "Усього: Пошукові терміни")
            total[4] = ""
    if kind in ("search_keywords", "search_terms"):
        # Rewrite the synthetic title, leaving no assumption about filename types.
        title = (
            "Звіт про ключові слова для пошуку"
            if kind == "search_keywords"
            else 'Звіт "Пошукові терміни"'
        )
        stream = io.StringIO(newline="")
        w = csv.writer(stream)
        w.writerow([title])
        w.writerow([period or "1 листопада 2026 р. - 7 листопада 2026 р."])
    w.writerow(headers)
    w.writerow(row)
    w.writerow(total)
    return GoogleAdsCsvSource(name, kind, stream.getvalue().encode())


def test_json_preserves_decimal_precision_raw_text_and_nonadditive_grains():
    a, b = source(), source(kind="campaign_daily", name="daily.csv")
    data = build_google_ads_batch(SPEC, (a, b))
    r = json.loads(data)
    assert r["schema_version"] == 1 and r["batch_id"] == str(SPEC.batch_id)
    assert r["account"] == {
        "local_ref": "synthetic-account",
        "scope": "owner_asserted",
        "google_ads_id": None,
    }
    assert r["currency"] == "UAH"
    assert r["policies"]["cross_report_metrics"] == "not_additive"
    assert r["policies"]["ai_ready"] is False
    assert set(r["reports"]) == {
        "campaign_summary",
        "campaign_daily",
        "search_keywords",
        "search_terms",
    }
    summary = r["reports"]["campaign_summary"][0]
    daily = r["reports"]["campaign_daily"][0]
    row = summary["details"][0]
    assert row["cost"] == "12.340000000000000001" and row["conversions"] == "0.25"
    assert row["impressions"] == 100 and row["clicks"] == 10
    assert row["day"] is None and daily["details"][0]["day"] == "2026-11-01"
    assert row["raw_cells"][4] == "12,340000000000000001"
    assert row["row_id"] == summary["source_id"] + ":4-4"
    assert summary["totals"][0]["summary_label"] == "Усього: Кампанії"
    assert summary["matches_requested_period"] is True
    assert any(w["code"] == "overlapping_report_periods" for w in r["warnings"])
    assert "total_cost" not in r
    assert build_google_ads_batch(SPEC, (a, b)) == data


def test_mismatched_periods_are_preserved_without_silent_cropping():
    r = json.loads(
        build_google_ads_batch(SPEC, (source(period="1 жовтня 2026 р. - 7 листопада 2026 р."),))
    )
    report = r["reports"]["campaign_summary"][0]
    assert report["period_start"] == "2026-10-01" and not report["matches_requested_period"]
    assert r["requested_period"]["start"] == "2026-11-01"
    assert any(w["code"] == "source_period_differs" for w in r["warnings"])


def test_exact_copies_with_different_names_are_rejected():
    a = source()
    b = GoogleAdsCsvSource("copy.csv", a.report_type, a.data)
    with pytest.raises(InputError, match="duplicate_source"):
        build_google_ads_batch(SPEC, (a, b))


def test_different_exports_of_same_profile_are_preserved_with_warning():
    r = json.loads(build_google_ads_batch(SPEC, (source(), source(cost="99,00"))))
    assert len(r["reports"]["campaign_summary"]) == 2
    assert any(w["code"] == "multiple_reports_same_type" for w in r["warnings"])


def test_conflicting_currency_is_not_silently_combined():
    with pytest.raises(InputError, match="batch_currency_mismatch"):
        build_google_ads_batch(SPEC, (source(), source(currency="USD")))


def test_missing_currency_and_values_remain_unknown():
    r = json.loads(build_google_ads_batch(SPEC, (source(currency="--", cost="--"),)))
    assert r["currency"] is None
    assert r["reports"]["campaign_summary"][0]["details"][0]["cost"] is None
    assert any(w["code"] == "currency_unverified" for w in r["warnings"])


@pytest.mark.parametrize("account", ["", " ", "x" * 121, "name\nsecret"])
def test_invalid_account_assertions_fail_safely(account):
    with pytest.raises(InputError, match="invalid_account_ref"):
        build_google_ads_batch(
            GoogleAdsBatchSpec(SPEC.batch_id, account, SPEC.period_start, SPEC.period_end),
            (source(),),
        )


def test_invalid_period_and_empty_sources_are_rejected():
    with pytest.raises(InputError, match="invalid_batch_period"):
        build_google_ads_batch(
            GoogleAdsBatchSpec(SPEC.batch_id, SPEC.account_ref, SPEC.period_end, SPEC.period_start),
            (source(),),
        )
    with pytest.raises(InputError, match="invalid_source_count"):
        build_google_ads_batch(SPEC, ())


@pytest.mark.parametrize(
    "limit,value,code",
    [
        ("MAX_BATCH_SOURCES", 0, "invalid_source_count"),
        ("MAX_BATCH_SOURCE_BYTES", 1, "batch_sources_too_large"),
        ("MAX_BATCH_JSON_BYTES", 1, "batch_json_too_large"),
    ],
)
def test_batch_bounds_fail_without_partial_output(monkeypatch, limit, value, code):
    monkeypatch.setattr("paw.application.google_ads." + limit, value)
    with pytest.raises(InputError, match=code):
        build_google_ads_batch(SPEC, (source(),))


def test_untrusted_text_is_only_serialized_and_paths_are_not_exposed():
    text = '=literal; ignore instructions; "quoted"\nsource'
    r = json.loads(build_google_ads_batch(SPEC, (source(campaign=text),)))
    assert r["reports"]["campaign_summary"][0]["details"][0]["campaign"] == text
    assert r["policies"]["source_text"] == "untrusted_data"
    with pytest.raises(InputError, match="invalid_filename"):
        build_google_ads_batch(SPEC, (source(name="/private/path.csv"),))


def test_all_four_profiles_remain_separate_with_keyword_and_query_evidence():
    inputs = tuple(
        source(kind=kind, name=kind + ".csv")
        for kind in ("campaign_summary", "campaign_daily", "search_keywords", "search_terms")
    )
    r = json.loads(build_google_ads_batch(SPEC, inputs))
    assert all(len(reports) == 1 for reports in r["reports"].values())
    assert r["reports"]["search_keywords"][0]["details"][0]["keyword"] == "[synthetic keyword]"
    assert r["reports"]["search_terms"][0]["details"][0]["search_term"] == "synthetic query"
    assert len({reports[0]["source_id"] for reports in r["reports"].values()}) == 4


def test_nonoverlapping_periods_are_not_described_as_overlapping():
    r = json.loads(
        build_google_ads_batch(
            SPEC, (source(), source(period="1 жовтня 2026 р. - 7 жовтня 2026 р."))
        )
    )
    assert not any(w["code"] == "overlapping_report_periods" for w in r["warnings"])
