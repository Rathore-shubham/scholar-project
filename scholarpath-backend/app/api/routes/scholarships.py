"""Scholarship search and detail endpoints."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Path, Query

from app.api.deps import ScholarshipServiceDep
from app.core.errors import ApiError
from app.domain import ScholarshipQuery
from app.schemas.scholarship import FilterOptionsResponse, ScholarshipDetail, ScholarshipListResponse
from app.services.vocabulary import category_token, education_token, gender_token, state_value

router = APIRouter(tags=["scholarships"])

MAX_IDS = 50


def _parse_ids(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return ()
    ids = [part.strip() for part in raw.split(",") if part.strip()]
    if len(ids) > MAX_IDS or any(len(i) > 64 for i in ids):
        raise ApiError(422, "invalid_ids", f"'ids' accepts at most {MAX_IDS} ids of up to 64 characters.")
    return tuple(dict.fromkeys(ids))


@router.get(
    "/scholarships",
    response_model=ScholarshipListResponse,
    summary="Search scholarships",
    description=(
        "Paginated search. Rejected records are never returned. Unverified records ARE returned (each carries "
        "`verification_status`, `is_verified` and a `data_notice`); pass `verified_only=true` for verified records only. "
        "A value filter (state, education level, category, gender) matches records that list that value or `ALL`; "
        "`student_percentage` / `student_income` keep records whose requirement is unknown or satisfied."
    ),
)
def list_scholarships(
    service: ScholarshipServiceDep,
    q: Annotated[str | None, Query(max_length=200, description="Search text: name, provider, benefits, level, states, courses")] = None,
    state: Annotated[str | None, Query(max_length=60)] = None,
    education_level: Annotated[str | None, Query(max_length=40, description="Label (Undergraduate) or token (UG, 12)")] = None,
    category: Annotated[str | None, Query(max_length=40)] = None,
    gender: Annotated[str | None, Query(max_length=40)] = None,
    scheme_type: Literal["central", "state", "other"] | None = None,
    student_percentage: Annotated[float | None, Query(ge=0, le=100)] = None,
    student_income: Annotated[float | None, Query(ge=0, le=1_000_000_000)] = None,
    min_award: Annotated[float | None, Query(ge=0, le=1_000_000_000)] = None,
    verified_only: bool = False,
    ids: Annotated[str | None, Query(max_length=4000, description="Comma-separated scholarship ids (max 50)")] = None,
    sort: Literal["name", "amount_desc", "deadline", "recently_verified"] = "name",
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 12,
) -> ScholarshipListResponse:
    level = None
    if education_level and education_level.strip():
        level = education_token(education_level)
        if level is None:
            raise ApiError(422, "invalid_education_level", "Unrecognized education level; use Class 8-12, Diploma, Undergraduate or Postgraduate.")
    try:
        gender_filter = gender_token(gender)
    except ValueError as exc:
        raise ApiError(422, "invalid_gender", str(exc)) from exc
    query = ScholarshipQuery(
        text=(q or "").strip() or None, state=state_value(state), education_level=level,
        category=category_token(category), gender=gender_filter, scheme_type=scheme_type,
        student_percentage=student_percentage, student_income=student_income, min_award=min_award,
        verified_only=verified_only, ids=_parse_ids(ids), sort=sort, page=page, page_size=page_size,
    )
    return service.list(query)


@router.get(
    "/scholarships/{scholarship_id}",
    response_model=ScholarshipDetail,
    summary="Scholarship detail with criteria, sources and verification status",
    responses={404: {"description": "Unknown or rejected scholarship id"}},
)
def get_scholarship(
    scholarship_id: Annotated[str, Path(min_length=1, max_length=64)], service: ScholarshipServiceDep
) -> ScholarshipDetail:
    return service.get(scholarship_id)


@router.get(
    "/meta/filters",
    response_model=FilterOptionsResponse,
    summary="Values available for the search filters, taken from the stored records",
)
def filter_options(service: ScholarshipServiceDep) -> FilterOptionsResponse:
    return service.filter_options()
