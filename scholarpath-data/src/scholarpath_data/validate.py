"""Record-level and cross-record validation.

Severity policy (see ``schema.ISSUE_CATALOG`` for every code):

* error   - a value is present but invalid or contradictory;
* warning - important information is unavailable, ambiguous or unconfirmed;
* info    - optional information is simply not in the source.

A missing optional field never produces an error.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Iterable

from scholarpath_data.parsers import is_government_domain, is_valid_url
from scholarpath_data.schema import (
    Issue,
    ScholarshipRecord,
    Severity,
    VerificationStatus,
    make_issue,
)

DEFAULT_MAX_VERIFICATION_AGE_DAYS = 365


def _check_url(issues: list[Issue], field: str, value: str | None) -> None:
    if value is not None and not is_valid_url(value):
        issues.append(make_issue("invalid_url", field, f"value {value!r}"))


def validate_record(
    record: ScholarshipRecord,
    as_of: date,
    max_verification_age_days: int = DEFAULT_MAX_VERIFICATION_AGE_DAYS,
) -> list[Issue]:
    """Rule-based issues for one record (normalization-time issues are kept separately)."""
    issues: list[Issue] = []
    extra = record.extra_attributes

    # --- identity / provenance
    if not record.scholarship_name:
        issues.append(make_issue("missing_scholarship_name", "scholarship_name"))
    if not record.provider_name and "provider_raw" not in extra:
        issues.append(make_issue("missing_provider", "provider_name"))

    if record.official_url is None:
        issues.append(make_issue("official_url_missing", "official_url"))
    else:
        _check_url(issues, "official_url", record.official_url)
        if is_valid_url(record.official_url) and not is_government_domain(record.official_url):
            issues.append(make_issue("official_url_non_government_domain", "official_url", f"value {record.official_url!r}"))
    if record.source_url is None:
        issues.append(make_issue("source_url_missing", "source_url"))
    else:
        _check_url(issues, "source_url", record.source_url)

    # --- academic year / eligibility
    if record.academic_year is None and "academic_year_raw" not in extra:
        issues.append(make_issue("missing_academic_year", "academic_year"))
    if not (
        record.education_level or record.eligible_courses or record.eligible_states
        or record.eligible_categories or record.eligibility_rules
        or record.minimum_percentage is not None or record.maximum_family_income is not None
    ):
        issues.append(make_issue("missing_eligibility_details", "eligibility"))

    # --- numeric ranges
    pct = record.minimum_percentage
    if pct is not None:
        if pct < 0 or pct > 100:
            issues.append(make_issue("percentage_out_of_range", "minimum_percentage", f"value {pct:g}"))
        elif 0 < pct <= 1:
            issues.append(make_issue("percentage_possibly_fraction", "minimum_percentage", f"value {pct:g}"))
    if record.maximum_family_income is not None and record.maximum_family_income < 0:
        issues.append(make_issue("negative_income", "maximum_family_income", f"value {record.maximum_family_income:g}"))
    low, high = record.award_amount_min, record.award_amount_max
    for field_name, amount in (("award_amount_min", low), ("award_amount_max", high)):
        if amount is not None and amount < 0:
            issues.append(make_issue("negative_amount", field_name, f"value {amount:g}"))
    if low is not None and high is not None and low > high:
        issues.append(make_issue("amount_min_exceeds_max", "award_amount_min", f"{low:g} > {high:g}"))

    # --- dates
    opens, deadline = record.application_open_date, record.application_deadline
    if opens is None and "application_open_date_raw" not in extra:
        issues.append(make_issue("missing_application_open_date", "application_open_date"))
    if deadline is None and "application_deadline_raw" not in extra:
        issues.append(make_issue("missing_application_deadline", "application_deadline"))
    if opens and deadline and deadline < opens:
        issues.append(make_issue("deadline_before_open_date", "application_deadline", f"{deadline} < {opens}"))
    if deadline and deadline < as_of:
        issues.append(make_issue("deadline_passed", "application_deadline", f"{deadline} is before {as_of}"))

    # --- verification
    status = record.verification_status
    if status is VerificationStatus.PENDING:
        issues.append(make_issue("unverified_record", "verification_status"))
    elif status is VerificationStatus.NEEDS_REVIEW:
        issues.append(make_issue("record_needs_review", "verification_status"))
    elif status is VerificationStatus.REJECTED:
        issues.append(make_issue("record_rejected", "verification_status"))
    elif status is VerificationStatus.VERIFIED:
        has_source = any(is_valid_url(u) for u in (record.official_url, record.source_url) if u)
        if record.last_verified_at is None or not has_source:
            issues.append(make_issue("verified_without_evidence", "verification_status"))
        elif (as_of - record.last_verified_at).days > max_verification_age_days:
            issues.append(
                make_issue(
                    "verification_outdated", "last_verified_at",
                    f"last verified {record.last_verified_at}, limit {max_verification_age_days} days",
                )
            )
    return issues


def find_duplicate_ids(records: Iterable[ScholarshipRecord]) -> dict[str, list[ScholarshipRecord]]:
    """scholarship_ids shared by several records (ids are the key reviewers and decisions use)."""
    by_id: dict[str, list[ScholarshipRecord]] = defaultdict(list)
    for record in records:
        by_id[record.scholarship_id].append(record)
    return {key: group for key, group in by_id.items() if len(group) > 1}


def status_from_issues(issues: Iterable[Issue]) -> str:
    severities = {issue.severity for issue in issues}
    if Severity.ERROR in severities:
        return "error"
    return "warning" if Severity.WARNING in severities else "ok"


def unique_issues(issues: Iterable[Issue]) -> list[Issue]:
    """Drop exact repeats while keeping order."""
    seen: set[Issue] = set()
    result: list[Issue] = []
    for issue in issues:
        if issue not in seen:
            seen.add(issue)
            result.append(issue)
    return result
