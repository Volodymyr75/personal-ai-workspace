"""Bounded Ukrainian Google Ads parsers; no persistence, aggregation or AI."""

import csv
import io
import re
from datetime import date
from decimal import Decimal
from hashlib import sha256

from paw.domain.files import (
    MAX_CELL_CHARS,
    MAX_COLUMNS,
    MAX_FILE_BYTES,
    MAX_ROWS,
    InputError,
)
from paw.domain.google_ads import GoogleAdsReport, GoogleAdsRow, MatchType, ReportType

_MONTHS = (
    "січня",
    "лютого",
    "березня",
    "квітня",
    "травня",
    "червня",
    "липня",
    "серпня",
    "вересня",
    "жовтня",
    "листопада",
    "грудня",
)
_REQUIRED = {"Кампанія", "Покази", "Кліки", "Вартість"}
_OTHER_GRAINS = {
    "День",
    "Дата",
    "Пошуковий термін",
    "Пошуковий запит",
    "Ключове слово",
    "Ключове слово для пошуку",
}
_MATCH_TYPES: dict[str, MatchType] = {
    "Точна відповідність": "exact",
    "Фразова відповідність": "phrase",
    "Широка відповідність": "broad",
}


def _date(text: str) -> date:
    numeric = re.fullmatch(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", text)
    localized = re.fullmatch(r"(\d{1,2}) (\w+) (\d{4})(?: р\.)?", text)
    try:
        if numeric:
            day, month, year = map(int, numeric.groups())
            return date(year, month, day)
        if localized and localized[2] in _MONTHS:
            return date(int(localized[3]), _MONTHS.index(localized[2]) + 1, int(localized[1]))
    except ValueError:
        pass
    raise InputError("invalid_report_period")


def _period(text: str) -> tuple[date, date]:
    normalized = " ".join(text.split())
    parts = re.split(r"\s+[–—-]\s+", normalized)
    if len(parts) != 2:
        raise InputError("invalid_report_period")
    start, end = map(_date, parts)
    if start > end:
        raise InputError("invalid_report_period")
    return start, end


def _number(text: str, *, integer: bool = False, percent: bool = False) -> Decimal | None:
    value = text.strip()
    if value in ("", "--"):
        return None
    if percent:
        if not value.endswith("%"):
            raise InputError("invalid_numeric")
        value = value[:-1].rstrip()
    # Grouping spaces must separate groups of three, never silently delete arbitrary spaces.
    if not re.fullmatch(r"(?:\d+|\d{1,3}(?:[ \u00a0\u202f]\d{3})+)(?:,\d+)?", value):
        raise InputError("invalid_numeric")
    normalized = re.sub(r"[ \u00a0\u202f]", "", value).replace(",", ".")
    result = Decimal(normalized)
    if result > Decimal("1e15"):
        raise InputError("numeric_overflow")
    if integer and result != result.to_integral_value():
        raise InputError("invalid_numeric")
    if percent and result > 100:
        raise InputError("invalid_numeric")
    return result


def parse_campaign_summary(data: bytes, delimiter: str = ",") -> GoogleAdsReport:
    """Parse the aggregate campaign profile; daily input is explicitly rejected."""
    return _parse_report(data, delimiter, "campaign_summary")


def parse_campaign_daily(data: bytes, delimiter: str = ",") -> GoogleAdsReport:
    """Parse the daily campaign profile, retaining dated and undated totals."""
    return _parse_report(data, delimiter, "campaign_daily")


def parse_search_keywords(data: bytes, delimiter: str = ",") -> GoogleAdsReport:
    """Parse search keyword exports; keyword text is preserved without interpretation."""
    return _parse_report(data, delimiter, "search_keywords")


def parse_search_terms(data: bytes, delimiter: str = ",") -> GoogleAdsReport:
    """Parse visible queries and retain other-term/account totals without allocation."""
    return _parse_report(data, delimiter, "search_terms")


def _parse_report(data: bytes, delimiter: str, report_type: ReportType) -> GoogleAdsReport:
    """Parse only the documented two-preamble-row Google Ads profiles.

    Original bytes remain the caller's responsibility. Raw cells and physical line
    references preserve provenance; normalized values never replace source text.
    Unknown columns are retained as text. Unsupported profiles fail explicitly.
    """
    if len(data) > MAX_FILE_BYTES:
        raise InputError("file_too_large")
    if delimiter not in (",", ";"):
        raise InputError("invalid_delimiter")
    try:
        content = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise InputError("invalid_encoding") from None
    if any(ord(c) < 32 and c not in "\r\n\t" or ord(c) == 127 for c in content):
        raise InputError("invalid_csv")
    reader = csv.reader(io.StringIO(content, newline=""), delimiter=delimiter, strict=True)

    def read() -> list[str]:
        try:
            row = next(reader)
        except StopIteration:
            raise InputError("invalid_report_layout") from None
        except csv.Error:
            raise InputError("invalid_csv") from None
        if len(row) > MAX_COLUMNS:
            raise InputError("too_many_columns")
        if any(len(cell) > MAX_CELL_CHARS for cell in row):
            raise InputError("cell_too_large")
        return row

    title = read()
    period = read()
    keywords = report_type == "search_keywords"
    terms = report_type == "search_terms"
    expected_title = "Звіт про кампанію"
    if terms:
        expected_title = 'Звіт "Пошукові терміни"'
    elif keywords:
        expected_title = "Звіт про ключові слова для пошуку"
    if len(title) != 1 or title[0].strip() != expected_title:
        raise InputError("unsupported_report_type")
    if len(period) != 1:
        raise InputError("invalid_report_layout")
    start, end = _period(period[0])
    headers = read()
    names = [cell.strip() for cell in headers]
    if not names or any(not name for name in names) or len(set(names)) != len(names):
        raise InputError("invalid_headers")
    if any(len(cell) > 256 for cell in headers):
        raise InputError("header_too_long")
    daily = report_type == "campaign_daily"
    allowed_grain: set[str] = set()
    if terms:
        allowed_grain = {"Пошуковий запит", "Ключове слово"}
    elif keywords:
        allowed_grain = {"Ключове слово"}
    elif daily:
        allowed_grain = {"День"}
    unsupported = _OTHER_GRAINS - allowed_grain
    if unsupported.intersection(names):
        raise InputError("unsupported_report_grain")
    extra_required: set[str] = set()
    if keywords or terms:
        extra_required = {"Група оголошень", "Тип відповідності"}
        extra_required.add("Пошуковий запит" if terms else "Ключове слово")
    elif daily:
        extra_required = {"День"}
    if not (_REQUIRED | extra_required).issubset(names):
        raise InputError("missing_required_columns")
    details: list[GoogleAdsRow] = []
    totals: list[GoogleAdsRow] = []
    currencies: set[str] = set()
    missing_currency = False
    daily_keys: set[tuple[str, date]] = set()
    duplicate_daily_rows = False
    keyword_keys: set[tuple[str, str, str, MatchType]] = set()
    duplicate_keyword_rows = False
    term_keys: set[tuple[str, str, str, str | None, str]] = set()
    duplicate_search_term_rows = False
    keyword_link_unavailable = False
    count = 0
    while True:
        line_start = reader.line_num + 1
        # Probe EOF without accepting blank rows or concealing parser failures.
        try:
            cells = read()
        except InputError as error:
            if error.code == "invalid_report_layout" and reader.line_num < line_start:
                break
            raise
        count += 1
        if count > MAX_ROWS:
            raise InputError("too_many_rows")
        if len(cells) != len(headers):
            raise InputError("inconsistent_columns")
        fields = dict(zip(names, cells, strict=True))
        campaign = fields["Кампанія"].strip()
        # Native exports put summary labels in the status column. Limit detection
        # to structural columns: arbitrary source text is never an instruction.
        label_columns: tuple[str, ...]
        if terms:
            label_columns = ("Пошуковий запит", "Кампанія")
        elif keywords:
            label_columns = ("Статус ключового слова", "Ключове слово", "Кампанія")
        else:
            label_columns = ("Статус кампанії", "Кампанія")
        labels = {
            fields.get(column, "").strip()
            for column in label_columns
            if fields.get(column, "").strip().startswith("Усього:")
        }
        if len(labels) > 1:
            raise InputError("ambiguous_summary")
        summary_label = next(iter(labels), None)
        if campaign in ("", "--") and summary_label is None:
            raise InputError("missing_campaign")
        campaign_name = campaign if campaign not in ("", "--") and campaign not in labels else None
        keyword = None
        ad_group = None
        match_type = None
        keyword_status = None
        search_term = None
        match_type_text = None
        close_variant = None
        added_or_excluded = None
        if keywords:
            keyword = fields["Ключове слово"]  # Keep brackets, quotes and readable source text.
            ad_group = fields["Група оголошень"].strip()
            match_text = fields["Тип відповідності"].strip()
            keyword_status = fields.get("Статус ключового слова", "").strip() or None
            if summary_label is None:
                if keyword.strip() in ("", "--"):
                    raise InputError("missing_keyword")
                if ad_group in ("", "--"):
                    raise InputError("missing_ad_group")
                match_type = _MATCH_TYPES.get(match_text)
                if match_type is None:
                    raise InputError("unsupported_match_type")
                assert campaign_name is not None
                keyword_key = (campaign_name, ad_group, keyword, match_type)
                if keyword_key in keyword_keys:
                    duplicate_keyword_rows = True
                keyword_keys.add(keyword_key)
            else:
                # Summary placeholders are not keyword/ad-group identities.
                keyword = None
                ad_group = None
                keyword_status = None
        if terms and summary_label is None:
            search_term = fields["Пошуковий запит"]
            if search_term.strip() in ("", "--"):
                raise InputError("missing_search_term")
            ad_group = fields["Група оголошень"].strip()
            if ad_group in ("", "--"):
                raise InputError("missing_ad_group")
            keyword = fields.get("Ключове слово")
            if keyword is None or keyword.strip() in ("", "--"):
                keyword = None
                keyword_link_unavailable = True
            match_type_text = fields["Тип відповідності"].strip()
            suffix = " (наближений варіант)"
            close_variant = match_type_text.endswith(suffix)
            base_match = match_type_text.removesuffix(suffix)
            match_type = _MATCH_TYPES.get(base_match)
            if match_type is None or (close_variant and match_type == "broad"):
                raise InputError("unsupported_match_type")
            added_or_excluded = fields.get("Додано або виключено", "").strip() or None
            assert campaign_name is not None
            term_key = (campaign_name, ad_group, search_term, keyword, match_type_text)
            if term_key in term_keys:
                duplicate_search_term_rows = True
            term_keys.add(term_key)
        day = None
        if daily:
            text = fields["День"].strip()
            if text in ("", "--"):
                if summary_label is None:
                    raise InputError("missing_report_day")
            else:
                if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", text):
                    raise InputError("invalid_report_day")
                try:
                    day = date.fromisoformat(text)
                except ValueError:
                    raise InputError("invalid_report_day") from None
                if not start <= day <= end:
                    raise InputError("report_day_out_of_period")
            if summary_label is None and campaign_name is not None and day is not None:
                key = (campaign_name, day)
                if key in daily_keys:
                    duplicate_daily_rows = True
                daily_keys.add(key)
        currency = fields.get("Код валюти", "").strip()
        if currency in ("", "--"):
            missing_currency = True
            currency = ""
        elif not re.fullmatch(r"[A-Z]{3}", currency):
            raise InputError("invalid_currency")
        else:
            currencies.add(currency)
        impressions = _number(fields["Покази"], integer=True)
        clicks = _number(fields["Кліки"], integer=True)
        row = GoogleAdsRow(
            line_start=line_start,
            line_end=reader.line_num,
            raw_cells=tuple(cells),
            campaign=campaign_name,
            impressions=int(impressions) if impressions is not None else None,
            clicks=int(clicks) if clicks is not None else None,
            cost=_number(fields["Вартість"]),
            currency=currency or None,
            conversions=_number(fields.get("Конверсії", "")),
            ctr_percent=_number(fields.get("CTR", ""), percent=True),
            average_cpc=_number(fields.get("Сер. ціна за клік", "")),
            summary_label=summary_label,
            day=day,
            keyword=keyword,
            ad_group=ad_group,
            match_type=match_type,
            keyword_status=keyword_status,
            search_term=search_term,
            match_type_text=match_type_text,
            close_variant=close_variant,
            added_or_excluded=added_or_excluded,
        )
        (totals if summary_label is not None else details).append(row)
    # A search-term export can disclose only summary/other-term activity.
    # Do not invent visible queries or reject it solely for zero detail coverage.
    if not details and not (terms and totals):
        raise InputError("empty_report")
    if len(currencies) > 1:
        raise InputError("currency_mismatch")
    return GoogleAdsReport(
        source_sha256=sha256(data).hexdigest(),
        source_size_bytes=len(data),
        title=title[0],
        period_text=period[0],
        period_start=start,
        period_end=end,
        headers=tuple(headers),
        delimiter=delimiter,
        currency=next(iter(currencies)) if currencies and not missing_currency else None,
        details=tuple(details),
        totals=tuple(totals),
        report_type=report_type,
        warnings=("account_scope_unverified", "coverage_unverified")
        + (("currency_unverified",) if missing_currency else ())
        + (("duplicate_daily_rows",) if duplicate_daily_rows else ())
        + (("duplicate_keyword_rows",) if duplicate_keyword_rows else ())
        + (("duplicate_search_term_rows",) if duplicate_search_term_rows else ())
        + (("keyword_link_unavailable",) if keyword_link_unavailable else ()),
    )
