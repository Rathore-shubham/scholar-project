"""Canonical scholarship schema, enums and the validation-issue catalog.

Design rules (also documented in the README):

* The pydantic model checks *structure and types* only. Business rules (ranges,
  date order, URL format...) live in ``validate.py`` so a bad value is reported
  instead of making the whole record unparseable.
* Unknown / unavailable values are ``None`` (scalars) or ``[]`` (collections).
  They are never replaced by 0 or by a guess.
* ``["ALL"]`` in a collection means the source explicitly says "all"; ``[]``
  means the source says nothing.
* Anything that does not fit a canonical column is kept in ``extra_attributes``
  (JSON-serializable) so no source information is lost.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ACADEMIC_YEAR_PATTERN = re.compile(r"^\d{4}-\d{2}$")
ALL_SENTINEL = "ALL"


class VerificationStatus(StrEnum):
    PENDING = "pending"  # nobody has reviewed it yet (default for every new record)
    NEEDS_REVIEW = "needs_review"  # flagged for a human look
    VERIFIED = "verified"  # reviewer + evidence recorded (see verification.py)
    REJECTED = "rejected"  # reviewer decided the record is wrong / not a scholarship


class SchemeType(StrEnum):
    CENTRAL = "central"
    STATE = "state"
    OTHER = "other"


class SourceType(StrEnum):
    LOCAL_EXCEL = "local_excel"
    LOCAL_CSV = "local_csv"
    MYSCHEME = "myscheme"
    DATA_GOV_IN = "data_gov_in"
    HUGGINGFACE = "huggingface"
    NSP = "nsp"
    MANUAL = "manual"
    OTHER = "other"


class Severity(StrEnum):
    ERROR = "error"  # a value is present but wrong / contradictory
    WARNING = "warning"  # important information is unavailable, ambiguous or unconfirmed
    INFO = "info"  # optional information is simply not in the source


# --------------------------------------------------------------------------- #
# Issue catalog: one place that fixes the severity of every check.
# --------------------------------------------------------------------------- #

E, W, I = Severity.ERROR, Severity.WARNING, Severity.INFO

ISSUE_CATALOG: dict[str, tuple[Severity, str]] = {
    # --- errors: present but invalid / contradictory
    "missing_scholarship_name": (E, "Scholarship name is missing."),
    "invalid_url": (E, "Value is not a valid http(s) URL."),
    "date_invalid": (E, "Value looks like a date but is not a real calendar date."),
    "deadline_before_open_date": (E, "Application deadline is earlier than the opening date."),
    "negative_income": (E, "Family income limit is negative."),
    "negative_amount": (E, "Award amount is negative."),
    "amount_min_exceeds_max": (E, "Minimum award amount is greater than the maximum."),
    "percentage_out_of_range": (E, "Minimum percentage is outside 0-100."),
    "duplicate_scholarship_id": (E, "scholarship_id is used by more than one record."),
    "verified_without_evidence": (E, "Status is 'verified' but last_verified_at or a source URL is missing."),
    # --- warnings: unavailable / ambiguous / unconfirmed
    "missing_provider": (W, "Provider name is missing."),
    "official_url_missing": (W, "No official URL is available for this record."),
    "missing_academic_year": (W, "Academic year is missing."),
    "missing_eligibility_details": (W, "No eligibility details are available (level, courses, states, categories, percentage, income or rules)."),
    "percentage_not_numeric": (W, "Minimum percentage is not a single unambiguous number; kept as text in eligibility_rules."),
    "percentage_possibly_fraction": (W, "Minimum percentage is between 0 and 1; it may be a fraction rather than a percentage."),
    "income_not_numeric": (W, "Family income limit is not a single unambiguous amount; kept as text in eligibility_rules."),
    "amount_not_numeric": (W, "Award amount is not a single unambiguous number; see award_amount_text."),
    "date_ambiguous": (W, "Date could be read in more than one way (DD/MM vs MM/DD); left empty."),
    "date_unparsed": (W, "Value is not a recognizable date; left empty."),
    "academic_year_unparsed": (W, "Academic year is not in a recognizable YYYY-YY form; left empty."),
    "provider_copies_scheme_name": (W, "Provider column repeats the scheme name, so it is not a real provider; left empty."),
    "unrecognized_state": (W, "State / region name was not recognized; kept as written."),
    "verification_status_unrecognized": (W, "Source verification status is not recognized; set to needs_review."),
    "verification_claim_unconfirmed": (W, "Source claims 'verified' but the pipeline cannot confirm it; set to needs_review."),
    "record_needs_review": (W, "Record is flagged needs_review."),
    "verification_outdated": (W, "Last verification is older than the allowed age."),
    "deadline_passed": (W, "Application deadline is in the past; the record may be outdated."),
    "duplicate_scholarship_name": (W, "Another record has the same normalized scholarship name."),
    "possible_duplicate": (W, "Record is similar to another record; review manually."),
    "verification_decision_rejected": (W, "A reviewer decision for this record was not applied."),
    # --- info: optional information not present
    "source_url_missing": (I, "No source_url; provenance is the local source file and row."),
    "missing_application_open_date": (I, "Application opening date is not available."),
    "missing_application_deadline": (I, "Application deadline is not available."),
    "official_url_multiple": (I, "Source cell listed several URLs; first one used, all kept in extra_attributes."),
    "official_url_cleaned": (I, "Extra text was removed around the URL in the source cell."),
    "official_url_non_government_domain": (I, "official_url is not on a .gov.in/.nic.in/.ac.in/.edu.in domain; confirm it is the official site."),
    "unverified_record": (I, "Record has not been reviewed yet (verification_status=pending)."),
    "record_rejected": (I, "Record was rejected by a reviewer."),
    "scheme_type_unmapped": (I, "government_level could not be mapped to central/state."),
}


@dataclass(frozen=True)
class Issue:
    code: str
    severity: Severity
    field: str | None
    message: str

    def to_dict(self) -> dict[str, str | None]:
        return {
            "code": self.code,
            "severity": self.severity.value,
            "field": self.field,
            "message": self.message,
        }


def make_issue(code: str, field: str | None = None, detail: str | None = None) -> Issue:
    """Build an Issue whose severity/message come from the catalog."""
    severity, text = ISSUE_CATALOG[code]
    message = f"{text} ({detail})" if detail else text
    return Issue(code=code, severity=severity, field=field, message=message)


# --------------------------------------------------------------------------- #
# Canonical record
# --------------------------------------------------------------------------- #


class ScholarshipRecord(BaseModel):
    """One scholarship, in the canonical ScholarPath schema."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, validate_assignment=True)

    # --- identity
    scholarship_id: str = Field(min_length=1, description="Source id if the source has one, otherwise a deterministic id generated from name/provider/level (prefix 'SP-').")
    scholarship_name: str | None = Field(None, description="Official scholarship / scheme name (whitespace-cleaned only).")
    provider_name: str | None = Field(None, description="Ministry / department / organisation that runs the scheme.")
    scheme_type: SchemeType | None = Field(None, description="'central' or 'state', derived from the source's government level.")
    academic_year: str | None = Field(None, description="Canonical 'YYYY-YY', only when the source states it unambiguously.")

    # --- eligibility
    education_level: list[str] = Field(default_factory=list, description="Level tokens as written in the source (e.g. '12', 'UG', 'PG'); order preserved, duplicates removed.")
    eligible_courses: list[str] = Field(default_factory=list, description="Course/stream tokens; ['ALL'] when the source says all courses.")
    eligible_states: list[str] = Field(default_factory=list, description="Canonical state/UT names; ['ALL'] when open to all states.")
    eligible_categories: list[str] = Field(default_factory=list, description="Upper-case category codes (SC, ST, OBC, ...); ['ALL'] when open to all.")
    minimum_percentage: float | None = Field(None, description="Single minimum percentage; null when the source gives board-specific or complex conditions.")
    maximum_family_income: float | None = Field(None, description="Single annual family-income ceiling in INR; null when conditional / category-specific / a range. Missing is never 0.")

    # --- award
    award_amount_min: float | None = Field(None, description="Numeric amount in INR, only for a single unambiguous number or explicit range.")
    award_amount_max: float | None = Field(None, description="See award_amount_min.")
    award_amount_text: str | None = Field(None, description="Human-readable benefit description from the source (period/currency live here).")

    # --- application
    application_open_date: date | None = None
    application_deadline: date | None = None
    required_documents: list[str] = Field(default_factory=list)
    eligibility_rules: list[str] = Field(default_factory=list, description="Source conditions that no canonical column can hold, quoted as stated (never interpreted).")
    application_procedure: str | None = None

    # --- provenance & verification
    official_url: str | None = None
    source_url: str | None = Field(None, description="Page/API/file URL the record was extracted from; null for local files.")
    source_name: str | None = None
    source_type: SourceType = SourceType.OTHER
    extracted_at: datetime = Field(description="Timezone-aware UTC time the source content was first extracted.")
    last_verified_at: date | None = Field(None, description="Date a human last verified the record (null until reviewed).")
    verification_status: VerificationStatus = VerificationStatus.PENDING
    review_notes: str | None = None

    # --- pipeline metadata (not part of the 27 canonical fields)
    source_record_id: str | None = Field(None, description="Identifier exactly as given in the source (null if the source has none).")
    source_file: str | None = None
    source_sheet: str | None = None
    source_row: int | None = Field(None, description="1-based row number in the source sheet (header row counts as given in the file).")
    duplicate_group_id: str | None = Field(None, description="Set when the record is part of a possible-duplicate group.")
    validation_status: Literal["ok", "warning", "error"] | None = None
    validation_issue_codes: list[str] = Field(default_factory=list)
    extra_attributes: dict[str, Any] = Field(default_factory=dict, description="Source-specific data with no canonical column (gender, government level, raw text of unparsed values...).")

    @field_validator("academic_year")
    @classmethod
    def _academic_year_shape(cls, value: str | None) -> str | None:
        if value is not None and not ACADEMIC_YEAR_PATTERN.match(value):
            raise ValueError("academic_year must look like '2024-25'")
        return value

    @field_validator("extracted_at")
    @classmethod
    def _extracted_at_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("extracted_at must be timezone-aware (UTC)")
        return value


CANONICAL_FIELDS: tuple[str, ...] = (
    "scholarship_id", "scholarship_name", "provider_name", "scheme_type", "academic_year",
    "education_level", "eligible_courses", "eligible_states", "eligible_categories",
    "minimum_percentage", "maximum_family_income",
    "award_amount_min", "award_amount_max", "award_amount_text",
    "application_open_date", "application_deadline",
    "required_documents", "eligibility_rules", "application_procedure",
    "official_url", "source_url", "source_name", "source_type",
    "extracted_at", "last_verified_at", "verification_status", "review_notes",
)

PIPELINE_FIELDS: tuple[str, ...] = (
    "source_record_id", "source_file", "source_sheet", "source_row",
    "duplicate_group_id", "validation_status", "validation_issue_codes", "extra_attributes",
)

ALL_FIELDS: tuple[str, ...] = CANONICAL_FIELDS + PIPELINE_FIELDS

# Fields that are non-scalar; CSV stores them as JSON text so they round-trip exactly.
COLLECTION_FIELDS: frozenset[str] = frozenset(
    name for name, info in ScholarshipRecord.model_fields.items()
    if str(info.annotation).startswith(("list", "dict"))
)

assert set(ALL_FIELDS) == set(ScholarshipRecord.model_fields), "field lists out of sync with the model"
