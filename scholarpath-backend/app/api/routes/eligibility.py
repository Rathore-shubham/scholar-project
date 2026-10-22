"""Eligibility check endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import EligibilityServiceDep
from app.schemas.eligibility import EligibilityCheckRequest, EligibilityCheckResponse

router = APIRouter(tags=["eligibility"])


@router.post(
    "/eligibility/check",
    response_model=EligibilityCheckResponse,
    summary="Rule-based eligibility for one or more scholarships",
    description=(
        "Deterministic, rule-based check - no scoring and no AI. Every criterion is reported with the required value, "
        "the student's value, a status (`pass`, `fail`, `missing`, `unable_to_verify`), a plain-language explanation "
        "and source evidence when it exists.\n\n"
        "`eligible` and `not_eligible` are returned only when the scholarship is **verified** and the deciding "
        "mandatory criteria are **reviewed and evidence-backed**. Otherwise the outcome is `cant_tell_yet` and "
        "`indicative` is only a hint."
    ),
)
def check_eligibility(request: EligibilityCheckRequest, service: EligibilityServiceDep) -> EligibilityCheckResponse:
    return service.check(request)
