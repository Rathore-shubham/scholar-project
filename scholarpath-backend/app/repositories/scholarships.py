"""Scholarship repository: a small Protocol plus the SQLAlchemy implementation.

Services depend on the Protocol, so business logic and API wiring can be tested with a stub while the SQL
itself is tested against an in-memory SQLite database (all queries here are portable SQL; PostgreSQL is never
required for the unit tests).

Search semantics (documented in the README):
* ``rejected`` records are never returned.
* A value filter (state / education level / category / gender) matches records that list the value OR list
  ``ALL``. Records that are silent about that attribute do not match an explicit filter.
* ``student_percentage`` / ``student_income`` keep records whose numeric requirement is unknown (null) or
  satisfied; null never means 0.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from typing import Protocol

from sqlalchemy import Select, exists, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.domain import (
    ALL,
    CriterionView,
    FilterOptions,
    ScholarshipQuery,
    ScholarshipView,
    SearchResult,
)
from app.models import Scholarship, ScholarshipValue

MAX_TERMS = 8


class ScholarshipRepository(Protocol):
    def search(self, query: ScholarshipQuery) -> SearchResult: ...
    def get(self, scholarship_id: str) -> ScholarshipView | None: ...
    def get_many(self, scholarship_ids: Sequence[str]) -> list[ScholarshipView]: ...
    def filter_options(self) -> FilterOptions: ...


def _like_pattern(term: str) -> str:
    escaped = term.casefold().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _has_value(kind: str, wanted: str) -> object:
    """EXISTS(value row of this kind equal to ``wanted`` or to ALL)."""
    return exists().where(
        ScholarshipValue.scholarship_pk == Scholarship.id,
        ScholarshipValue.kind == kind,
        func.lower(ScholarshipValue.value).in_([wanted.casefold(), ALL.casefold()]),
    )


def _to_view(row: Scholarship) -> ScholarshipView:
    grouped: dict[str, list[str]] = defaultdict(list)
    for value in row.values:
        grouped[value.kind].append(value.value)
    criteria = tuple(
        CriterionView(
            criterion_type=c.criterion_type, label=c.label, operator=c.operator, required_value=dict(c.required_value),
            is_mandatory=c.is_mandatory, review_status=c.review_status, evidence_text=c.evidence_text,
            evidence_url=c.evidence_url, source_ref=c.source_ref, display_order=c.display_order,
        )
        for c in sorted(row.criteria, key=lambda c: c.display_order)
    )
    return ScholarshipView(
        scholarship_id=row.scholarship_id, name=row.name, verification_status=row.verification_status,
        provider_name=row.provider_name, scheme_type=row.scheme_type, government_level=row.government_level,
        academic_year=row.academic_year,
        education_levels=tuple(grouped["education_level"]), eligible_courses=tuple(grouped["course"]),
        eligible_states=tuple(grouped["state"]), eligible_categories=tuple(grouped["category"]),
        eligible_genders=tuple(grouped["gender"]),
        minimum_percentage=row.minimum_percentage, maximum_family_income=row.maximum_family_income,
        income_comparator=row.income_comparator, award_amount_min=row.award_amount_min,
        award_amount_max=row.award_amount_max, award_amount_text=row.award_amount_text,
        application_open_date=row.application_open_date, application_deadline=row.application_deadline,
        application_procedure=row.application_procedure,
        required_documents=tuple(row.required_documents or ()), eligibility_rules=tuple(row.eligibility_rules or ()),
        official_url=row.official_url, source_url=row.source_url, source_name=row.source_name,
        source_type=row.source_type, extracted_at=row.extracted_at, last_verified_at=row.last_verified_at,
        review_notes=row.review_notes, source_file=row.source_file, source_sheet=row.source_sheet,
        source_row=row.source_row, source_record_id=row.source_record_id, duplicate_group_id=row.duplicate_group_id,
        etl_validation_status=row.etl_validation_status, etl_issue_codes=tuple(row.etl_issue_codes or ()),
        extra_attributes=dict(row.extra_attributes or {}), criteria=criteria,
    )


class SqlScholarshipRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------ queries
    def _base(self) -> Select[tuple[Scholarship]]:
        return select(Scholarship).where(Scholarship.verification_status != "rejected")

    def _filtered(self, query: ScholarshipQuery) -> Select[tuple[Scholarship]]:
        stmt = self._base()
        if query.verified_only:
            stmt = stmt.where(Scholarship.verification_status == "verified")
        if query.ids:
            stmt = stmt.where(Scholarship.scholarship_id.in_(list(query.ids)))
        if query.scheme_type:
            stmt = stmt.where(Scholarship.scheme_type == query.scheme_type)
        if query.state:
            stmt = stmt.where(_has_value("state", query.state))
        if query.education_level:
            stmt = stmt.where(_has_value("education_level", query.education_level))
        if query.category:
            stmt = stmt.where(_has_value("category", query.category))
        if query.gender:
            stmt = stmt.where(_has_value("gender", query.gender))
        if query.student_percentage is not None:
            stmt = stmt.where(
                or_(Scholarship.minimum_percentage.is_(None), Scholarship.minimum_percentage <= query.student_percentage)
            )
        if query.student_income is not None:
            stmt = stmt.where(
                or_(Scholarship.maximum_family_income.is_(None), Scholarship.maximum_family_income >= query.student_income)
            )
        if query.min_award is not None:
            stmt = stmt.where(Scholarship.award_amount_max >= query.min_award)
        for term in (query.text or "").split()[:MAX_TERMS]:
            pattern = _like_pattern(term)
            stmt = stmt.where(
                or_(
                    func.lower(Scholarship.name).like(pattern, escape="\\"),
                    func.lower(Scholarship.provider_name).like(pattern, escape="\\"),
                    func.lower(Scholarship.award_amount_text).like(pattern, escape="\\"),
                    func.lower(Scholarship.government_level).like(pattern, escape="\\"),
                    func.lower(Scholarship.scheme_type).like(pattern, escape="\\"),
                    exists().where(
                        ScholarshipValue.scholarship_pk == Scholarship.id,
                        func.lower(ScholarshipValue.value).like(pattern, escape="\\"),
                    ),
                )
            )
        return stmt

    @staticmethod
    def _ordered(stmt: Select[tuple[Scholarship]], sort: str) -> Select[tuple[Scholarship]]:
        name_order = (func.lower(Scholarship.name), Scholarship.id)
        if sort == "amount_desc":
            return stmt.order_by(Scholarship.award_amount_max.desc().nulls_last(), *name_order)
        if sort == "deadline":
            return stmt.order_by(Scholarship.application_deadline.asc().nulls_last(), *name_order)
        if sort == "recently_verified":
            return stmt.order_by(Scholarship.last_verified_at.desc().nulls_last(), *name_order)
        return stmt.order_by(*name_order)

    # ------------------------------------------------------------------ protocol
    def search(self, query: ScholarshipQuery) -> SearchResult:
        filtered = self._filtered(query)
        total = self._session.scalar(select(func.count()).select_from(filtered.order_by(None).subquery())) or 0
        stmt = (
            self._ordered(filtered, query.sort)
            .options(selectinload(Scholarship.values), selectinload(Scholarship.criteria))
            .offset((query.page - 1) * query.page_size)
            .limit(query.page_size)
        )
        return SearchResult([_to_view(row) for row in self._session.scalars(stmt)], int(total))

    def get(self, scholarship_id: str) -> ScholarshipView | None:
        stmt = (
            self._base()
            .where(Scholarship.scholarship_id == scholarship_id)
            .options(selectinload(Scholarship.values), selectinload(Scholarship.criteria))
        )
        row = self._session.scalars(stmt).first()
        return _to_view(row) if row else None

    def get_many(self, scholarship_ids: Sequence[str]) -> list[ScholarshipView]:
        if not scholarship_ids:
            return []
        stmt = (
            self._base()
            .where(Scholarship.scholarship_id.in_(list(scholarship_ids)))
            .options(selectinload(Scholarship.values), selectinload(Scholarship.criteria))
        )
        by_id = {row.scholarship_id: _to_view(row) for row in self._session.scalars(stmt)}
        return [by_id[sid] for sid in scholarship_ids if sid in by_id]  # preserves the requested order

    def filter_options(self) -> FilterOptions:
        rows = self._session.execute(
            select(ScholarshipValue.kind, ScholarshipValue.value)
            .join(Scholarship, Scholarship.id == ScholarshipValue.scholarship_pk)
            .where(Scholarship.verification_status != "rejected", func.lower(ScholarshipValue.value) != ALL.casefold())
            .distinct()
        ).all()
        by_kind: dict[str, set[str]] = defaultdict(set)
        for kind, value in rows:
            by_kind[kind].add(value)
        scheme_types = sorted(
            {s for (s,) in self._session.execute(
                select(Scholarship.scheme_type).where(Scholarship.verification_status != "rejected").distinct()
            ) if s}
        )
        total = self._session.scalar(select(func.count()).select_from(self._base().subquery())) or 0
        verified = self._session.scalar(
            select(func.count()).select_from(self._base().where(Scholarship.verification_status == "verified").subquery())
        ) or 0
        return FilterOptions(
            states=sorted(by_kind["state"]), education_levels=sorted(by_kind["education_level"]),
            categories=sorted(by_kind["category"]), genders=sorted(by_kind["gender"]),
            scheme_types=scheme_types, total_scholarships=int(total), verified_scholarships=int(verified),
        )
