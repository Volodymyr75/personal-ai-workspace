"""Entirely synthetic exports; no private campaign names or source values."""

import csv
import io
from datetime import date
from decimal import Decimal
from hashlib import sha256

import pytest

from paw.domain.files import InputError, inspect_csv
from paw.tools.google_ads_csv import (
    parse_campaign_daily,
    parse_campaign_summary,
    parse_search_keywords,
    parse_search_terms,
)

HEADERS = [
    "Кампанія",
    "Покази",
    "Кліки",
    "Вартість",
    "Код валюти",
    "Конверсії",
    "CTR",
    "Сер. ціна за клік",
    "Примітка",
]
ROWS = [
    ["Synthetic Alpha", "1\u00a0234", "12", "24,60", "UAH", "1,25", "0,97%", "2,05", "=1+1"],
    ["Synthetic Beta", "2\u202f000", "0", "0", "UAH", "--", "0%", "--", "literal\ntext"],
    ["Усього: Кампанії", "3 234", "12", "24,60", "UAH", "1,25", "0,37%", "2,05", ""],
    ["Усього: Обліковий запис", "3 234", "12", "24,60", "UAH", "1,25", "0,37%", "2,05", ""],
]


def export(
    *,
    rows=None,
    headers=None,
    period="1 листопада 2026 р. – 7 листопада 2026 р.",
    title="Звіт про кампанію",
    delimiter=",",
):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, delimiter=delimiter)
    writer.writerow([title])
    writer.writerow([period])
    writer.writerow(HEADERS if headers is None else headers)
    writer.writerows(ROWS if rows is None else rows)
    return stream.getvalue().encode()


def test_normalization_keeps_totals_separate_and_preserves_provenance():
    data = b"\xef\xbb\xbf" + export()
    report = parse_campaign_summary(data)
    assert report.source_sha256 == sha256(data).hexdigest()
    assert report.source_size_bytes == len(data)
    assert report.headers == tuple(HEADERS)
    assert report.period_start == date(2026, 11, 1)
    assert report.period_end == date(2026, 11, 7)
    assert report.title == "Звіт про кампанію"
    assert report.period_text == "1 листопада 2026 р. – 7 листопада 2026 р."
    assert report.currency == "UAH"
    assert report.account_id is None
    assert report.warnings == ("account_scope_unverified", "coverage_unverified")
    assert len(report.details) == len(report.totals) == 2
    first, second = report.details
    assert (first.line_start, first.line_end) == (4, 4)
    assert (second.line_start, second.line_end) == (5, 6)
    assert report.totals[0].line_start == 7
    assert first.raw_cells == tuple(ROWS[0])
    assert first.impressions == 1234
    assert first.clicks == 12
    assert first.cost == Decimal("24.60")
    assert first.conversions == Decimal("1.25")
    assert first.ctr_percent == Decimal("0.97")
    assert first.average_cpc == Decimal("2.05")
    assert second.impressions == 2000
    assert second.clicks == second.cost == 0
    assert second.conversions is second.average_cpc is None
    # Detail spend is 24.60; the two reconciliation rows must never triple it.
    assert sum(row.cost for row in report.details) == Decimal("24.60")


def test_semicolon_and_numeric_dates_are_explicit():
    data = export(delimiter=";", period="01.11.2026 - 07.11.2026")
    assert parse_campaign_summary(data, ";").period_end == date(2026, 11, 7)
    with pytest.raises(InputError):
        parse_campaign_summary(data)
    with pytest.raises(InputError, match="invalid_delimiter"):
        parse_campaign_summary(data, "\t")


@pytest.mark.parametrize(
    "column,value,code",
    [
        ("Вартість", "1 23,40", "invalid_numeric"),
        ("Вартість", "NaN", "invalid_numeric"),
        ("Вартість", "Infinity", "invalid_numeric"),
        ("Вартість", "=1+1", "invalid_numeric"),
        ("Вартість", "-1", "invalid_numeric"),
        ("Вартість", "12.34", "invalid_numeric"),
        ("Вартість", "1000000000000001", "numeric_overflow"),
        ("Кліки", "1,5", "invalid_numeric"),
        ("CTR", "1,5", "invalid_numeric"),
        ("CTR", "101%", "invalid_numeric"),
        ("Код валюти", "eur", "invalid_currency"),
        ("Кампанія", " ", "missing_campaign"),
    ],
)
def test_bad_values_fail_without_echoing_private_data(column, value, code):
    row = ROWS[0].copy()
    row[HEADERS.index(column)] = value
    with pytest.raises(InputError) as error:
        parse_campaign_summary(export(rows=[row]))
    assert str(error.value) == code


def test_missing_values_and_currency_are_not_invented():
    row = ["Synthetic Missing", "--", "", "--", "--", "", "--", "", ""]
    report = parse_campaign_summary(export(rows=[ROWS[0], row]))
    missing = report.details[1]
    assert missing.impressions is missing.clicks is missing.cost is None
    assert missing.currency is report.currency is None
    assert "currency_unverified" in report.warnings


def test_minimal_columns_retain_unknown_currency():
    report = parse_campaign_summary(
        export(
            headers=HEADERS[:4],
            rows=[["Synthetic Minimal", "10", "1", "1,20"]],
        )
    )
    assert report.details[0].cost == Decimal("1.20")
    assert report.details[0].conversions is None
    assert report.currency is None


def test_mixed_currencies_rejected_even_in_totals():
    row = ROWS[2].copy()
    row[4] = "USD"
    with pytest.raises(InputError, match="currency_mismatch"):
        parse_campaign_summary(export(rows=[ROWS[0], row]))


@pytest.mark.parametrize(
    "period",
    [
        "",
        "Last week",
        "31 лютого 2026 р. – 7 березня 2026 р.",
        "07.11.2026 - 01.11.2026",
        "01.13.2026 - 07.13.2026",
    ],
)
def test_invalid_or_ambiguous_periods_rejected(period):
    with pytest.raises(InputError, match="invalid_report_period"):
        parse_campaign_summary(export(period=period))


@pytest.mark.parametrize(
    "data,code",
    [
        (b"\xff", "invalid_encoding"),
        (b"\x00", "invalid_csv"),
        (b"x" * (10 * 1024 * 1024 + 1), "file_too_large"),
        (export(title="Search terms"), "unsupported_report_type"),
        (export(headers=HEADERS + ["День"]), "unsupported_report_grain"),
        (export(headers=HEADERS + ["Кампанія"]), "invalid_headers"),
        (export(headers=["Кампанія", "Покази"]), "missing_required_columns"),
        (export(headers=HEADERS + ["x" * 257]), "header_too_long"),
        (export(headers=[f"c{i}" for i in range(201)]), "too_many_columns"),
        (export(rows=[ROWS[0][:-1]]), "inconsistent_columns"),
        (export(rows=[ROWS[0] + ["extra"]]), "inconsistent_columns"),
        (export(rows=[ROWS[0][:-1] + ["x" * 32769]]), "cell_too_large"),
        (export(rows=[]), "empty_report"),
        (export(rows=ROWS[2:]), "empty_report"),
        (export() + b"\n", "inconsistent_columns"),
        (export() + b'"unfinished', "invalid_csv"),
        (b"", "invalid_report_layout"),
    ],
)
def test_invalid_layouts_have_stable_errors(data, code):
    with pytest.raises(InputError) as error:
        parse_campaign_summary(data)
    assert error.value.code == code


def test_row_limit_includes_totals(monkeypatch):
    monkeypatch.setattr("paw.tools.google_ads_csv.MAX_ROWS", 3)
    with pytest.raises(InputError, match="too_many_rows"):
        parse_campaign_summary(export())


def test_generic_csv_behavior_is_unchanged():
    assert inspect_csv(b"campaign,cost\nSynthetic,1.20\n").row_count == 1
    with pytest.raises(InputError, match="inconsistent_columns"):
        inspect_csv(export())


@pytest.mark.parametrize("campaign_cell", ["", " --", "Synthetic Alpha"])
def test_native_status_totals_keep_label_and_source_without_becoming_details(campaign_cell):
    header = ["Статус кампанії"] + HEADERS
    total = ROWS[2].copy()
    total[0] = campaign_cell
    report = parse_campaign_summary(
        export(
            headers=header,
            rows=[["Увімкнено"] + ROWS[0], [" Усього: Кампанії "] + total],
        )
    )
    assert len(report.details) == len(report.totals) == 1
    assert report.details[0].campaign == "Synthetic Alpha"
    assert report.details[0].summary_label is None
    summary = report.totals[0]
    assert summary.summary_label == "Усього: Кампанії"
    assert summary.campaign == (campaign_cell if campaign_cell == "Synthetic Alpha" else None)
    assert summary.raw_cells == tuple([" Усього: Кампанії "] + total)
    assert summary.line_start == summary.line_end == 5
    assert summary.cost == report.details[0].cost == Decimal("24.60")


def test_legacy_campaign_label_is_not_a_campaign_identity():
    report = parse_campaign_summary(export())
    assert report.totals[0].summary_label == "Усього: Кампанії"
    assert report.totals[0].campaign is None


def test_summary_text_in_unrelated_column_does_not_hide_a_detail_row():
    row = ROWS[0].copy()
    row[-1] = "Усього: literal note"
    report = parse_campaign_summary(export(rows=[row]))
    assert len(report.details) == 1
    assert not report.totals


def test_missing_campaign_marker_is_invalid_for_detail():
    row = ROWS[0].copy()
    row[0] = " --"
    with pytest.raises(InputError, match="missing_campaign"):
        parse_campaign_summary(export(rows=[row]))


def test_conflicting_structural_summary_labels_are_rejected():
    with pytest.raises(InputError, match="ambiguous_summary"):
        parse_campaign_summary(
            export(
                headers=["Статус кампанії"] + HEADERS,
                rows=[["Усього: Different scope"] + ROWS[2]],
            )
        )


def daily_export(rows=None, delimiter=","):
    if rows is None:
        rows = [
            ["2026-11-01", "Увімкнено"] + ROWS[0],
            ["2026-11-01", "Увімкнено"] + ROWS[1],
            ["2026-11-01", "Усього: Кампанії", " --"] + ROWS[2][1:],
            [" --", "Усього: Обліковий запис", ""] + ROWS[3][1:],
        ]
    return export(headers=["День", "Статус кампанії"] + HEADERS, rows=rows, delimiter=delimiter)


def test_daily_profile_preserves_grain_dates_and_both_total_levels():
    data = daily_export()
    report = parse_campaign_daily(data)
    assert report.report_type == "campaign_daily"
    assert report.source_sha256 == sha256(data).hexdigest()
    assert len(report.details) == 2
    assert len(report.totals) == 2
    assert [r.campaign for r in report.details] == ["Synthetic Alpha", "Synthetic Beta"]
    assert all(r.day == date(2026, 11, 1) for r in report.details)
    assert report.totals[0].day == date(2026, 11, 1)
    assert report.totals[1].day is None
    assert all(r.campaign is None and r.summary_label for r in report.totals)
    assert report.details[0].conversions == Decimal("1.25")
    assert report.details[0].raw_cells[:2] == ("2026-11-01", "Увімкнено")
    assert report.details[0].line_start == 4
    assert report.details[1].line_end == 6  # Multiline cell still has correct provenance.
    assert sum(r.cost for r in report.details) == Decimal("24.60")
    assert "duplicate_daily_rows" not in report.warnings


@pytest.mark.parametrize(
    "text,code",
    [
        ("", "missing_report_day"),
        (" --", "missing_report_day"),
        ("2026-02-30", "invalid_report_day"),
        ("2026-11-1", "invalid_report_day"),
        ("01.11.2026", "invalid_report_day"),
        ("2026-10-31", "report_day_out_of_period"),
        ("2026-11-08", "report_day_out_of_period"),
    ],
)
def test_daily_detail_requires_a_valid_day_in_report_period(text, code):
    with pytest.raises(InputError) as error:
        parse_campaign_daily(daily_export([[text, "Увімкнено"] + ROWS[0]]))
    assert str(error.value) == code


def test_daily_summary_dates_are_validated_too():
    with pytest.raises(InputError, match="report_day_out_of_period"):
        parse_campaign_daily(
            daily_export(
                [
                    ["2026-11-01", "Увімкнено"] + ROWS[0],
                    ["2026-11-08", "Усього: Кампанії", ""] + ROWS[2][1:],
                ]
            )
        )


def test_daily_duplicate_keys_are_preserved_and_flagged_without_aggregation():
    first = ["2026-11-01", "Увімкнено"] + ROWS[0]
    second = ["2026-11-07", "Увімкнено"] + ROWS[0]
    report = parse_campaign_daily(daily_export([first, first, second]))
    assert len(report.details) == 3
    assert report.details[2].day == date(2026, 11, 7)
    assert report.warnings.count("duplicate_daily_rows") == 1
    assert report.details[0].raw_cells == report.details[1].raw_cells
    assert report.details[0].line_start != report.details[1].line_start


def test_daily_profile_does_not_require_every_day_or_equal_totals():
    # Missing dates are uncollected coverage, not fabricated zero-activity rows.
    report = parse_campaign_daily(
        daily_export(
            [
                ["2026-11-01", "Увімкнено"] + ROWS[0],
                ["2026-11-07", "Увімкнено"] + ROWS[1],
                ["", "Усього: Кампанії", ""] + ["9999", "999", "99,99"] + ROWS[2][4:],
            ]
        )
    )
    assert len(report.details) == 2
    assert report.totals[0].cost == Decimal("99.99")
    assert "coverage_unverified" in report.warnings


def test_campaign_profiles_remain_explicit_and_delimiter_is_not_guessed():
    with pytest.raises(InputError, match="unsupported_report_grain"):
        parse_campaign_summary(daily_export())
    with pytest.raises(InputError, match="missing_required_columns"):
        parse_campaign_daily(export())
    assert parse_campaign_daily(daily_export(delimiter=";"), ";").delimiter == ";"
    assert all(r.day is None for r in parse_campaign_summary(export()).details)


KEYWORD_HEADERS = [
    "Статус ключового слова",
    "Ключове слово",
    "Тип відповідності",
    "Група оголошень",
] + HEADERS
KEYWORD_ROW = [
    "Увімкнено",
    '"synthetic phrase"',
    "Фразова відповідність",
    "Synthetic Group",
] + ROWS[0]


def keyword_export(rows=None, headers=None, delimiter=","):
    return export(
        title="Звіт про ключові слова для пошуку",
        headers=KEYWORD_HEADERS if headers is None else headers,
        rows=[KEYWORD_ROW] if rows is None else rows,
        delimiter=delimiter,
    )


def test_keywords_preserve_identity_source_and_uah_metrics_with_separate_totals():
    total = ["Усього: Активні ключові слова", "", " --", ""] + [" --"] + ROWS[2][1:]
    data = keyword_export(rows=[KEYWORD_ROW, total, total])
    report = parse_search_keywords(data)
    assert report.report_type == "search_keywords"
    assert report.currency == "UAH"
    assert report.source_sha256 == sha256(data).hexdigest()
    assert report.headers == tuple(KEYWORD_HEADERS)
    assert len(report.details) == 1 and len(report.totals) == 2
    row = report.details[0]
    assert row.raw_cells == tuple(KEYWORD_ROW)
    assert row.keyword == '"synthetic phrase"'
    assert row.match_type == "phrase"
    assert row.ad_group == "Synthetic Group"
    assert row.keyword_status == "Увімкнено"
    assert row.campaign == "Synthetic Alpha" and row.day is None
    assert row.impressions == 1234 and row.clicks == 12
    assert row.cost == Decimal("24.60") and row.conversions == Decimal("1.25")
    assert row.line_start == row.line_end == 4
    assert all(t.keyword is t.ad_group is t.match_type is t.campaign is None for t in report.totals)
    assert report.totals[0].summary_label == "Усього: Активні ключові слова"
    assert "duplicate_keyword_rows" not in report.warnings


@pytest.mark.parametrize(
    "source,normalized",
    [
        ("Точна відповідність", "exact"),
        ("Фразова відповідність", "phrase"),
        ("Широка відповідність", "broad"),
    ],
)
def test_keyword_match_types_are_explicit_and_text_is_not_executed(source, normalized):
    row = KEYWORD_ROW.copy()
    row[1] = "[=literal\nsource]"
    row[2] = source
    parsed = parse_search_keywords(keyword_export(rows=[row])).details[0]
    assert parsed.match_type == normalized
    assert parsed.keyword == row[1]
    assert parsed.line_end == 5


@pytest.mark.parametrize(
    "index,value,code",
    [
        (1, " --", "missing_keyword"),
        (3, "", "missing_ad_group"),
        (2, "Unknown", "unsupported_match_type"),
        (4, "--", "missing_campaign"),
        (7, "NaN", "invalid_numeric"),
        (8, "uah", "invalid_currency"),
    ],
)
def test_invalid_keyword_rows_fail_with_safe_codes(index, value, code):
    row = KEYWORD_ROW.copy()
    row[index] = value
    with pytest.raises(InputError) as error:
        parse_search_keywords(keyword_export(rows=[row]))
    assert str(error.value) == code


def test_keyword_duplicates_preserved_but_different_groups_and_match_types_are_distinct():
    other_group = KEYWORD_ROW.copy()
    other_group[3] = "Synthetic Other Group"
    other_match = KEYWORD_ROW.copy()
    other_match[2] = "Точна відповідність"
    distinct = [KEYWORD_ROW, other_group, other_match]
    assert (
        "duplicate_keyword_rows"
        not in parse_search_keywords(keyword_export(rows=distinct)).warnings
    )
    report = parse_search_keywords(keyword_export(rows=distinct + [KEYWORD_ROW]))
    assert len(report.details) == 4
    assert "duplicate_keyword_rows" in report.warnings


def test_keyword_coverage_is_unverified_and_unequal_totals_are_retained():
    total = ["Усього: Обліковий запис", "", "", "", ""] + ROWS[2][1:]
    total[7] = "999,00"
    report = parse_search_keywords(keyword_export(rows=[KEYWORD_ROW, total]))
    assert report.totals[0].cost == Decimal("999.00")
    assert report.details[0].cost == Decimal("24.60")
    assert "coverage_unverified" in report.warnings


def test_keyword_profile_validation_and_shared_limits(monkeypatch):
    assert parse_search_keywords(keyword_export(delimiter=";"), ";").currency == "UAH"
    with pytest.raises(InputError, match="unsupported_report_type"):
        parse_search_keywords(export())
    with pytest.raises(InputError, match="missing_required_columns"):
        parse_search_keywords(keyword_export(headers=KEYWORD_HEADERS[1:3] + HEADERS))
    with pytest.raises(InputError, match="unsupported_report_grain"):
        parse_search_keywords(keyword_export(headers=KEYWORD_HEADERS + ["Пошуковий запит"]))
    with pytest.raises(InputError, match="inconsistent_columns"):
        parse_search_keywords(keyword_export(rows=[KEYWORD_ROW[:-1]]))
    monkeypatch.setattr("paw.tools.google_ads_csv.MAX_ROWS", 1)
    with pytest.raises(InputError, match="too_many_rows"):
        parse_search_keywords(keyword_export(rows=[KEYWORD_ROW, KEYWORD_ROW]))


def test_currency_is_read_from_source_without_conversion_or_uah_default():
    row = KEYWORD_ROW.copy()
    row[8] = "USD"
    report = parse_search_keywords(keyword_export(rows=[row]))
    assert report.currency == "USD" and report.details[0].cost == Decimal("24.60")
    row[8] = "--"
    report = parse_search_keywords(keyword_export(rows=[row]))
    assert report.currency is None and "currency_unverified" in report.warnings


TERM_HEADERS = [
    "Пошуковий запит",
    "Тип відповідності",
    "Додано або виключено",
    "Група оголошень",
    "Ключове слово",
] + HEADERS
TERM_ROW = [
    "synthetic query",
    "Точна відповідність (наближений варіант)",
    "Немає",
    "Synthetic Group",
    "[synthetic keyword]",
] + ROWS[0]


def term_export(rows=None, headers=None, delimiter=","):
    return export(
        title='Звіт "Пошукові терміни"',
        headers=TERM_HEADERS if headers is None else headers,
        rows=[TERM_ROW] if rows is None else rows,
        delimiter=delimiter,
    )


def term_total(label, cost):
    row = [label, " --", "", "", "", " --"] + ROWS[2][1:]
    row[8] = cost
    return row


def test_search_terms_preserve_queries_links_and_other_terms_without_double_counting():
    rows = [
        TERM_ROW,
        term_total("Усього: Пошукові терміни", "24,60"),
        term_total("Усього: Інші пошукові терміни", "75,40"),
        term_total("Усього: Обліковий запис", "100,00"),
    ]
    data = term_export(rows=rows)
    r = parse_search_terms(data)
    assert r.report_type == "search_terms" and r.currency == "UAH"
    assert r.headers == tuple(TERM_HEADERS) and r.source_sha256 == sha256(data).hexdigest()
    assert len(r.details) == 1 and len(r.totals) == 3
    detail = r.details[0]
    assert detail.search_term == "synthetic query"
    assert detail.keyword == "[synthetic keyword]"
    assert detail.ad_group == "Synthetic Group" and detail.campaign == "Synthetic Alpha"
    assert detail.match_type == "exact" and detail.close_variant is True
    assert detail.match_type_text == TERM_ROW[1] and detail.added_or_excluded == "Немає"
    assert detail.raw_cells == tuple(TERM_ROW) and detail.line_start == detail.line_end == 4
    assert detail.conversions == Decimal("1.25")
    assert sum(x.cost for x in r.details) == Decimal("24.60")
    assert r.totals[1].summary_label == "Усього: Інші пошукові терміни"
    assert r.totals[1].cost == Decimal("75.40")
    assert all(x.search_term is x.keyword is x.ad_group is x.match_type is None for x in r.totals)
    assert "coverage_unverified" in r.warnings


@pytest.mark.parametrize(
    "label,base,close",
    [
        ("Точна відповідність", "exact", False),
        ("Фразова відповідність", "phrase", False),
        ("Широка відповідність", "broad", False),
        ("Точна відповідність (наближений варіант)", "exact", True),
        ("Фразова відповідність (наближений варіант)", "phrase", True),
    ],
)
def test_search_match_types_distinguish_close_variants(label, base, close):
    row = TERM_ROW.copy()
    row[1] = label
    row[0] = '=literal\n"query"'
    d = parse_search_terms(term_export(rows=[row])).details[0]
    assert d.match_type == base and d.close_variant is close
    assert d.search_term == row[0] and d.line_end == 5


@pytest.mark.parametrize(
    "index,value,code",
    [
        (0, " --", "missing_search_term"),
        (3, "", "missing_ad_group"),
        (5, "", "missing_campaign"),
        (1, "Unknown", "unsupported_match_type"),
        (8, "=1+1", "invalid_numeric"),
        (9, "uah", "invalid_currency"),
    ],
)
def test_invalid_search_term_rows_have_safe_errors(index, value, code):
    row = TERM_ROW.copy()
    row[index] = value
    with pytest.raises(InputError) as error:
        parse_search_terms(term_export(rows=[row]))
    assert str(error.value) == code


def test_missing_keyword_link_is_disclosed_and_never_invented():
    row = TERM_ROW.copy()
    row[4] = "--"
    r = parse_search_terms(term_export(rows=[row]))
    assert r.details[0].keyword is None and "keyword_link_unavailable" in r.warnings
    r = parse_search_terms(
        term_export(headers=TERM_HEADERS[:4] + TERM_HEADERS[5:], rows=[TERM_ROW[:4] + TERM_ROW[5:]])
    )
    assert r.details[0].keyword is None and "keyword_link_unavailable" in r.warnings


def test_search_terms_with_only_undisclosed_activity_are_valid():
    r = parse_search_terms(
        term_export(
            rows=[
                term_total("Усього: Інші пошукові терміни", "100,00"),
                term_total("Усього: Обліковий запис", "100,00"),
            ]
        )
    )
    assert not r.details and len(r.totals) == 2
    assert r.totals[0].cost == Decimal("100.00")
    assert "coverage_unverified" in r.warnings
    with pytest.raises(InputError, match="empty_report"):
        parse_search_terms(term_export(rows=[]))


def test_search_duplicates_preserved_and_different_keyword_links_are_distinct():
    other = TERM_ROW.copy()
    other[4] = "[synthetic other]"
    r = parse_search_terms(term_export(rows=[TERM_ROW, other]))
    assert "duplicate_search_term_rows" not in r.warnings
    r = parse_search_terms(term_export(rows=[TERM_ROW, other, TERM_ROW]))
    assert len(r.details) == 3 and "duplicate_search_term_rows" in r.warnings


def test_search_profile_limits_and_discrepancies_are_explicit(monkeypatch):
    r = parse_search_terms(
        term_export(rows=[TERM_ROW, term_total("Усього: Пошукові терміни", "7,00")])
    )
    assert r.totals[0].cost == Decimal("7.00")  # Discrepancy is data, not parser failure.
    assert parse_search_terms(term_export(delimiter=";"), ";").currency == "UAH"
    with pytest.raises(InputError, match="unsupported_report_type"):
        parse_search_terms(keyword_export())
    with pytest.raises(InputError, match="missing_required_columns"):
        parse_search_terms(term_export(headers=TERM_HEADERS[1:]))
    with pytest.raises(InputError, match="unsupported_report_grain"):
        parse_search_terms(term_export(headers=TERM_HEADERS + ["День"]))
    with pytest.raises(InputError, match="inconsistent_columns"):
        parse_search_terms(term_export(rows=[TERM_ROW[:-1]]))
    monkeypatch.setattr("paw.tools.google_ads_csv.MAX_ROWS", 1)
    with pytest.raises(InputError, match="too_many_rows"):
        parse_search_terms(term_export(rows=[TERM_ROW, TERM_ROW]))
