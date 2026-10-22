"""Scholarship service: turns repository views into API schemas. No SQL, no HTTP."""

from __future__ import annotations

import math

from app.core.errors import NotFoundError
from app.domain import FilterOptions, ScholarshipQuery, ScholarshipView
from app.repositories.scholarships import ScholarshipRepository
from app.schemas.scholarship import (
    CriterionOut,
    FilterOptionsResponse,
    Provenance,
    ScholarshipDetail,
    ScholarshipListResponse,
    ScholarshipSummary,
)
from app.services.vocabulary import education_label, education_sort_key

UNVERIFIED_NOTICE = (
    "Unverified: this record was extracted from source data and has not been reviewed. "
    "Do not treat it as a confirmed, currently available opportunity; check the official source."
)
NEEDS_REVIEW_NOTICE = (
    "Flagged for review: this record may be incomplete or out of date. "
    "Check the official source before relying on it."
)


def data_notice(status: str) -> str | None:
    if status == "pending":
        return UNVERIFIED_NOTICE
    if status == "needs_review":
        return NEEDS_REVIEW_NOTICE
    return None


def to_summary(view: ScholarshipView) -> ScholarshipSummary:
    levels = sorted(view.education_levels, key=education_sort_key)
    return ScholarshipSummary(
        scholarship_id=view.scholarship_id, name=view.name, provider_name=view.provider_name,
        scheme_type=view.scheme_type, government_level=view.government_level,  # type: ignore[arg-type]
        education_levels=levels, education_level_labels=[education_label(t) for t in levels],
        eligible_states=list(view.eligible_states), eligible_categories=list(view.eligible_categories),
        award_amount_min=view.award_amount_min, award_amount_max=view.award_amount_max,
        award_amount_text=view.award_amount_text, application_deadline=view.application_deadline,
        official_url=view.official_url, verification_status=view.verification_status,  # type: ignore[arg-type]
        is_verified=view.is_verified, last_verified_at=view.last_verified_at, data_notice=data_notice(view.verification_status),
    )


def to_detail(view: ScholarshipView) -> ScholarshipDetail:
    summary = to_summary(view).model_dump()
    return ScholarshipDetail(
        **summary,
        academic_year=view.academic_year, eligible_courses=list(view.eligible_courses),
        eligible_genders=list(view.eligible_genders), minimum_percentage=view.minimum_percentage,
        maximum_family_income=view.maximum_family_income,
        income_comparator=view.income_comparator,  # type: ignore[arg-type]
        application_open_date=view.application_open_date, application_procedure=view.application_procedure,
        required_documents=list(view.required_documents), eligibility_rules=list(view.eligibility_rules),
        source_url=view.source_url, source_name=view.source_name, source_type=view.source_type,
        extracted_at=view.extracted_at, review_notes=view.review_notes,
        provenance=Provenance(
            source_file=view.source_file, source_sheet=view.source_sheet, source_row=view.source_row,
            source_record_id=view.source_record_id, duplicate_group_id=view.duplicate_group_id,
            etl_validation_status=view.etl_validation_status, etl_issue_codes=list(view.etl_issue_codes),
        ),
        extra_attributes=dict(view.extra_attributes),
        criteria=[
            CriterionOut(
                criterion_type=c.criterion_type, label=c.label, operator=c.operator, required_value=dict(c.required_value),
                is_mandatory=c.is_mandatory, review_status=c.review_status,  # type: ignore[arg-type]
                evidence_text=c.evidence_text, evidence_url=c.evidence_url, source_ref=c.source_ref,
            )
            for c in view.criteria
        ],
    )


class ScholarshipService:
    def __init__(self, repository: ScholarshipRepository) -> None:
        self._repo = repository

    def list(self, query: ScholarshipQuery) -> ScholarshipListResponse:
        result = self._repo.search(query)
        pages = max(1, math.ceil(result.total / query.page_size)) if result.total else 0
        return ScholarshipListResponse(
            items=[to_summary(v) for v in result.items], total=result.total, page=query.page,
            page_size=query.page_size, pages=pages,
        )

    def get(self, scholarship_id: str) -> ScholarshipDetail:
        view = self._repo.get(scholarship_id)
        if view is None:
            raise NotFoundError("scholarship_not_found", f"No scholarship with id '{scholarship_id}'.")
        return to_detail(view)

    def filter_options(self) -> FilterOptionsResponse:
        options: FilterOptions = self._repo.filter_options()
        levels = sorted(options.education_levels, key=education_sort_key)
        return FilterOptionsResponse(
            states=options.states, education_levels=[{"value": t, "label": education_label(t)} for t in levels],
            categories=options.categories, genders=options.genders, scheme_types=options.scheme_types,
            total_scholarships=options.total_scholarships, verified_scholarships=options.verified_scholarships,
        )
