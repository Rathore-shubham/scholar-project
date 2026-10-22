"""Shared synthetic fixtures. Nothing here touches the network or the user's real data."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import openpyxl
import pytest

from scholarpath_data.normalize import ColumnMapping, SourceContext, build_record, map_columns, normalize_columns
from scholarpath_data.schema import ScholarshipRecord, SourceType

HEADERS = [
    "SCHOLARSHIP_ID", "Scholarship Name", "government_level", "provider", "academic_year",
    "education_level", "eligible_courses", "eligible_states", "gender", "min_percentage",
    "max_family_income", "eligible_categories", "amount", "key benefits",
    "application_open_date", "deadline", "required_documents", "official_url",
    "last_verified_at", "verification_status",
]

NOW = datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
CTX = SourceContext("test.xlsx", "test.xlsx", SourceType.LOCAL_EXCEL, NOW)


def make_row(**overrides: Any) -> dict[str, Any]:
    """A source row keyed by the ORIGINAL header names, with sensible defaults."""
    row: dict[str, Any] = {h: None for h in HEADERS}
    row.update(
        {
            "Scholarship Name": "Alpha Merit Scholarship",
            "government_level": "CENTRAL",
            "provider": "Ministry of Education",
            "education_level": "12",
            "eligible_courses": "ALL COURSES",
            "eligible_states": "ALL",
            "gender": "MALE,FEMALE,OTHERS",
            "eligible_categories": "SC,ST,OBC",
            "official_url": "https://scholarships.gov.in",
        }
    )
    row.update(overrides)
    return row


def write_xlsx(path: Path, rows: list[dict[str, Any]], *, sheet: str = "Sheet1", extra_sheets: dict[str, list[list[Any]]] | None = None) -> Path:
    workbook = openpyxl.Workbook()
    ws = workbook.active
    ws.title = sheet
    ws.append(HEADERS)
    for row in rows:
        ws.append([row.get(h) for h in HEADERS])
    for name, grid in (extra_sheets or {}).items():
        other = workbook.create_sheet(name)
        for line in grid:
            other.append(line)
    workbook.save(path)
    return path


def write_csv(path: Path, rows: list[dict[str, Any]], *, encoding: str = "utf-8-sig", delimiter: str = ",") -> Path:
    import csv

    with path.open("w", newline="", encoding=encoding) as handle:
        writer = csv.writer(handle, delimiter=delimiter)
        writer.writerow(HEADERS)
        for row in rows:
            writer.writerow(["" if row.get(h) is None else row.get(h) for h in HEADERS])
    return path


def build(row: dict[str, Any], source_row: int = 2) -> tuple[ScholarshipRecord, list]:
    """Normalize one ORIGINAL-header row into (record, normalization issues)."""
    normalized = normalize_columns(HEADERS)
    mapping: ColumnMapping = map_columns(normalized.values())
    keyed = {normalized[k]: v for k, v in row.items()}
    item = build_record(keyed, mapping, CTX, "Sheet1", source_row)
    return item.record, item.issues


@pytest.fixture()
def sample_rows() -> list[dict[str, Any]]:
    return [
        make_row(),
        make_row(**{"Scholarship Name": "Beta State Scholarship", "government_level": "MP", "provider": "Dept of Higher Education",
                    "eligible_states": "MP", "max_family_income": "<8,00,000", "amount": 50000, "min_percentage": 60}),
        make_row(**{"Scholarship Name": "Gamma Girls Scholarship", "gender": "FEMALE", "amount": "GIRLS - 3,000 ; BOYS - 2,500",
                    "official_url": "https://a.gov.in (Portal) / https://b.nic.in"}),
    ]


@pytest.fixture()
def sample_xlsx(tmp_path: Path, sample_rows: list[dict[str, Any]]) -> Path:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    return write_xlsx(source_dir / "sample.xlsx", sample_rows)
