"""Response schemas for the scholarship endpoints."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

VerificationStatusLiteral = Literal["pending", "needs_review", "verified", "rejected"]


class ScholarshipSummary(BaseModel):
    scholarship_id: str = Field(description="Stable ETL id (use it in URLs)")
    name: str
    provider_name: str | None = None
    scheme_type: Literal["central", "state", "other"] | None = None
    government_level: str | None = None
    education_levels: list[str] = Field(description="ETL tokens, e.g. ['9','10','UG']")
    education_level_labels: list[str] = Field(description="Readable labels, e.g. ['Class 9','Class 10','Undergraduate']")
    eligible_states: list[str]
    eligible_categories: list[str]
    award_amount_min: float | None = None
    award_amount_max: float | None = None
    award_amount_text: str | None = None
    application_deadline: date | None = Field(default=None, description="null = not available in the source")
    official_url: str | None = None
    verification_status: VerificationStatusLiteral
    is_verified: bool
    last_verified_at: date | None = None
    data_notice: str | None = Field(description="Plain-language caveat shown to users for unverified records")


class CriterionOut(BaseModel):
    criterion_type: str
    label: str
    operator: str
    required_value: dict[str, Any]
    is_mandatory: bool
    review_status: Literal["unreviewed", "reviewed", "disputed"]
    evidence_text: str | None = None
    evidence_url: str | None = None
    source_ref: str | None = Field(default=None, description="Where the ETL got it (file / sheet / row); not a citation of the rule")


class Provenance(BaseModel):
    source_file: str | None = None
    source_sheet: str | None = None
    source_row: int | None = None
    source_record_id: str | None = None
    duplicate_group_id: str | None = None
    etl_validation_status: str | None = None
    etl_issue_codes: list[str] = []


class ScholarshipDetail(ScholarshipSummary):
    academic_year: str | None = None
    eligible_courses: list[str]
    eligible_genders: list[str]
    minimum_percentage: float | None = None
    maximum_family_income: float | None = None
    income_comparator: Literal["<", "<="] | None = None
    application_open_date: date | None = None
    application_procedure: str | None = None
    required_documents: list[str]
    eligibility_rules: list[str] = Field(description="Source conditions stored as text, quoted as stated")
    source_url: str | None = None
    source_name: str | None = None
    source_type: str
    extracted_at: datetime | None = None
    review_notes: str | None = None
    provenance: Provenance
    extra_attributes: dict[str, Any]
    criteria: list[CriterionOut]


class ScholarshipListResponse(BaseModel):
    items: list[ScholarshipSummary]
    total: int
    page: int
    page_size: int
    pages: int


class FilterOptionsResponse(BaseModel):
    states: list[str]
    education_levels: list[dict[str, str]] = Field(description="[{'value': token, 'label': readable}]")
    categories: list[str]
    genders: list[str]
    scheme_types: list[str]
    total_scholarships: int
    verified_scholarships: int
