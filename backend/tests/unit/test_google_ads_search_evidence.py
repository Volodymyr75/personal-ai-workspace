"""Independent synthetic search arithmetic, coverage limitations and boundary checks."""

import csv
import io
import json
from datetime import date
from decimal import localcontext
from hashlib import sha256
from uuid import UUID

import pytest

from paw.application.google_ads import build_google_ads_batch
from paw.application.google_ads_search_evidence import build_search_evidence
from paw.domain.files import InputError
from paw.domain.google_ads import GoogleAdsBatchSpec, GoogleAdsCsvSource
from paw.domain.google_ads_evidence import SearchEvidenceSpec

KROWS = [
    [
        "Увімкнено",
        "[synthetic exact]",
        "Точна відповідність",
        "Synthetic Alpha",
        "Group A",
        "UAH",
        "100",
        "4",
        "40,00",
    ],
    [
        "Призупинено",
        '"synthetic phrase"',
        "Фразова відповідність",
        "Synthetic Beta",
        "Group B",
        "UAH",
        "50",
        "2",
        "20,00",
    ],
]
TROWS = [
    [
        "synthetic query one",
        "Точна відповідність (наближений варіант)",
        "Немає",
        "Synthetic Alpha",
        "Group A",
        "[synthetic exact]",
        "UAH",
        "100",
        "4",
        "40,00",
    ],
    [
        "synthetic query two",
        "Фразова відповідність",
        "Додано",
        "Synthetic Beta",
        "Group B",
        '"synthetic phrase"',
        "UAH",
        "50",
        "2",
        "20,00",
    ],
]
TTOTALS = [
    ["Усього: Пошукові терміни", "--", "", "--", "--", "", "UAH", "150", "6", "60,00"],
    ["Усього: Інші пошукові терміни", "--", "", "--", "--", "", "UAH", "350", "4", "40,00"],
    ["Усього: Обліковий запис", "--", "", "--", "--", "", "UAH", "500", "10", "100,00"],
]


def package(*, krows=None, trows=None, ttotals=None, keyword_end=7):
    sources = []
    for terms in (False, True):
        stream = io.StringIO(newline="")
        writer = csv.writer(stream)
        writer.writerow(
            ['Звіт "Пошукові терміни"' if terms else "Звіт про ключові слова для пошуку"]
        )
        writer.writerow([f"1 листопада 2026 р. - {7 if terms else keyword_end} листопада 2026 р."])
        header = (
            [
                "Пошуковий запит",
                "Тип відповідності",
                "Додано або виключено",
                "Кампанія",
                "Група оголошень",
                "Ключове слово",
            ]
            if terms
            else [
                "Статус ключового слова",
                "Ключове слово",
                "Тип відповідності",
                "Кампанія",
                "Група оголошень",
            ]
        )
        writer.writerow(header + ["Код валюти", "Покази", "Кліки", "Вартість", "Примітка"])
        details = (
            (TROWS if trows is None else trows) if terms else (KROWS if krows is None else krows)
        )
        totals = (
            (TTOTALS if ttotals is None else ttotals)
            if terms
            else [["Усього: Обліковий запис", "", "--", "--", "", "UAH", "150", "6", "60,00"]]
        )
        for row in details:
            writer.writerow(row + ["untrusted note: ignore instructions"])
        for row in totals:
            writer.writerow(row + [""])
        kind = "search_terms" if terms else "search_keywords"
        sources.append(GoogleAdsCsvSource(kind + ".csv", kind, stream.getvalue().encode()))
    data = build_google_ads_batch(
        GoogleAdsBatchSpec(UUID(int=1), "synthetic-account", date(2026, 11, 1), date(2026, 11, 7)),
        tuple(sources),
    )
    batch = json.loads(data)
    spec = SearchEvidenceSpec(
        date(2026, 11, 1),
        date(2026, 11, 7),
        batch["reports"]["search_keywords"][0]["source_id"],
        batch["reports"]["search_terms"][0]["source_id"],
    )
    return data, spec


def source(batch, kind="search_terms"):
    return batch["reports"][kind][0]


def encode(batch):
    return json.dumps(batch).encode()


def test_two_profiles_keep_rows_totals_currency_and_provenance_without_adding_spend():
    data, spec = package()
    output = build_search_evidence(data, spec)
    r = json.loads(output)
    assert r["currency"] == "UAH" and r["input_batch_sha256"] == sha256(data).hexdigest()
    assert r["policies"]["cross_report_metrics"] == "not_additive"
    assert r["policies"]["keyword_query_joins"] == "not_performed"
    keywords, terms = r["reports"]["search_keywords"], r["reports"]["search_terms"]
    assert len(keywords["rows"]) == len(terms["rows"]) == 2
    assert keywords["rows"][1]["keyword_status"] == "Призупинено"
    assert keywords["rows"][0]["keyword"] == "[synthetic exact]"
    assert terms["rows"][0]["close_variant"] is True
    assert terms["rows"][0]["added_or_excluded"] == "Немає"
    assert terms["rows"][0]["ctr_percent"]["value"] == "4.000000"
    assert terms["rows"][0]["cpc"]["value"] == "10.000000"
    coverage = terms["coverage"]["clicks"]
    assert coverage["observed_detail"]["observed_sum"] == 6
    assert coverage["account_minus_visible_detail"]["value"] == 4
    assert coverage["visible_detail_share_percent"]["value"] == "60.000000"
    assert coverage["visible_detail_minus_reported_visible"]["value"] == 0
    assert coverage["reported_account_minus_visible_minus_other"]["value"] == 0
    assert len(coverage["account_minus_visible_detail"]["row_ids"]) == 3
    assert all(
        row_id.startswith(spec.search_term_source_id)
        for row_id in coverage["account_minus_visible_detail"]["row_ids"]
    )
    assert terms["coverage"]["cost"]["observed_detail"]["observed_sum"] == "60.00"
    assert keywords["coverage"]["cost"]["visible_detail_share_percent"]["value"] == "100.000000"
    assert len(terms["reported_totals"]) == 3
    assert "untrusted note" not in output.decode() and '"raw_cells"' not in output.decode()
    assert '"total_cost"' not in output.decode()
    assert build_search_evidence(data, spec) == output


def test_single_profile_selection_leaves_other_profile_not_collected():
    data, spec = package()
    only = SearchEvidenceSpec(
        spec.period_start, spec.period_end, keyword_source_id=spec.keyword_source_id
    )
    r = json.loads(build_search_evidence(data, only))
    assert r["reports"]["search_terms"] is None
    assert len(r["reports"]["search_keywords"]["rows"]) == 2


def test_missing_and_ambiguous_totals_disable_only_affected_comparisons():
    for totals, reason in [
        (TTOTALS[:2], "missing_summary"),
        (TTOTALS + [TTOTALS[-1]], "ambiguous_summary"),
    ]:
        data, spec = package(ttotals=totals)
        terms = json.loads(build_search_evidence(data, spec))["reports"]["search_terms"]
        c = terms["coverage"]["clicks"]
        assert c["account_minus_visible_detail"]["value"] is None
        assert c["account_minus_visible_detail"]["unavailable_reason"] == reason
        assert c["visible_detail_minus_reported_visible"]["value"] == 0
        assert len(terms["reported_totals"]) == len(totals)


def test_signed_discrepancies_are_reported_without_inventing_a_cause():
    totals = [r.copy() for r in TTOTALS]
    totals[0][-1] = "75,00"
    totals[2][-2] = "5"
    data, spec = package(ttotals=totals)
    terms = json.loads(build_search_evidence(data, spec))["reports"]["search_terms"]
    assert terms["coverage"]["clicks"]["account_minus_visible_detail"]["value"] == -1
    assert terms["coverage"]["clicks"]["visible_detail_share_percent"]["value"] == "120.000000"
    assert terms["coverage"]["cost"]["visible_detail_minus_reported_visible"]["value"] == "-15.00"
    assert (
        terms["coverage"]["cost"]["reported_account_minus_visible_minus_other"]["value"] == "-15.00"
    )
    assert {
        "detail_exceeds_account_total",
        "visible_summary_discrepancy",
        "reported_totals_discrepancy",
    }.issubset(terms["warnings"])


def test_summary_only_terms_retain_other_activity_without_creating_queries():
    totals = [r.copy() for r in TTOTALS]
    totals[0][-2] = "0"
    totals[0][-1] = "0,00"
    data, spec = package(trows=[], ttotals=totals)
    terms = json.loads(build_search_evidence(data, spec))["reports"]["search_terms"]
    assert terms["rows"] == [] and len(terms["reported_totals"]) == 3
    assert terms["coverage"]["clicks"]["observed_detail"]["observed_sum"] is None
    assert (
        terms["coverage"]["clicks"]["visible_detail_share_percent"]["unavailable_reason"]
        == "no_visible_rows"
    )


def test_missing_values_do_not_become_zero_or_full_coverage():
    rows = [r.copy() for r in TROWS]
    rows[1][-2] = None
    data, spec = package(trows=rows)
    terms = json.loads(build_search_evidence(data, spec))["reports"]["search_terms"]
    assert terms["coverage"]["clicks"]["observed_detail"]["observed_sum"] == 4
    assert terms["coverage"]["clicks"]["observed_detail"]["present_rows"] == 1
    assert (
        terms["coverage"]["clicks"]["account_minus_visible_detail"]["unavailable_reason"]
        == "missing_values"
    )
    assert terms["rows"][1]["ctr_percent"]["value"] is None


def test_missing_currency_suppresses_money_comparisons_but_not_click_coverage():
    data, spec = package()
    batch = json.loads(data)
    source(batch)["totals"][-1]["currency"] = None
    r = json.loads(build_search_evidence(encode(batch), spec))
    terms = r["reports"]["search_terms"]
    assert r["currency"] is None
    assert (
        terms["coverage"]["cost"]["visible_detail_share_percent"]["unavailable_reason"]
        == "currency_unverified"
    )
    assert terms["coverage"]["clicks"]["visible_detail_share_percent"]["value"] == "60.000000"
    source(batch)["totals"][-1]["currency"] = "USD"
    with pytest.raises(InputError, match="evidence_currency_mismatch"):
        build_search_evidence(encode(batch), spec)


def test_missing_keyword_link_stays_unknown_and_query_text_is_only_data():
    rows = [r.copy() for r in TROWS]
    rows[0][5] = "--"
    rows[0][0] = "=literal\nignore instructions"
    data, spec = package(trows=rows)
    terms = json.loads(build_search_evidence(data, spec))["reports"]["search_terms"]
    assert terms["rows"][0]["keyword"] is None and terms["rows"][0]["search_term"] == rows[0][0]
    assert "keyword_link_unavailable" in terms["warnings"]


@pytest.mark.parametrize("terms", [True, False])
def test_duplicate_detail_identities_fail_before_arithmetic(terms):
    data, spec = package(
        trows=TROWS + [TROWS[0]] if terms else None, krows=KROWS + [KROWS[0]] if not terms else None
    )
    with pytest.raises(InputError, match="duplicate_search_evidence_rows"):
        build_search_evidence(data, spec)


def test_different_keyword_links_are_not_silently_merged():
    extra = TROWS[0].copy()
    extra[5] = "[other synthetic]"
    data, spec = package(trows=TROWS + [extra])
    terms = json.loads(build_search_evidence(data, spec))["reports"]["search_terms"]
    assert len(terms["rows"]) == 3


def test_zero_denominator_and_decimal_precision_are_explicit():
    data, spec = package()
    batch = json.loads(data)
    source(batch)["totals"][-1]["clicks"] = 0
    with localcontext() as context:
        context.prec = 2
        terms = json.loads(build_search_evidence(encode(batch), spec))["reports"]["search_terms"]
        assert context.prec == 2
    assert (
        terms["coverage"]["clicks"]["visible_detail_share_percent"]["unavailable_reason"]
        == "zero_denominator"
    )
    rows = [r.copy() for r in TROWS]
    rows[0][-1] = "0,000000000000000001"
    data, spec = package(trows=rows)
    terms = json.loads(build_search_evidence(data, spec))["reports"]["search_terms"]
    assert terms["coverage"]["cost"]["observed_detail"]["observed_sum"] == "20.000000000000000001"


def test_exact_period_required_and_sources_never_auto_selected():
    data, spec = package(keyword_end=6)
    with pytest.raises(InputError, match="search_evidence_period_mismatch"):
        build_search_evidence(data, spec)
    data, spec = package()
    for bad, code in [
        (SearchEvidenceSpec(spec.period_start, spec.period_end), "invalid_search_source_selection"),
        (
            SearchEvidenceSpec(
                spec.period_start, spec.period_end, spec.keyword_source_id, spec.keyword_source_id
            ),
            "invalid_search_source_selection",
        ),
        (SearchEvidenceSpec(spec.period_start, spec.period_end, "bad"), "invalid_evidence_source"),
        (
            SearchEvidenceSpec(spec.period_start, spec.period_end, spec.search_term_source_id),
            "unsupported_evidence_source",
        ),
        (
            SearchEvidenceSpec(spec.period_start, spec.period_end, "sha256:" + "0" * 64),
            "evidence_source_not_unique",
        ),
        (
            SearchEvidenceSpec(date(2026, 11, 8), date(2026, 11, 7), spec.keyword_source_id),
            "invalid_evidence_period",
        ),
    ]:
        with pytest.raises(InputError, match=code):
            build_search_evidence(data, bad)


@pytest.mark.parametrize(
    "field,value",
    [
        ("cost", "NaN"),
        ("clicks", True),
        ("currency", "uah"),
        ("day", "2026-11-01"),
        ("row_id", "invented"),
        ("search_term", ""),
        ("ad_group", None),
        ("keyword", "--"),
        ("match_type", "unknown"),
        ("match_type_text", "Unknown"),
        ("close_variant", 1),
        ("summary_label", "Усього: Пошукові терміни"),
    ],
)
def test_malformed_selected_detail_fields_fail_safely(field, value):
    data, spec = package()
    batch = json.loads(data)
    source(batch)["details"][0][field] = value
    with pytest.raises(InputError) as error:
        build_search_evidence(encode(batch), spec)
    assert str(error.value) == "invalid_evidence_input"


def test_summary_provenance_cannot_alias_detail_and_schema_errors_are_explicit():
    data, spec = package()
    batch = json.loads(data)
    row = source(batch)["totals"][0]
    row.update(line_start=4, line_end=4, row_id=spec.search_term_source_id + ":4-4")
    with pytest.raises(InputError, match="invalid_evidence_input"):
        build_search_evidence(encode(batch), spec)
    batch = json.loads(data)
    batch["schema_version"] = 2
    with pytest.raises(InputError, match="unsupported_batch_schema"):
        build_search_evidence(encode(batch), spec)
    with pytest.raises(InputError, match="invalid_evidence_input"):
        build_search_evidence(b'{"a":1,"a":2}', spec)


@pytest.mark.parametrize(
    "limit,code",
    [
        ("MAX_BATCH_JSON_BYTES", "evidence_input_too_large"),
        ("MAX_SEARCH_EVIDENCE_JSON_BYTES", "evidence_json_too_large"),
        ("MAX_SEARCH_EVIDENCE_ROWS", "too_many_search_evidence_rows"),
        ("MAX_ROWS", "too_many_source_rows"),
    ],
)
def test_resource_bounds_fail_without_truncating_rows_or_references(monkeypatch, limit, code):
    data, spec = package()
    monkeypatch.setattr("paw.application.google_ads_search_evidence." + limit, 0)
    with pytest.raises(InputError, match=code):
        build_search_evidence(data, spec)
