"""Reading CSV/JSON and validating ETL records."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.services.importer.records import ETL_COLUMNS, UNMAPPED_KEY, ImportInputError, RawRow, read_input, validate_row
from tests.support import etl_record, write_csv, write_json


def validate(**overrides: Any):
    return validate_row(RawRow(1, etl_record(**overrides)), [])


def test_etl_contract_has_35_unique_columns() -> None:
    assert len(ETL_COLUMNS) == 35 and len(set(ETL_COLUMNS)) == 35
    assert set(etl_record()) == set(ETL_COLUMNS)


def test_json_wrapper_and_bare_list_are_both_read(tmp_path: Path) -> None:
    records = [etl_record(), etl_record(scholarship_id="SP-TEST000002")]
    wrapped = read_input(write_json(tmp_path / "a.json", records))
    bare = read_input(write_json(tmp_path / "b.json", records, wrapper=False))
    assert wrapped.format == bare.format == "json" and len(wrapped.rows) == len(bare.rows) == 2
    assert wrapped.rows[1].index == 2 and wrapped.sha256 != bare.sha256


def test_csv_round_trips_lists_dicts_and_nulls_like_the_etl_writes_them(tmp_path: Path) -> None:
    rec = etl_record(
        education_level=["9", "10"], eligibility_rules=["Minimum percentage (as stated in source): MP BOARD-60"],
        minimum_percentage=None, maximum_family_income=450000, extra_attributes={"gender": ["FEMALE"], "n": 1},
    )
    loaded = read_input(write_csv(tmp_path / "a.csv", [rec]))
    row = loaded.rows[0].data
    assert row["education_level"] == ["9", "10"] and row["extra_attributes"] == {"gender": ["FEMALE"], "n": 1}
    assert row["minimum_percentage"] is None and row["application_deadline"] is None  # empty cell -> null, not 0
    parsed = validate_row(loaded.rows[0], loaded.unmapped_columns)
    assert parsed.maximum_family_income == 450000 and parsed.minimum_percentage is None
    assert parsed.extracted_at.tzinfo is not None


def test_csv_and_json_of_the_same_records_validate_identically(tmp_path: Path) -> None:
    records = [etl_record(maximum_family_income=250000, award_amount_min=1000, award_amount_max=5000, source_row=7)]
    a = read_input(write_csv(tmp_path / "x.csv", records))
    b = read_input(write_json(tmp_path / "x.json", records))
    assert validate_row(a.rows[0], []).model_dump() == validate_row(b.rows[0], []).model_dump()


def test_file_level_problems_are_reported_clearly(tmp_path: Path) -> None:
    with pytest.raises(ImportInputError, match="not found"):
        read_input(tmp_path / "missing.csv")
    other = tmp_path / "x.xlsx"
    other.write_bytes(b"x")
    with pytest.raises(ImportInputError, match="Unsupported input type"):
        read_input(other)
    wrong = tmp_path / "wrong.csv"
    wrong.write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(ImportInputError, match="missing required column.*scholarship_id"):
        read_input(wrong)
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    with pytest.raises(ImportInputError, match="Cannot read"):
        read_input(broken)
    shape = tmp_path / "shape.json"
    shape.write_text('{"records": "nope"}', encoding="utf-8")
    with pytest.raises(ImportInputError, match="list of records"):
        read_input(shape)
    no_required = tmp_path / "r.json"
    no_required.write_text('[{"foo": 1}]', encoding="utf-8")
    with pytest.raises(ImportInputError, match="missing required field"):
        read_input(no_required)


def test_malformed_json_cell_in_csv_fails_that_record_only(tmp_path: Path) -> None:
    path = write_csv(tmp_path / "a.csv", [etl_record(), etl_record(scholarship_id="SP-TEST000002")])
    text = path.read_text(encoding="utf-8-sig").replace('"[""12""]"', "[not-json", 1)  # csv escapes the quotes inside the cell
    path.write_text(text, encoding="utf-8-sig")
    loaded = read_input(path)
    with pytest.raises(ValueError, match="education_level.*invalid JSON"):
        validate_row(loaded.rows[0], [])
    assert validate_row(loaded.rows[1], []).scholarship_id == "SP-TEST000002"


def test_unknown_columns_are_preserved_not_discarded(tmp_path: Path) -> None:
    path = write_csv(tmp_path / "a.csv", [etl_record(hostel="Yes", empty_extra="")], extra_columns=("hostel", "empty_extra"))
    loaded = read_input(path)
    assert loaded.unmapped_columns == ["empty_extra", "hostel"]
    rec = validate_row(loaded.rows[0], loaded.unmapped_columns)
    assert rec.extra_attributes[UNMAPPED_KEY] == {"hostel": "Yes"}
    assert rec.extra_attributes["government_level"] == "CENTRAL"  # existing extras kept


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"scholarship_id": ""}, "scholarship_id"),
        ({"scholarship_id": "x" * 65}, "scholarship_id"),
        ({"scholarship_name": ""}, "scholarship_name"),
        ({"scholarship_name": None}, "scholarship_name"),
        ({"verification_status": "approved"}, "verification_status"),
        ({"scheme_type": "galactic"}, "scheme_type"),
        ({"minimum_percentage": 101}, "minimum_percentage"),
        ({"minimum_percentage": -1}, "minimum_percentage"),
        ({"maximum_family_income": -1}, "maximum_family_income"),
        ({"award_amount_min": -1}, "award_amount_min"),
        ({"award_amount_min": 9, "award_amount_max": 1}, "award_amount_min is greater"),
        ({"application_open_date": "2026-09-01", "application_deadline": "2026-08-01"}, "before application_open_date"),
        ({"application_deadline": "31/02/2026"}, "application_deadline"),
        ({"official_url": "scholarships.gov.in"}, "not a valid http"),
        ({"source_url": "https://exa mple.com"}, "not a valid http"),
        ({"extracted_at": "2026-10-12T05:03:39"}, "timezone"),
        ({"extracted_at": None}, "extracted_at"),
        ({"academic_year": "2024"}, "academic_year"),
        ({"education_level": "12"}, "education_level"),
        ({"surprise_field": 1}, "surprise_field"),
    ],
)
def test_invalid_records_are_rejected_with_a_reason(overrides: dict[str, Any], message: str) -> None:
    data = etl_record()
    data.update(overrides)
    # unknown columns are preserved by validate_row, so exercise the model directly for that case
    from app.services.importer.records import ImportRecord
    from pydantic import ValidationError

    if "surprise_field" in overrides:
        with pytest.raises(ValidationError):
            ImportRecord.model_validate(data)
        return
    with pytest.raises(ValueError, match=message):
        validate_row(RawRow(1, data), [])


def test_verified_requires_a_date_and_a_source_url() -> None:
    with pytest.raises(ValueError, match="verified.*requires"):
        validate(verification_status="verified")
    with pytest.raises(ValueError, match="verified.*requires"):
        validate(verification_status="verified", last_verified_at="2026-10-01", official_url=None)
    ok = validate(verification_status="verified", last_verified_at="2026-10-01")
    assert ok.verification_status == "verified"


def test_nulls_are_preserved_never_defaulted_to_zero() -> None:
    rec = validate()
    assert rec.minimum_percentage is None and rec.maximum_family_income is None
    assert rec.award_amount_min is None and rec.application_deadline is None and rec.source_url is None


def test_validation_error_text_does_not_echo_input_values() -> None:
    with pytest.raises(ValueError) as exc:
        validate(official_url="https://user:hunter2@bad host.com")
    assert "hunter2" not in str(exc.value)


def test_reading_never_modifies_the_input(tmp_path: Path) -> None:
    path = write_json(tmp_path / "a.json", [etl_record()])
    before = (path.read_bytes(), path.stat().st_mtime_ns)
    read_input(path)
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before
    assert json.loads(path.read_text())["record_count"] == 1
