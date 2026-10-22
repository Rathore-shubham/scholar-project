"""Plain domain types shared by the repository, services and importer.

These are database-agnostic dataclasses: routes and services never touch ORM objects, which keeps the
business logic (eligibility, search semantics) testable without a database.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

ALL = "ALL"  # explicit "all" marker used by the ETL in state/category/course/level lists

VERIFICATION_STATUSES = ("pending", "needs_review", "verified", "rejected")
SCHEME_TYPES = ("central", "state", "other")
VALUE_KINDS = ("education_level", "course", "state", "category", "gender")
CRITERION_TYPES = (
    "education_level", "state", "category", "gender", "course",
    "minimum_percentage", "maximum_family_income", "other_rule",
)
OPERATORS = ("in", "gte", "lte", "lt", "text")
REVIEW_STATUSES = ("unreviewed", "reviewed", "disputed")
CRITERION_ORIGINS = ("etl", "reviewer")
SORT_OPTIONS = ("name", "amount_desc", "deadline", "recently_verified")


@dataclass(frozen=True)
class CriterionView:
    criterion_type: str
    label: str
    operator: str
    required_value: dict[str, Any]
    is_mandatory: bool = True
    review_status: str = "unreviewed"
    evidence_text: str | None = None
    evidence_url: str | None = None
    source_ref: str | None = None
    display_order: int = 0

    @property
    def has_evidence(self) -> bool:
        return bool(self.evidence_text or self.evidence_url)


@dataclass(frozen=True)
class ScholarshipView:
    scholarship_id: str
    name: str
    verification_status: str
    provider_name: str | None = None
    scheme_type: str | None = None
    government_level: str | None = None
    academic_year: str | None = None
    education_levels: tuple[str, ...] = ()
    eligible_courses: tuple[str, ...] = ()
    eligible_states: tuple[str, ...] = ()
    eligible_categories: tuple[str, ...] = ()
    eligible_genders: tuple[str, ...] = ()
    minimum_percentage: float | None = None
    maximum_family_income: float | None = None
    income_comparator: str | None = None
    award_amount_min: float | None = None
    award_amount_max: float | None = None
    award_amount_text: str | None = None
    application_open_date: date | None = None
    application_deadline: date | None = None
    application_procedure: str | None = None
    required_documents: tuple[str, ...] = ()
    eligibility_rules: tuple[str, ...] = ()
    official_url: str | None = None
    source_url: str | None = None
    source_name: str | None = None
    source_type: str = "other"
    extracted_at: datetime | None = None
    last_verified_at: date | None = None
    review_notes: str | None = None
    source_file: str | None = None
    source_sheet: str | None = None
    source_row: int | None = None
    source_record_id: str | None = None
    duplicate_group_id: str | None = None
    etl_validation_status: str | None = None
    etl_issue_codes: tuple[str, ...] = ()
    extra_attributes: dict[str, Any] = field(default_factory=dict)
    criteria: tuple[CriterionView, ...] = ()

    @property
    def is_verified(self) -> bool:
        return self.verification_status == "verified"


@dataclass(frozen=True)
class ScholarshipQuery:
    text: str | None = None
    state: str | None = None
    education_level: str | None = None  # ETL token, e.g. "UG", "12"
    category: str | None = None
    gender: str | None = None  # ETL token: MALE / FEMALE / OTHERS
    scheme_type: str | None = None
    student_percentage: float | None = None
    student_income: float | None = None
    min_award: float | None = None
    verified_only: bool = False
    ids: tuple[str, ...] = ()
    sort: str = "name"
    page: int = 1
    page_size: int = 12


@dataclass(frozen=True)
class SearchResult:
    items: list[ScholarshipView]
    total: int


@dataclass(frozen=True)
class FilterOptions:
    states: list[str] = field(default_factory=list)
    education_levels: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    genders: list[str] = field(default_factory=list)
    scheme_types: list[str] = field(default_factory=list)
    total_scholarships: int = 0
    verified_scholarships: int = 0
