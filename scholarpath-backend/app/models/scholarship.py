"""SQLAlchemy 2.x models for scholarships, their filterable values, criteria and import runs.

Column set is derived from the real ETL output (``scholarships_cleaned.csv`` / ``.json``, 35 columns);
nothing is invented and nulls stay null. Types are portable on purpose: ``JSON`` becomes ``JSONB`` on
PostgreSQL, and multi-valued attributes live in a relational ``scholarship_values`` table instead of arrays,
so every query can also be exercised on in-memory SQLite in unit tests (PostgreSQL itself is never needed
to run the test-suite).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

# BigInteger identity on PostgreSQL; plain INTEGER primary key on SQLite (needed for autoincrement there).
PK_TYPE = BigInteger().with_variant(Integer, "sqlite")
JsonType = JSON().with_variant(JSONB(), "postgresql")


def _num(precision: int, scale: int) -> Numeric:
    return Numeric(precision, scale, asdecimal=False)


class ImportRun(Base):
    """Audit row for one importer run that wrote to the database."""

    __tablename__ = "import_runs"
    __table_args__ = (
        CheckConstraint("status IN ('running', 'succeeded', 'failed')", name="status_valid"),
    )

    id: Mapped[int] = mapped_column(PK_TYPE, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_file: Mapped[str | None] = mapped_column(Text)
    source_sha256: Mapped[str | None] = mapped_column(String(64))
    source_format: Mapped[str | None] = mapped_column(String(8))
    records_read: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    inserted: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    updated: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    unchanged: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    skipped: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    failed: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'running'"))
    error_message: Mapped[str | None] = mapped_column(Text)


class Scholarship(Base):
    """One scholarship record, mirroring the ETL record faithfully."""

    __tablename__ = "scholarships"
    __table_args__ = (
        UniqueConstraint("scholarship_id"),
        CheckConstraint(
            "verification_status IN ('pending', 'needs_review', 'verified', 'rejected')",
            name="verification_status_valid",
        ),
        # The database itself refuses a 'verified' record that has no verification date.
        CheckConstraint("verification_status <> 'verified' OR last_verified_at IS NOT NULL", name="verified_has_date"),
        CheckConstraint("scheme_type IS NULL OR scheme_type IN ('central', 'state', 'other')", name="scheme_type_valid"),
        CheckConstraint(
            "minimum_percentage IS NULL OR (minimum_percentage >= 0 AND minimum_percentage <= 100)",
            name="minimum_percentage_range",
        ),
        CheckConstraint("maximum_family_income IS NULL OR maximum_family_income >= 0", name="income_non_negative"),
        CheckConstraint("income_comparator IS NULL OR income_comparator IN ('<', '<=')", name="income_comparator_valid"),
        CheckConstraint(
            "(award_amount_min IS NULL OR award_amount_min >= 0) AND (award_amount_max IS NULL OR award_amount_max >= 0)",
            name="award_non_negative",
        ),
        CheckConstraint(
            "award_amount_min IS NULL OR award_amount_max IS NULL OR award_amount_min <= award_amount_max",
            name="award_min_le_max",
        ),
        CheckConstraint(
            "application_open_date IS NULL OR application_deadline IS NULL OR application_deadline >= application_open_date",
            name="deadline_after_open",
        ),
        Index("ix_scholarships_verification_status", "verification_status"),
        Index("ix_scholarships_scheme_type", "scheme_type"),
        Index("ix_scholarships_name", "name"),
    )

    id: Mapped[int] = mapped_column(PK_TYPE, primary_key=True, autoincrement=True)
    scholarship_id: Mapped[str] = mapped_column(String(64), nullable=False)  # stable ETL id, used in URLs
    name: Mapped[str] = mapped_column(Text, nullable=False)
    provider_name: Mapped[str | None] = mapped_column(Text)
    scheme_type: Mapped[str | None] = mapped_column(String(16))
    government_level: Mapped[str | None] = mapped_column(Text)
    academic_year: Mapped[str | None] = mapped_column(String(7))

    minimum_percentage: Mapped[float | None] = mapped_column(_num(5, 2))
    maximum_family_income: Mapped[float | None] = mapped_column(_num(14, 2))
    income_comparator: Mapped[str | None] = mapped_column(String(2))
    award_amount_min: Mapped[float | None] = mapped_column(_num(14, 2))
    award_amount_max: Mapped[float | None] = mapped_column(_num(14, 2))
    award_amount_text: Mapped[str | None] = mapped_column(Text)

    application_open_date: Mapped[date | None] = mapped_column(Date)
    application_deadline: Mapped[date | None] = mapped_column(Date)
    application_procedure: Mapped[str | None] = mapped_column(Text)
    required_documents: Mapped[list[str]] = mapped_column(JsonType, nullable=False, default=list, server_default=text("'[]'"))
    eligibility_rules: Mapped[list[str]] = mapped_column(JsonType, nullable=False, default=list, server_default=text("'[]'"))

    official_url: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    source_name: Mapped[str | None] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    extracted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_verified_at: Mapped[date | None] = mapped_column(Date)
    verification_status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'pending'"))
    review_notes: Mapped[str | None] = mapped_column(Text)

    etl_validation_status: Mapped[str | None] = mapped_column(String(8))
    etl_issue_codes: Mapped[list[str]] = mapped_column(JsonType, nullable=False, default=list, server_default=text("'[]'"))
    duplicate_group_id: Mapped[str | None] = mapped_column(String(32))
    source_file: Mapped[str | None] = mapped_column(Text)
    source_sheet: Mapped[str | None] = mapped_column(Text)
    source_row: Mapped[int | None] = mapped_column(Integer)
    source_record_id: Mapped[str | None] = mapped_column(Text)
    extra_attributes: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False, default=dict, server_default=text("'{}'"))

    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # sha256 of the input record (change detection)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_import_run_id: Mapped[int | None] = mapped_column(PK_TYPE, ForeignKey("import_runs.id", ondelete="SET NULL"))

    values: Mapped[list[ScholarshipValue]] = relationship(
        back_populates="scholarship", cascade="all, delete-orphan", order_by="ScholarshipValue.id"
    )
    criteria: Mapped[list[ScholarshipCriterion]] = relationship(
        back_populates="scholarship", cascade="all, delete-orphan", order_by="ScholarshipCriterion.display_order"
    )


class ScholarshipValue(Base):
    """Filterable multi-valued attribute (state, category, education level, course, gender). ``ALL`` = explicit 'all'."""

    __tablename__ = "scholarship_values"
    __table_args__ = (
        UniqueConstraint("scholarship_pk", "kind", "value"),
        CheckConstraint("kind IN ('education_level', 'course', 'state', 'category', 'gender')", name="kind_valid"),
        Index("ix_scholarship_values_kind_value", "kind", "value"),
    )

    id: Mapped[int] = mapped_column(PK_TYPE, primary_key=True, autoincrement=True)
    scholarship_pk: Mapped[int] = mapped_column(PK_TYPE, ForeignKey("scholarships.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)

    scholarship: Mapped[Scholarship] = relationship(back_populates="values")


class ScholarshipCriterion(Base):
    """One eligibility criterion with its review status and (when available) source evidence.

    The ETL carries no per-criterion citations, mandatory flags or review status: rows derived from it are
    ``origin='etl'``, ``review_status='unreviewed'`` and have no evidence, so they can never establish a
    positive eligibility result on their own.
    """

    __tablename__ = "scholarship_criteria"
    __table_args__ = (
        UniqueConstraint("scholarship_pk", "display_order"),
        CheckConstraint(
            "criterion_type IN ('education_level', 'state', 'category', 'gender', 'course', "
            "'minimum_percentage', 'maximum_family_income', 'other_rule')",
            name="criterion_type_valid",
        ),
        CheckConstraint("operator IN ('in', 'gte', 'lte', 'lt', 'text')", name="operator_valid"),
        CheckConstraint("review_status IN ('unreviewed', 'reviewed', 'disputed')", name="review_status_valid"),
        CheckConstraint("origin IN ('etl', 'reviewer')", name="origin_valid"),
    )

    id: Mapped[int] = mapped_column(PK_TYPE, primary_key=True, autoincrement=True)
    scholarship_pk: Mapped[int] = mapped_column(PK_TYPE, ForeignKey("scholarships.id", ondelete="CASCADE"), nullable=False)
    criterion_type: Mapped[str] = mapped_column(String(32), nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    operator: Mapped[str] = mapped_column(String(8), nullable=False)
    required_value: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)
    is_mandatory: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=true())
    review_status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'unreviewed'"))
    evidence_text: Mapped[str | None] = mapped_column(Text)
    evidence_url: Mapped[str | None] = mapped_column(Text)
    source_ref: Mapped[str | None] = mapped_column(Text)
    origin: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'etl'"))
    display_order: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    scholarship: Mapped[Scholarship] = relationship(back_populates="criteria")
