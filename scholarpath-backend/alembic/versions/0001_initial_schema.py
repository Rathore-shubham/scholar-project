"""Initial schema: scholarships, scholarship_values, scholarship_criteria, import_runs.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-10-12

Hand-written (there was no database to autogenerate against) and verified against the models by
``tests/test_migration.py``, which compares this migration's PostgreSQL SQL with the DDL generated from the
models. It has NOT been run against a real database yet.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "import_runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_file", sa.Text(), nullable=True),
        sa.Column("source_sha256", sa.String(length=64), nullable=True),
        sa.Column("source_format", sa.String(length=8), nullable=True),
        sa.Column("records_read", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("inserted", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("updated", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("unchanged", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("skipped", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("failed", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("status", sa.String(length=16), server_default=sa.text("'running'"), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_import_runs"),
        sa.CheckConstraint("status IN ('running', 'succeeded', 'failed')", name=op.f("ck_import_runs_status_valid")),
    )

    op.create_table(
        "scholarships",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("scholarship_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("provider_name", sa.Text(), nullable=True),
        sa.Column("scheme_type", sa.String(length=16), nullable=True),
        sa.Column("government_level", sa.Text(), nullable=True),
        sa.Column("academic_year", sa.String(length=7), nullable=True),
        sa.Column("minimum_percentage", sa.Numeric(5, 2, asdecimal=False), nullable=True),
        sa.Column("maximum_family_income", sa.Numeric(14, 2, asdecimal=False), nullable=True),
        sa.Column("income_comparator", sa.String(length=2), nullable=True),
        sa.Column("award_amount_min", sa.Numeric(14, 2, asdecimal=False), nullable=True),
        sa.Column("award_amount_max", sa.Numeric(14, 2, asdecimal=False), nullable=True),
        sa.Column("award_amount_text", sa.Text(), nullable=True),
        sa.Column("application_open_date", sa.Date(), nullable=True),
        sa.Column("application_deadline", sa.Date(), nullable=True),
        sa.Column("application_procedure", sa.Text(), nullable=True),
        sa.Column("required_documents", postgresql.JSONB(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("eligibility_rules", postgresql.JSONB(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("official_url", sa.Text(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("source_name", sa.Text(), nullable=True),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_verified_at", sa.Date(), nullable=True),
        sa.Column("verification_status", sa.String(length=16), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("etl_validation_status", sa.String(length=8), nullable=True),
        sa.Column("etl_issue_codes", postgresql.JSONB(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("duplicate_group_id", sa.String(length=32), nullable=True),
        sa.Column("source_file", sa.Text(), nullable=True),
        sa.Column("source_sheet", sa.Text(), nullable=True),
        sa.Column("source_row", sa.Integer(), nullable=True),
        sa.Column("source_record_id", sa.Text(), nullable=True),
        sa.Column("extra_attributes", postgresql.JSONB(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_import_run_id", sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_scholarships"),
        sa.UniqueConstraint("scholarship_id", name="uq_scholarships_scholarship_id"),
        sa.ForeignKeyConstraint(
            ["last_import_run_id"], ["import_runs.id"],
            name="fk_scholarships_last_import_run_id_import_runs", ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "verification_status IN ('pending', 'needs_review', 'verified', 'rejected')",
            name=op.f("ck_scholarships_verification_status_valid"),
        ),
        sa.CheckConstraint(
            "verification_status <> 'verified' OR last_verified_at IS NOT NULL",
            name=op.f("ck_scholarships_verified_has_date"),
        ),
        sa.CheckConstraint(
            "scheme_type IS NULL OR scheme_type IN ('central', 'state', 'other')",
            name=op.f("ck_scholarships_scheme_type_valid"),
        ),
        sa.CheckConstraint(
            "minimum_percentage IS NULL OR (minimum_percentage >= 0 AND minimum_percentage <= 100)",
            name=op.f("ck_scholarships_minimum_percentage_range"),
        ),
        sa.CheckConstraint(
            "maximum_family_income IS NULL OR maximum_family_income >= 0",
            name=op.f("ck_scholarships_income_non_negative"),
        ),
        sa.CheckConstraint(
            "income_comparator IS NULL OR income_comparator IN ('<', '<=')",
            name=op.f("ck_scholarships_income_comparator_valid"),
        ),
        sa.CheckConstraint(
            "(award_amount_min IS NULL OR award_amount_min >= 0) AND (award_amount_max IS NULL OR award_amount_max >= 0)",
            name=op.f("ck_scholarships_award_non_negative"),
        ),
        sa.CheckConstraint(
            "award_amount_min IS NULL OR award_amount_max IS NULL OR award_amount_min <= award_amount_max",
            name=op.f("ck_scholarships_award_min_le_max"),
        ),
        sa.CheckConstraint(
            "application_open_date IS NULL OR application_deadline IS NULL OR application_deadline >= application_open_date",
            name=op.f("ck_scholarships_deadline_after_open"),
        ),
    )
    op.create_index("ix_scholarships_verification_status", "scholarships", ["verification_status"])
    op.create_index("ix_scholarships_scheme_type", "scholarships", ["scheme_type"])
    op.create_index("ix_scholarships_name", "scholarships", ["name"])

    op.create_table(
        "scholarship_values",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("scholarship_pk", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_scholarship_values"),
        sa.UniqueConstraint("scholarship_pk", "kind", "value", name="uq_scholarship_values_scholarship_pk"),
        sa.ForeignKeyConstraint(
            ["scholarship_pk"], ["scholarships.id"],
            name="fk_scholarship_values_scholarship_pk_scholarships", ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "kind IN ('education_level', 'course', 'state', 'category', 'gender')",
            name=op.f("ck_scholarship_values_kind_valid"),
        ),
    )
    op.create_index("ix_scholarship_values_kind_value", "scholarship_values", ["kind", "value"])

    op.create_table(
        "scholarship_criteria",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("scholarship_pk", sa.BigInteger(), nullable=False),
        sa.Column("criterion_type", sa.String(length=32), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("operator", sa.String(length=8), nullable=False),
        sa.Column("required_value", postgresql.JSONB(), nullable=False),
        sa.Column("is_mandatory", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("review_status", sa.String(length=16), server_default=sa.text("'unreviewed'"), nullable=False),
        sa.Column("evidence_text", sa.Text(), nullable=True),
        sa.Column("evidence_url", sa.Text(), nullable=True),
        sa.Column("source_ref", sa.Text(), nullable=True),
        sa.Column("origin", sa.String(length=16), server_default=sa.text("'etl'"), nullable=False),
        sa.Column("display_order", sa.SmallInteger(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_scholarship_criteria"),
        sa.UniqueConstraint("scholarship_pk", "display_order", name="uq_scholarship_criteria_scholarship_pk"),
        sa.ForeignKeyConstraint(
            ["scholarship_pk"], ["scholarships.id"],
            name="fk_scholarship_criteria_scholarship_pk_scholarships", ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "criterion_type IN ('education_level', 'state', 'category', 'gender', 'course', "
            "'minimum_percentage', 'maximum_family_income', 'other_rule')",
            name=op.f("ck_scholarship_criteria_criterion_type_valid"),
        ),
        sa.CheckConstraint("operator IN ('in', 'gte', 'lte', 'lt', 'text')", name=op.f("ck_scholarship_criteria_operator_valid")),
        sa.CheckConstraint(
            "review_status IN ('unreviewed', 'reviewed', 'disputed')", name=op.f("ck_scholarship_criteria_review_status_valid")
        ),
        sa.CheckConstraint("origin IN ('etl', 'reviewer')", name=op.f("ck_scholarship_criteria_origin_valid")),
    )


def downgrade() -> None:
    op.drop_table("scholarship_criteria")
    op.drop_index("ix_scholarship_values_kind_value", table_name="scholarship_values")
    op.drop_table("scholarship_values")
    op.drop_index("ix_scholarships_name", table_name="scholarships")
    op.drop_index("ix_scholarships_scheme_type", table_name="scholarships")
    op.drop_index("ix_scholarships_verification_status", table_name="scholarships")
    op.drop_table("scholarships")
    op.drop_table("import_runs")
