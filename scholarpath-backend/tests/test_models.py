"""Model constraints, enforced on in-memory SQLite (the same CHECK / UNIQUE / FK rules the PostgreSQL schema has)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import ImportRun, Scholarship, ScholarshipCriterion, ScholarshipValue
from tests.support import memory_engine


def scholarship(**overrides: Any) -> Scholarship:
    fields: dict[str, Any] = dict(
        scholarship_id="SP-M000001", name="Model Test Scholarship", source_type="local_excel",
        extracted_at=datetime(2026, 10, 12, tzinfo=timezone.utc), source_hash="0" * 64,
    )
    fields.update(overrides)
    return Scholarship(**fields)


@pytest.fixture()
def session():
    engine = memory_engine()
    with Session(engine) as s:
        yield s


def commit_fails(session: Session, obj: Scholarship) -> None:
    session.add(obj)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_defaults_are_unverified_and_empty_not_zero(session: Session) -> None:
    session.add(scholarship())
    session.commit()
    row = session.scalars(select(Scholarship)).one()
    assert row.verification_status == "pending"
    assert row.required_documents == [] and row.eligibility_rules == [] and row.etl_issue_codes == []
    assert row.extra_attributes == {}
    assert row.maximum_family_income is None and row.minimum_percentage is None  # null, never 0
    assert row.created_at is not None and row.updated_at is not None


def test_stable_scholarship_id_is_unique(session: Session) -> None:
    session.add(scholarship())
    session.commit()
    commit_fails(session, scholarship(name="Another record with the same id"))


@pytest.mark.parametrize(
    "overrides",
    [
        {"verification_status": "approved"},
        {"verification_status": "verified"},  # no last_verified_at -> refused by the database itself
        {"scheme_type": "galactic"},
        {"minimum_percentage": 101}, {"minimum_percentage": -1},
        {"maximum_family_income": -5}, {"income_comparator": ">"},
        {"award_amount_min": -1}, {"award_amount_min": 900, "award_amount_max": 100},
        {"application_open_date": date(2026, 9, 1), "application_deadline": date(2026, 8, 1)},
        {"name": None}, {"extracted_at": None}, {"source_type": None},
    ],
)
def test_invalid_rows_are_rejected_by_the_database(session: Session, overrides: dict[str, Any]) -> None:
    commit_fails(session, scholarship(**overrides))


def test_verified_needs_a_verification_date(session: Session) -> None:
    session.add(scholarship(verification_status="verified", last_verified_at=date(2026, 10, 1)))
    session.commit()
    assert session.scalars(select(Scholarship)).one().verification_status == "verified"


def test_valid_boundaries_are_accepted(session: Session) -> None:
    session.add(
        scholarship(
            minimum_percentage=0, maximum_family_income=0, award_amount_min=100, award_amount_max=100,
            application_open_date=date(2026, 9, 1), application_deadline=date(2026, 9, 1), income_comparator="<=",
        )
    )
    session.commit()


def test_children_cascade_with_the_scholarship(session: Session) -> None:
    obj = scholarship()
    obj.values.append(ScholarshipValue(kind="state", value="Madhya Pradesh"))
    obj.criteria.append(
        ScholarshipCriterion(criterion_type="state", label="State", operator="in", required_value={"values": ["Madhya Pradesh"]}, display_order=0)
    )
    session.add(obj)
    session.commit()
    assert session.scalars(select(ScholarshipValue)).one().kind == "state"
    crit = session.scalars(select(ScholarshipCriterion)).one()
    assert crit.is_mandatory is True and crit.review_status == "unreviewed" and crit.origin == "etl"
    session.delete(obj)
    session.commit()
    assert session.scalars(select(ScholarshipValue)).all() == [] and session.scalars(select(ScholarshipCriterion)).all() == []


def test_value_and_criterion_constraints(session: Session) -> None:
    obj = scholarship()
    obj.values.extend([ScholarshipValue(kind="state", value="Bihar"), ScholarshipValue(kind="state", value="Bihar")])
    commit_fails(session, obj)  # duplicate (scholarship, kind, value)

    obj2 = scholarship(scholarship_id="SP-M000002")
    obj2.values.append(ScholarshipValue(kind="planet", value="Mars"))
    commit_fails(session, obj2)

    for bad in (
        dict(criterion_type="vibes", operator="in", review_status="unreviewed", origin="etl"),
        dict(criterion_type="state", operator="approx", review_status="unreviewed", origin="etl"),
        dict(criterion_type="state", operator="in", review_status="maybe", origin="etl"),
        dict(criterion_type="state", operator="in", review_status="unreviewed", origin="robot"),
    ):
        o = scholarship(scholarship_id=f"SP-{abs(hash(str(bad))) % 10**8:08d}")
        o.criteria.append(ScholarshipCriterion(label="x", required_value={}, display_order=0, **bad))
        commit_fails(session, o)


def test_import_run_status_is_constrained(session: Session) -> None:
    session.add(ImportRun(status="running"))
    session.commit()
    session.add(ImportRun(status="exploded"))
    with pytest.raises(IntegrityError):
        session.commit()
