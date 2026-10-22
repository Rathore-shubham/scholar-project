"""Missing values, numbers, dates, URLs, states and list splitting."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from scholarpath_data.parsers import (
    clean_text,
    extract_urls,
    government_level_to_scheme_type,
    is_government_domain,
    is_valid_url,
    match_key,
    parse_academic_year,
    parse_amount,
    parse_date,
    parse_income,
    parse_number,
    parse_percentage,
    parse_url_cell,
    resolve_states,
    split_list,
)


# ----------------------------------------------------------------- missing values
@pytest.mark.parametrize(
    "value",
    [None, "", "   ", " ", "nan", "NaN", "None", "null", "N/A", "NA", "n.a.", "-", "--", "—", "?",
     "Nil", "unknown", "Not Available", "TBD", float("nan"), float("inf"), "​"],
)
def test_missing_value_representations_become_none(value: object) -> None:
    assert clean_text(value) is None


def test_clean_text_trims_and_collapses_whitespace() -> None:
    assert clean_text("  PM   YASASVI \n scheme\t") == "PM YASASVI scheme"
    assert clean_text(12.0) == "12"
    assert clean_text(0.5) == "0.5"
    assert clean_text(80) == "80"


def test_real_zero_is_not_treated_as_missing() -> None:
    assert clean_text(0) == "0"
    assert parse_number(0) == 0.0
    assert parse_income(0).value == 0.0  # an explicit 0 is kept; only *missing* is never 0


def test_missing_income_is_none_not_zero() -> None:
    for blank in (None, "", "NA", float("nan")):
        result = parse_income(blank)
        assert result.value is None and result.status == "missing"


# ----------------------------------------------------------------- numbers
@pytest.mark.parametrize(
    "text, expected",
    [
        ("12,000", 12000), ("3,00,000", 300000), ("8,00,000", 800000), ("1,234,567", 1234567),
        ("120000", 120000), ("₹50,000", 50000), ("Rs. 5,000", 5000), ("INR 2500", 2500),
        ("3 Lakh", 300000), ("1.5 lakhs", 150000), ("2 crore", 20000000), ("50,000/-", 50000),
        ("-5000", -5000), ("12.5", 12.5), (50000, 50000), (80.0, 80),
    ],
)
def test_parse_number_accepts_indian_and_western_grouping(text: object, expected: float) -> None:
    assert parse_number(text) == expected


@pytest.mark.parametrize("text", ["12,34", "1,2,3", "abc", "12 000", "GIRLS - 3,000", "12,000 per year", True])
def test_parse_number_rejects_anything_not_a_single_plain_number(text: object) -> None:
    assert parse_number(text) is None


def test_amount_single_number_sets_min_and_max() -> None:
    r = parse_amount("50,000")
    assert (r.minimum, r.maximum, r.status) == (50000, 50000, "ok")
    assert parse_amount(12000).maximum == 12000


def test_amount_explicit_range() -> None:
    r = parse_amount("2,000 - 11,000")
    assert (r.minimum, r.maximum, r.status) == (2000, 11000, "ok")
    assert parse_amount("5000 to 1000").minimum == 1000  # order-insensitive


@pytest.mark.parametrize("text", ["GIRLS - 3,000 ; BOYS - 2,500", "12,000(first 3yrs); 20,000 (post graduation)", "up to 5 lakh per year"])
def test_amount_tiered_or_worded_text_is_ambiguous_not_guessed(text: str) -> None:
    r = parse_amount(text)
    assert (r.minimum, r.maximum, r.status) == (None, None, "ambiguous")


def test_amount_missing() -> None:
    assert parse_amount(None).status == "missing"
    assert parse_amount(float("nan")).status == "missing"


@pytest.mark.parametrize(
    "text, value, comparator",
    [("<8,00,000", 800000, "<"), ("< 4,50,000", 450000, "<"), ("2,50,000", 250000, None), (600000, 600000, None),
     ("up to 3 lakh", 300000, "<="), ("≤ 1,00,000", 100000, "<="), ("Below Rs. 2,50,000", 250000, "<"),
     ("max 8,00,000", 800000, "<=")],
)
def test_income_parsing_keeps_comparator(text: object, value: float, comparator: str | None) -> None:
    r = parse_income(text)
    assert (r.value, r.comparator, r.status) == (value, comparator, "ok")


@pytest.mark.parametrize(
    "text",
    ["SC/ST - 2,50,000 ; 0BC - 1,50,000/8,00,000", "1,00,000 -2,50,000", "HIGHER ED. - 120000,SCHOOL-54000"],
)
def test_income_category_specific_ranges_and_tiers_are_ambiguous(text: str) -> None:
    r = parse_income(text)
    assert r.value is None and r.status == "ambiguous"


@pytest.mark.parametrize("value, expected", [(80, 80.0), ("60", 60.0), ("60%", 60.0), ("72.5 %", 72.5), (0.6, 0.6), (150, 150.0), ("-5", -5.0)])
def test_percentage_ok(value: object, expected: float) -> None:
    assert parse_percentage(value) == (expected, "ok")


@pytest.mark.parametrize("value", ["MP BOARD-60", "MP board- 70,CBSE - 85", "first class"])
def test_percentage_board_specific_is_ambiguous(value: str) -> None:
    assert parse_percentage(value) == (None, "ambiguous")


def test_percentage_missing() -> None:
    assert parse_percentage(None) == (None, "missing")
    assert parse_percentage(float("nan")) == (None, "missing")


# ----------------------------------------------------------------- dates
@pytest.mark.parametrize(
    "value, expected",
    [
        ("2026-03-31", date(2026, 3, 31)), ("2026/3/5", date(2026, 3, 5)), ("2026-03-31T10:00:00Z", date(2026, 3, 31)),
        ("31/03/2026", date(2026, 3, 31)), ("03/31/2026", date(2026, 3, 31)), ("05/05/2026", date(2026, 5, 5)),
        ("31 March 2026", date(2026, 3, 31)), ("31-Mar-2026", date(2026, 3, 31)), ("1st Sept 2026", date(2026, 9, 1)),
        ("March 31, 2026", date(2026, 3, 31)), ("Mar 5 2026", date(2026, 3, 5)),
        (datetime(2026, 3, 31, 9, 30), date(2026, 3, 31)), (date(2026, 3, 31), date(2026, 3, 31)),
    ],
)
def test_unambiguous_dates_are_parsed(value: object, expected: date) -> None:
    result = parse_date(value)
    assert (result.value, result.status) == (expected, "ok")


@pytest.mark.parametrize("value", ["03/04/2026", "12-11-2026", "01.02.2026"])
def test_day_month_ambiguous_dates_are_not_guessed(value: str) -> None:
    result = parse_date(value)
    assert result.value is None and result.status == "ambiguous"


@pytest.mark.parametrize("value", ["2026-02-30", "31/02/2026", "45/45/2026", "31 Feb 2026"])
def test_impossible_dates_are_invalid(value: str) -> None:
    assert parse_date(value).status == "invalid"


@pytest.mark.parametrize("value", ["rolling", "Open throughout the year", "March", "45678", "tomorrow", 45678.0])
def test_non_dates_are_unparsed(value: object) -> None:
    result = parse_date(value)
    assert result.value is None and result.status == "unparsed"


def test_missing_dates() -> None:
    for blank in (None, "", "NA", float("nan")):
        assert parse_date(blank).status == "missing"


@pytest.mark.parametrize(
    "value, expected",
    [("2024-25", "2024-25"), ("2024-2025", "2024-25"), ("AY 2024-25", "2024-25"), ("2024/25", "2024-25"), ("2099-00", "2099-00")],
)
def test_academic_year(value: str, expected: str) -> None:
    assert parse_academic_year(value) == (expected, "ok")


@pytest.mark.parametrize("value", ["2024", "2024-26", "2024-2027", "24-25", "this year"])
def test_academic_year_ambiguous_or_wrong_is_not_guessed(value: str) -> None:
    assert parse_academic_year(value) == (None, "unparsed")


# ----------------------------------------------------------------- URLs
@pytest.mark.parametrize(
    "url", ["https://scholarships.gov.in", "http://www.aicte-india.org/path?q=1", "https://www.tribal.mp.gov.in/MPTAAS", "https://a.b.c.gov.in:8443/x"],
)
def test_valid_urls(url: str) -> None:
    assert is_valid_url(url)


@pytest.mark.parametrize(
    "url", [None, "", "scholarships.gov.in", "www.example.com", "ftp://example.com", "https://", "https://localhost",
            "https://exa mple.com", "https://scholarships.gov.in (National Scholarship Portal)", "https://bad_host.in",
            "https://example.123", "htp://example.com", "https://example.com:notaport"],
)
def test_invalid_urls(url: str | None) -> None:
    assert not is_valid_url(url)


def test_extract_urls_from_decorated_cells() -> None:
    assert extract_urls("https://scholarships.gov.in (National Scholarship Portal)") == ["https://scholarships.gov.in"]
    assert extract_urls("https://www.aicte-india.org / https://scholarships.gov.in") == [
        "https://www.aicte-india.org", "https://scholarships.gov.in"]
    assert extract_urls("see https://a.gov.in/x.") == ["https://a.gov.in/x"]


def test_url_cell_flags_cleaned_and_multiple_and_keeps_invalid_text() -> None:
    clean = parse_url_cell("https://scholarships.gov.in")
    assert (clean.url, clean.cleaned, clean.multiple) == ("https://scholarships.gov.in", False, False)
    decorated = parse_url_cell("https://scholarships.gov.in (National Scholarship Portal)")
    assert (decorated.url, decorated.cleaned, decorated.multiple) == ("https://scholarships.gov.in", True, False)
    several = parse_url_cell("https://a.gov.in / https://b.gov.in")
    assert (several.url, several.multiple, several.all_urls) == ("https://a.gov.in", True, ["https://a.gov.in", "https://b.gov.in"])
    invalid = parse_url_cell("scholarships.gov.in")
    assert invalid.url == "scholarships.gov.in" and not invalid.all_urls  # kept so the validator reports it
    assert parse_url_cell(None).url is None


def test_government_domain_detection() -> None:
    assert is_government_domain("https://scholarships.gov.in")
    assert is_government_domain("https://scholarshipportal.mp.nic.in/")
    assert not is_government_domain("https://www.aicte-india.org")
    assert not is_government_domain("https://evilgov.in")


# ----------------------------------------------------------------- lists, states, keys
def test_split_list_dedupes_trims_and_keeps_order() -> None:
    assert split_list("9 ,10,11,12") == ["9", "10", "11", "12"]
    assert split_list("UG, PG ") == ["UG", "PG"]
    assert split_list("SC,sc,ST", upper=True) == ["SC", "ST"]
    assert split_list("Master's; ph.D") == ["Master's", "ph.D"]
    assert split_list("a\nb|c") == ["a", "b", "c"]
    assert split_list(None) == [] and split_list(float("nan")) == [] and split_list("NA, ,") == []


def test_split_list_all_sentinel_variants() -> None:
    for text in ("ALL COURSES", "ALLCOURSES", "ALL STREAMS", "All Categories", "ALL"):
        assert split_list(text, all_sentinel=True) == ["ALL"]
    assert split_list("ALL COURSES", all_sentinel=False) == ["ALL COURSES"]


def test_resolve_states_names_abbreviations_and_all() -> None:
    assert resolve_states("MP") == (["Madhya Pradesh"], [])
    assert resolve_states("WEST BENGAL, up") == (["West Bengal", "Uttar Pradesh"], [])
    assert resolve_states("J&K and LADAKH") == (["Jammu and Kashmir", "Ladakh"], [])
    assert resolve_states("Jammu & Kashmir") == (["Jammu and Kashmir"], [])
    assert resolve_states("Orissa") == (["Odisha"], [])
    assert resolve_states("ALL") == (["ALL"], [])
    assert resolve_states(None) == ([], [])


def test_resolve_states_unknown_is_kept_and_reported() -> None:
    assert resolve_states("Atlantis") == (["Atlantis"], ["Atlantis"])


def test_government_level_to_scheme_type() -> None:
    assert government_level_to_scheme_type("CENTRAL") == "central"
    assert government_level_to_scheme_type("MP") == "state"
    assert government_level_to_scheme_type("WEST BENGAL") == "state"
    assert government_level_to_scheme_type("Atlantis") is None
    assert government_level_to_scheme_type(None) is None


def test_match_key_ignores_case_punctuation_and_ampersand() -> None:
    assert match_key("Post-Matric  Scholarship (SSP)") == match_key("post matric scholarship ssp")
    assert match_key("Prime Minister's Scholarship") == "prime ministers scholarship"
    assert match_key("PMSS for CAPFs & AR") == "pmss for capfs and ar"
    assert match_key(None) == ""
