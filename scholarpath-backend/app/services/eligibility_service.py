"""Glue between the eligibility endpoint, the repository and the pure engine."""

from __future__ import annotations

from app.repositories.scholarships import ScholarshipRepository
from app.schemas.eligibility import (
    BasisOut,
    CriterionResultOut,
    EligibilityCheckRequest,
    EligibilityCheckResponse,
    EligibilityResultOut,
    EvidenceOut,
    StudentProfileIn,
)
from app.services.eligibility import CriterionResult, EligibilityResult, StudentProfile, evaluate
from app.services.vocabulary import category_token, education_token, gender_token, state_value


def normalize_profile(profile: StudentProfileIn) -> StudentProfile:
    return StudentProfile(
        state=state_value(profile.state),
        education_level=education_token(profile.education_level),
        percentage=profile.percentage,
        family_income=profile.family_income,
        category=category_token(profile.category),
        gender=gender_token(profile.gender),
        course=(profile.course or None),
    )


def _criterion_out(c: CriterionResult) -> CriterionResultOut:
    return CriterionResultOut(
        criterion_type=c.criterion_type, criterion=c.name, required=c.required, student_value=c.student_value,
        status=c.status, explanation=c.explanation, is_mandatory=c.is_mandatory, review_status=c.review_status,
        reliable=c.reliable,
        evidence=EvidenceOut(text=c.evidence.text, url=c.evidence.url, source_ref=c.evidence.source_ref) if c.evidence else None,
    )


def result_out(result: EligibilityResult) -> EligibilityResultOut:
    return EligibilityResultOut(
        scholarship_id=result.scholarship_id, scholarship_name=result.scholarship_name, outcome=result.outcome,
        summary=result.summary, indicative=result.indicative,
        basis=BasisOut(**result.basis.__dict__), missing_information=list(result.missing_information),
        limitations=list(result.limitations), criteria=[_criterion_out(c) for c in result.criteria],
    )


class EligibilityService:
    def __init__(self, repository: ScholarshipRepository) -> None:
        self._repo = repository

    def check(self, request: EligibilityCheckRequest) -> EligibilityCheckResponse:
        profile = normalize_profile(request.profile)
        views = self._repo.get_many(request.scholarship_ids)
        found = {v.scholarship_id for v in views}
        return EligibilityCheckResponse(
            results=[result_out(evaluate(view, profile)) for view in views],
            not_found=[sid for sid in request.scholarship_ids if sid not in found],
        )
