"""Synthetic test data and helpers. Nothing here is real scholarship data - names are labelled as fixtures."""

from __future__ import annotations

import csv
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.domain import CriterionView, FilterOptions, ScholarshipQuery, ScholarshipView, SearchResult
from app.services.importer.records import ETL_COLUMNS, JSON_COLUMNS


def etl_record(**overrides: Any) -> dict[str, Any]:
    """A valid ETL-shaped record (all 35 columns) for a synthetic, unverified scholarship."""
    record: dict[str, Any] = {
        "scholarship_id": "SP-TEST000001",
        "scholarship_name": "Alpha Merit Scholarship (test fixture)",
        "provider_name": "Test Department of Education",
        "scheme_type": "central",
        "academic_year": None,
        "education_level": ["12"],
        "eligible_courses": ["ALL"],
        "eligible_states": ["ALL"],
        "eligible_categories": ["SC", "ST"],
        "minimum_percentage": None,
        "maximum_family_income": None,
        "award_amount_min": None,
        "award_amount_max": None,
        "award_amount_text": None,
        "application_open_date": None,
        "application_deadline": None,
        "required_documents": [],
        "eligibility_rules": [],
        "application_procedure": None,
        "official_url": "https://scholarships.gov.in",
        "source_url": None,
        "source_name": "fixture.xlsx",
        "source_type": "local_excel",
        "extracted_at": "2026-10-12T05:03:39Z",
        "last_verified_at": None,
        "verification_status": "pending",
        "review_notes": None,
        "source_record_id": None,
        "source_file": "fixture.xlsx",
        "source_sheet": "Sheet1",
        "source_row": 2,
        "duplicate_group_id": None,
        "validation_status": "warning",
        "validation_issue_codes": ["missing_academic_year"],
        "extra_attributes": {"government_level": "CENTRAL", "gender": ["MALE", "FEMALE", "OTHERS"]},
    }
    assert set(record) == set(ETL_COLUMNS)
    record.update(overrides)
    return record


def write_json(path: Path, records: Sequence[dict[str, Any]], *, wrapper: bool = True) -> Path:
    payload: Any = {"schema_version": "1", "record_count": len(records), "records": list(records)} if wrapper else list(records)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def write_csv(path: Path, records: Sequence[dict[str, Any]], *, extra_columns: Sequence[str] = ()) -> Path:
    """Write records the way the ETL does: list/dict columns as JSON text, None as an empty cell, UTF-8 BOM."""
    columns = [*ETL_COLUMNS, *extra_columns]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        for record in records:
            row = []
            for column in columns:
                value = record.get(column)
                if value is None:
                    row.append("")
                elif column in JSON_COLUMNS:
                    row.append(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
                else:
                    row.append(str(value))
            writer.writerow(row)
    return path


def memory_engine() -> Engine:
    """In-memory SQLite with foreign keys on and every table created from the models."""
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_connection: Any, _record: Any) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    return engine


def criterion(
    criterion_type: str, operator: str, required_value: dict[str, Any], *, label: str | None = None,
    reviewed: bool = False, evidence: str | None = None, mandatory: bool = True, order: int = 0,
) -> CriterionView:
    return CriterionView(
        criterion_type=criterion_type, label=label or criterion_type.replace("_", " ").title(), operator=operator,
        required_value=required_value, is_mandatory=mandatory,
        review_status="reviewed" if reviewed else "unreviewed", evidence_text=evidence, source_ref="fixture.xlsx / Sheet1 / row 2",
        display_order=order,
    )


def view(scholarship_id: str = "SP-TEST000001", *, status: str = "pending", criteria: Sequence[CriterionView] = (), **kw: Any) -> ScholarshipView:
    fields: dict[str, Any] = {
        "name": "Alpha Merit Scholarship (test fixture)", "provider_name": "Test Department", "scheme_type": "central",
        "education_levels": ("12",), "eligible_states": ("ALL",), "eligible_categories": ("SC", "ST"),
    }
    fields.update(kw)
    return ScholarshipView(scholarship_id=scholarship_id, verification_status=status, criteria=tuple(criteria), **fields)


class StubRepository:
    """Repository double: serves fixed views and records the query it was given (no database involved)."""

    def __init__(self, views: Sequence[ScholarshipView] = (), *, total: int | None = None) -> None:
        self.views = list(views)
        self.total = total
        self.last_query: ScholarshipQuery | None = None

    def search(self, query: ScholarshipQuery) -> SearchResult:
        self.last_query = query
        return SearchResult(list(self.views), len(self.views) if self.total is None else self.total)

    def get(self, scholarship_id: str) -> ScholarshipView | None:
        return next((v for v in self.views if v.scholarship_id == scholarship_id), None)

    def get_many(self, scholarship_ids: Sequence[str]) -> list[ScholarshipView]:
        by_id = {v.scholarship_id: v for v in self.views}
        return [by_id[i] for i in scholarship_ids if i in by_id]

    def filter_options(self) -> FilterOptions:
        return FilterOptions(
            states=["Madhya Pradesh"], education_levels=["12", "UG"], categories=["SC"], genders=["FEMALE"],
            scheme_types=["central"], total_scholarships=len(self.views), verified_scholarships=0,
        )
