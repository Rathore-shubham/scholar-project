"""Column-name normalization, canonical mapping and row -> record conversion."""

from __future__ import annotations

from datetime import date

import pytest

from conftest import CTX, HEADERS, NOW, build, make_row
from scholarpath_data.normalize import make_ids_unique, map_columns, normalize_column_name, normalize_columns, NormalizedRecord
from scholarpath_data.schema import SchemeType, SourceType, VerificationStatus


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Scholarship Name", "scholarship_name"), ("SCHOLARSHIP_ID", "scholarship_id"), (" key benefits ", "key_benefits"),
        ("scholarshipName", "scholarship_name"), ("Max Family-Income (INR)", "max_family_income_inr"),
        ("official_url", "official_url"), ("  ", "unnamed"), (123, "123"), ("__A__B__", "a_b"),
    ],
)
def test_normalize_column_name(raw: object, expected: str) -> None:
    assert normalize_column_name(raw) == expected


def test_duplicate_normalized_names_get_suffixes() -> None:
    assert normalize_columns(["Name", "name", "NAME"]) == {"Name": "name", "name": "name_2", "NAME": "name_3"}


def test_all_source_headers_map_to_canonical_keys() -> None:
    mapping = map_columns(normalize_columns(HEADERS).values())
    assert mapping.extras == []
    assert mapping.by_key["scholarship_name"] == "scholarship_name"
    assert mapping.by_key["provider_name"] == "provider"
    assert mapping.by_key["minimum_percentage"] == "min_percentage"
    assert mapping.by_key["maximum_family_income"] == "max_family_income"
    assert mapping.by_key["application_deadline"] == "deadline"
    assert mapping.by_key["key_benefits"] == "key_benefits"


def test_unknown_columns_are_kept_as_extras_and_first_claim_wins() -> None:
    mapping = map_columns(["scholarship_name", "name", "hostel_available"])
    assert mapping.by_key == {"scholarship_name": "scholarship_name"}
    assert mapping.extras == ["name", "hostel_available"]


def test_unmapped_source_column_ends_up_in_extra_attributes() -> None:
    from scholarpath_data.normalize import build_record

    mapping = map_columns(["scholarship_name", "hostel_available"])
    item = build_record({"scholarship_name": "X", "hostel_available": " Yes "}, mapping, CTX, "S", 2)
    assert item.record.extra_attributes["hostel_available"] == "Yes"


# ----------------------------------------------------------------- record building
def test_basic_row_is_cleaned_and_mapped() -> None:
    rec, issues = build(make_row(**{"Scholarship Name": "  PM   YASASVI Scheme ", "education_level": 12,
                                    "eligible_categories": "ST,SC,OBC", "provider": "Ministry of Social Justice"}))
    assert rec.scholarship_name == "PM YASASVI Scheme"
    assert rec.education_level == ["12"]
    assert rec.eligible_courses == ["ALL"] and rec.eligible_states == ["ALL"]
    assert rec.eligible_categories == ["ST", "SC", "OBC"]
    assert rec.scheme_type is SchemeType.CENTRAL
    assert rec.source_type is SourceType.LOCAL_EXCEL
    assert rec.extracted_at == NOW
    assert (rec.source_file, rec.source_sheet, rec.source_row) == ("test.xlsx", "Sheet1", 2)
    assert issues == []


def test_missing_values_become_null_or_empty_never_invented() -> None:
    rec, _ = build(make_row(eligible_courses=None, eligible_categories="NA", max_family_income=None, min_percentage="-", amount=float("nan")))
    assert rec.eligible_courses == [] and rec.eligible_categories == []
    assert rec.maximum_family_income is None  # missing income is NOT zero
    assert rec.minimum_percentage is None
    assert rec.award_amount_min is None and rec.award_amount_max is None
    assert rec.academic_year is None and rec.application_deadline is None and rec.application_procedure is None
    assert rec.last_verified_at is None and rec.official_url is not None


def test_state_scheme_with_abbreviation() -> None:
    rec, _ = build(make_row(government_level="MP", eligible_states="MP"))
    assert rec.scheme_type is SchemeType.STATE
    assert rec.eligible_states == ["Madhya Pradesh"]
    assert rec.extra_attributes["government_level"] == "MP"


def test_numbers_are_parsed_only_when_unambiguous() -> None:
    rec, issues = build(make_row(max_family_income="<8,00,000", min_percentage="60", amount="3,00,000"))
    assert rec.maximum_family_income == 800000
    assert rec.extra_attributes["maximum_family_income_comparator"] == "<"
    assert rec.minimum_percentage == 60
    assert (rec.award_amount_min, rec.award_amount_max) == (300000, 300000)
    assert issues == []


def test_ambiguous_values_are_nulled_preserved_and_warned() -> None:
    rec, issues = build(make_row(
        max_family_income="SC/ST - 2,50,000 ; OBC - 1,50,000", min_percentage="MP BOARD-60",
        amount="GIRLS - 3,000 ; BOYS - 2,500", **{"key benefits": "₹3,000 per month for Girls"}))
    assert rec.maximum_family_income is None and rec.minimum_percentage is None
    assert (rec.award_amount_min, rec.award_amount_max) == (None, None)
    assert {i.code for i in issues} == {"income_not_numeric", "percentage_not_numeric", "amount_not_numeric"}
    assert "Family income limit (as stated in source): SC/ST - 2,50,000 ; OBC - 1,50,000" in rec.eligibility_rules
    assert "Minimum percentage (as stated in source): MP BOARD-60" in rec.eligibility_rules
    assert rec.extra_attributes["amount_raw"] == "GIRLS - 3,000 ; BOYS - 2,500"
    assert rec.award_amount_text == "₹3,000 per month for Girls"  # benefits text, not parsed into numbers


def test_amount_text_falls_back_to_raw_only_when_unparseable() -> None:
    rec, _ = build(make_row(amount="12,000(first 3yrs); 20,000 (post graduation)"))
    assert rec.award_amount_text == "12,000(first 3yrs); 20,000 (post graduation)"
    rec2, _ = build(make_row(amount=50000))
    assert rec2.award_amount_text is None and rec2.award_amount_min == 50000


def test_gender_restriction_becomes_a_rule_and_extra() -> None:
    rec, _ = build(make_row(gender="FEMALE"))
    assert rec.extra_attributes["gender"] == ["FEMALE"]
    assert rec.eligibility_rules == ["Gender (as stated in source): FEMALE"]
    open_rec, _ = build(make_row(gender="MALE,FEMALE,OTHERS"))
    assert open_rec.eligibility_rules == []


def test_dates_ambiguous_invalid_and_valid() -> None:
    rec, issues = build(make_row(application_open_date="2026-01-05", deadline="03/04/2026"))
    assert rec.application_open_date == date(2026, 1, 5)
    assert rec.application_deadline is None
    assert [i.code for i in issues] == ["date_ambiguous"]
    assert rec.extra_attributes["application_deadline_raw"] == "03/04/2026"

    _, issues2 = build(make_row(deadline="31/02/2026"))
    assert [(i.code, i.severity.value) for i in issues2] == [("date_invalid", "error")]
    _, issues3 = build(make_row(deadline="rolling"))
    assert [i.code for i in issues3] == ["date_unparsed"]


def test_official_url_cell_cleaning_and_issues() -> None:
    rec, issues = build(make_row(official_url="https://scholarships.gov.in (National Scholarship Portal)"))
    assert rec.official_url == "https://scholarships.gov.in"
    assert [i.code for i in issues] == ["official_url_cleaned"]

    rec2, issues2 = build(make_row(official_url="https://a.gov.in / https://b.gov.in"))
    assert rec2.official_url == "https://a.gov.in"
    assert rec2.extra_attributes["official_urls_all"] == ["https://a.gov.in", "https://b.gov.in"]
    assert [i.code for i in issues2] == ["official_url_multiple"]

    rec3, issues3 = build(make_row(official_url="scholarships.gov.in"))
    assert rec3.official_url == "scholarships.gov.in"  # kept verbatim; validate.py raises invalid_url
    assert issues3 == []


def test_provider_that_copies_scheme_name_is_nulled_and_preserved() -> None:
    rec, issues = build(make_row(**{"Scholarship Name": "Bihar Post-Matric Scholarship (PMS)", "provider": "Bihar Post Matric Scholarship PMS"}))
    assert rec.provider_name is None
    assert rec.extra_attributes["provider_raw"] == "Bihar Post Matric Scholarship PMS"
    assert [i.code for i in issues] == ["provider_copies_scheme_name"]


def test_unknown_state_is_kept_and_warned() -> None:
    rec, issues = build(make_row(eligible_states="Atlantis"))
    assert rec.eligible_states == ["Atlantis"]
    assert [i.code for i in issues] == ["unrecognized_state"]


# ----------------------------------------------------------------- verification status & ids
def test_empty_status_is_pending_and_never_verified() -> None:
    rec, _ = build(make_row())
    assert rec.verification_status is VerificationStatus.PENDING


def test_source_claim_of_verified_is_not_trusted() -> None:
    rec, issues = build(make_row(verification_status="Verified", last_verified_at="2026-01-01"))
    assert rec.verification_status is VerificationStatus.NEEDS_REVIEW
    assert "verification_claim_unconfirmed" in {i.code for i in issues}
    assert "not accepted" in (rec.review_notes or "")


@pytest.mark.parametrize(
    "raw, expected",
    [("pending", VerificationStatus.PENDING), ("Not Verified", VerificationStatus.PENDING),
     ("needs review", VerificationStatus.NEEDS_REVIEW), ("REJECTED", VerificationStatus.REJECTED)],
)
def test_other_status_values(raw: str, expected: VerificationStatus) -> None:
    rec, issues = build(make_row(verification_status=raw))
    assert rec.verification_status is expected and issues == []


def test_unrecognized_status_goes_to_needs_review() -> None:
    rec, issues = build(make_row(verification_status="approved??"))
    assert rec.verification_status is VerificationStatus.NEEDS_REVIEW
    assert [i.code for i in issues] == ["verification_status_unrecognized"]


def test_generated_ids_are_deterministic_and_source_ids_preserved() -> None:
    first, _ = build(make_row())
    again, _ = build(make_row(), source_row=99)  # row number must not change the id
    assert first.scholarship_id == again.scholarship_id and first.scholarship_id.startswith("SP-")
    assert first.source_record_id is None
    other, _ = build(make_row(**{"Scholarship Name": "Different"}))
    assert other.scholarship_id != first.scholarship_id

    given, _ = build(make_row(SCHOLARSHIP_ID=" SCH-001 "))
    assert given.scholarship_id == "SCH-001" and given.source_record_id == "SCH-001"


def test_colliding_generated_ids_get_suffixes_in_row_order() -> None:
    a, _ = build(make_row(), 2)
    b, _ = build(make_row(), 3)
    c, _ = build(make_row(SCHOLARSHIP_ID="X1"), 4)
    items = [NormalizedRecord(a, [], True), NormalizedRecord(b, [], True), NormalizedRecord(c, [], False)]
    base = a.scholarship_id
    make_ids_unique(items)
    assert [i.record.scholarship_id for i in items] == [base, f"{base}-2", "X1"]
