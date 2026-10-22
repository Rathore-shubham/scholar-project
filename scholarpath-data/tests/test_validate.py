"""Validation rules (errors vs warnings vs info) and the pydantic schema."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

import pytest
from pydantic import ValidationError

from conftest import NOW
from scholarpath_data.schema import (
    ALL_FIELDS,
    CANONICAL_FIELDS,
    COLLECTION_FIELDS,
    ISSUE_CATALOG,
    ScholarshipRecord,
    Severity,
    VerificationStatus,
)
from scholarpath_data.validate import find_duplicate_ids, status_from_issues, validate_record

AS_OF = date(2026, 6, 1)


def record(**overrides: Any) -> ScholarshipRecord:
    base: dict[str, Any] = dict(
        scholarship_id="SP-1", scholarship_name="Alpha", provider_name="Ministry", academic_year="2026-27",
        education_level=["12"], official_url="https://scholarships.gov.in", extracted_at=NOW,
    )
    base.update(overrides)
    return ScholarshipRecord(**base)


def codes(rec: ScholarshipRecord, **kw: Any) -> dict[str, Severity]:
    return {i.code: i.severity for i in validate_record(rec, AS_OF, **kw)}


# ----------------------------------------------------------------- schema
def test_minimal_record_is_valid_and_defaults_are_unverified() -> None:
    rec = record()
    assert rec.verification_status is VerificationStatus.PENDING
    assert rec.eligible_courses == [] and rec.extra_attributes == {}
    assert rec.maximum_family_income is None  # absent is None, not 0


def test_every_spec_field_exists_in_the_schema() -> None:
    spec = """scholarship_id scholarship_name provider_name scheme_type academic_year education_level eligible_courses
    eligible_states eligible_categories minimum_percentage maximum_family_income award_amount_min award_amount_max
    award_amount_text application_open_date application_deadline required_documents eligibility_rules
    application_procedure official_url source_url source_name source_type extracted_at last_verified_at
    verification_status review_notes""".split()
    assert list(CANONICAL_FIELDS) == spec
    assert set(ALL_FIELDS) == set(ScholarshipRecord.model_fields)


def test_collection_fields_are_detected() -> None:
    assert {"education_level", "eligible_courses", "eligible_states", "eligible_categories", "required_documents",
            "eligibility_rules", "validation_issue_codes", "extra_attributes"} == set(COLLECTION_FIELDS)


@pytest.mark.parametrize(
    "bad",
    [
        {"verification_status": "approved"}, {"scheme_type": "galactic"}, {"source_type": "carrier_pigeon"},
        {"academic_year": "2024"}, {"academic_year": "2024-2025"}, {"scholarship_id": ""},
        {"extracted_at": datetime(2026, 1, 1)},  # naive datetime
        {"unknown_field": 1}, {"minimum_percentage": "lots"}, {"application_deadline": "not a date"},
        {"eligible_states": "MP"},  # must be a list, not a string
        {"validation_status": "fine"},
    ],
)
def test_schema_rejects_structurally_invalid_values(bad: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        record(**bad)


def test_schema_accepts_but_does_not_judge_out_of_range_values() -> None:
    # range checks are the validator's job, so a bad value is reported instead of dropping the record
    rec = record(minimum_percentage=150, award_amount_min=-5)
    assert rec.minimum_percentage == 150


def test_assignment_is_validated() -> None:
    rec = record()
    with pytest.raises(ValidationError):
        rec.verification_status = "super_verified"  # type: ignore[assignment]
    rec.verification_status = "needs_review"  # type: ignore[assignment]
    assert rec.verification_status is VerificationStatus.NEEDS_REVIEW


def test_issue_catalog_is_consistent() -> None:
    assert all(isinstance(sev, Severity) and text.endswith((".", ")")) for sev, text in ISSUE_CATALOG.values())
    assert {s for s, _ in ISSUE_CATALOG.values()} == set(Severity)


# ----------------------------------------------------------------- errors vs warnings
def test_clean_record_has_only_info_issues() -> None:
    result = codes(record(eligible_categories=["SC"]))
    assert {c for c, s in result.items() if s is not Severity.INFO} == set()
    assert status_from_issues(validate_record(record(eligible_categories=["SC"]), AS_OF)) == "ok"


def test_missing_name_is_an_error_but_missing_optionals_are_not() -> None:
    result = codes(record(scholarship_name=None))
    assert result["missing_scholarship_name"] is Severity.ERROR

    sparse = codes(record(provider_name=None, academic_year=None, official_url=None, education_level=[]))
    assert sparse["missing_provider"] is Severity.WARNING
    assert sparse["official_url_missing"] is Severity.WARNING
    assert sparse["missing_academic_year"] is Severity.WARNING
    assert sparse["missing_eligibility_details"] is Severity.WARNING
    assert sparse["source_url_missing"] is Severity.INFO
    assert Severity.ERROR not in sparse.values()  # unavailable != invalid


def test_missing_dates_are_info_only() -> None:
    result = codes(record())
    assert result["missing_application_open_date"] is Severity.INFO
    assert result["missing_application_deadline"] is Severity.INFO


@pytest.mark.parametrize("url", ["scholarships.gov.in", "https://scholarships.gov.in (National Scholarship Portal)", "ftp://x.gov.in", "https://"])
def test_invalid_urls_are_errors_for_both_url_fields(url: str) -> None:
    assert codes(record(official_url=url))["invalid_url"] is Severity.ERROR
    assert codes(record(source_url=url))["invalid_url"] is Severity.ERROR


def test_valid_non_government_domain_is_only_info() -> None:
    result = codes(record(official_url="https://www.aicte-india.org"))
    assert "invalid_url" not in result
    assert result["official_url_non_government_domain"] is Severity.INFO


def test_deadline_before_open_date_is_an_error() -> None:
    rec = record(application_open_date=date(2026, 8, 1), application_deadline=date(2026, 7, 1))
    assert codes(rec)["deadline_before_open_date"] is Severity.ERROR
    ok = record(application_open_date=date(2026, 7, 1), application_deadline=date(2026, 8, 1))
    assert "deadline_before_open_date" not in codes(ok)
    one_sided = record(application_deadline=date(2026, 8, 1))
    assert "deadline_before_open_date" not in codes(one_sided)


def test_passed_deadline_is_flagged_as_possibly_outdated() -> None:
    assert codes(record(application_deadline=date(2026, 5, 31)))["deadline_passed"] is Severity.WARNING
    assert "deadline_passed" not in codes(record(application_deadline=date(2026, 6, 1)))


def test_negative_amounts_and_income_are_errors() -> None:
    result = codes(record(maximum_family_income=-1, award_amount_min=-100, award_amount_max=-50))
    assert result["negative_income"] is Severity.ERROR and result["negative_amount"] is Severity.ERROR
    assert codes(record(award_amount_min=900, award_amount_max=100))["amount_min_exceeds_max"] is Severity.ERROR
    assert "negative_income" not in codes(record(maximum_family_income=0))  # an explicit 0 is allowed


@pytest.mark.parametrize("pct, expected", [(-1, True), (100.5, True), (150, True), (0, False), (100, False), (55, False)])
def test_percentage_range(pct: float, expected: bool) -> None:
    assert ("percentage_out_of_range" in codes(record(minimum_percentage=pct))) is expected


def test_percentage_that_looks_like_a_fraction_is_warned() -> None:
    assert codes(record(minimum_percentage=0.6))["percentage_possibly_fraction"] is Severity.WARNING
    assert "percentage_possibly_fraction" not in codes(record(minimum_percentage=60))


def test_missing_academic_year_not_reported_twice_when_it_was_unparseable() -> None:
    rec = record(academic_year=None, extra_attributes={"academic_year_raw": "2024"})
    assert "missing_academic_year" not in codes(rec)


# ----------------------------------------------------------------- verification rules
def test_pending_and_needs_review_and_rejected_states() -> None:
    assert codes(record())["unverified_record"] is Severity.INFO
    assert codes(record(verification_status="needs_review"))["record_needs_review"] is Severity.WARNING
    assert codes(record(verification_status="rejected"))["record_rejected"] is Severity.INFO


def test_verified_without_evidence_is_an_error() -> None:
    assert codes(record(verification_status="verified"))["verified_without_evidence"] is Severity.ERROR
    no_source = record(verification_status="verified", last_verified_at=date(2026, 5, 1), official_url=None)
    assert codes(no_source)["verified_without_evidence"] is Severity.ERROR
    good = record(verification_status="verified", last_verified_at=date(2026, 5, 1))
    assert "verified_without_evidence" not in codes(good)


def test_outdated_verification_is_a_warning() -> None:
    old = record(verification_status="verified", last_verified_at=date(2024, 1, 1))
    assert codes(old)["verification_outdated"] is Severity.WARNING
    assert "verification_outdated" not in codes(old, max_verification_age_days=2000)


# ----------------------------------------------------------------- cross-record
def test_duplicate_scholarship_ids_are_found() -> None:
    a, b, c = record(scholarship_id="X"), record(scholarship_id="X"), record(scholarship_id="Y")
    dupes = find_duplicate_ids([a, b, c])
    assert set(dupes) == {"X"} and len(dupes["X"]) == 2


def test_status_from_issues_precedence() -> None:
    from scholarpath_data.schema import make_issue

    assert status_from_issues([]) == "ok"
    assert status_from_issues([make_issue("source_url_missing")]) == "ok"
    assert status_from_issues([make_issue("missing_provider")]) == "warning"
    assert status_from_issues([make_issue("missing_provider"), make_issue("invalid_url")]) == "error"


def test_timezone_aware_extracted_at_is_accepted() -> None:
    assert record(extracted_at=datetime(2026, 1, 1, tzinfo=timezone.utc)).extracted_at.tzinfo is not None
